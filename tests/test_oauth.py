"""
Вход через Google. Сеть не используется: для API подменяется OAuthProvider,
клиент Google проверяется на httpx.MockTransport.
"""
import base64
import hashlib
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.core.config import settings
from app.core.jwt import create_access_token, sign_payload
from app.domain.entities import ExternalIdentity, Role
from app.modules.auth.oauth import GoogleOAuthProvider, OAuthError, OAuthProvider, new_pkce_pair
from app.modules.auth.router import OAUTH_COOKIE, get_google_provider


class FakeProvider(OAuthProvider):
    name = "google"

    def __init__(self):
        self.identity = ExternalIdentity("google", "google-sub-1", "student@gmail.com", True)
        self.fail = False
        self.received = None

    def authorization_url(self, state: str, code_challenge: str) -> str:
        return f"https://provider.test/auth?state={state}&code_challenge={code_challenge}"

    def fetch_identity(self, code: str, code_verifier: str) -> ExternalIdentity:
        self.received = (code, code_verifier)
        if self.fail:
            raise OAuthError("token endpoint returned 400")
        return self.identity


@pytest.fixture
def provider(client):
    from app.main import app

    fake = FakeProvider()
    app.dependency_overrides[get_google_provider] = lambda: fake
    return fake


def start_login(client) -> str:
    response = client.get("/auth/google/login", follow_redirects=False)
    assert response.status_code == 302
    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


def finish_login(client, state: str, code: str = "auth-code"):
    return client.get("/auth/google/callback", params={"code": code, "state": state})


def test_login_redirects_to_provider_with_state_and_pkce(client, provider):
    response = client.get("/auth/google/login", follow_redirects=False)

    assert response.status_code == 302
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["state"][0] and query["code_challenge"][0]
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{OAUTH_COOKIE}=")
    assert "HttpOnly" in cookie
    assert "samesite=lax" in cookie.lower()


def test_first_login_creates_student_without_password(client, storage, provider):
    response = finish_login(client, start_login(client))

    assert response.status_code == 200
    tokens = response.json()
    me = client.get("/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}).json()
    assert me["email"] == "student@gmail.com"
    assert me["role"] == Role.STUDENT
    assert storage.users[me["id"]].password_hash is None
    assert storage.external_accounts[("google", "google-sub-1")] == me["id"]


def test_pkce_verifier_reaches_provider(client, provider):
    response = client.get("/auth/google/login", follow_redirects=False)
    query = parse_qs(urlparse(response.headers["location"]).query)

    finish_login(client, query["state"][0], code="the-code")

    code, verifier = provider.received
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert code == "the-code"
    assert query["code_challenge"][0] == expected


def test_repeat_login_uses_same_account(client, storage, provider):
    finish_login(client, start_login(client))
    provider.identity = ExternalIdentity("google", "google-sub-1", "renamed@gmail.com", True)

    finish_login(client, start_login(client))

    assert len(storage.users) == 1


def test_verified_email_links_existing_account(client, storage, provider):
    existing = client.post("/users/register", json={"email": "student@gmail.com", "password": "password123"}).json()

    tokens = finish_login(client, start_login(client)).json()

    me = client.get("/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}).json()
    assert me["id"] == existing["user_id"]
    assert len(storage.users) == 1


def test_unverified_email_is_rejected(client, storage, provider):
    client.post("/users/register", json={"email": "victim@gmail.com", "password": "password123"})
    provider.identity = ExternalIdentity("google", "attacker-sub", "victim@gmail.com", False)

    response = finish_login(client, start_login(client))

    assert response.status_code == 401
    assert storage.external_accounts == {}


def test_state_mismatch_is_rejected(client, provider):
    start_login(client)

    assert finish_login(client, "forged-state").status_code == 400
    assert provider.received is None


def test_callback_without_login_cookie_is_rejected(client, provider):
    state = start_login(client)
    client.cookies.clear()

    assert finish_login(client, state).status_code == 400


def test_tampered_cookie_is_rejected(client, provider):
    header, payload, signature = sign_payload({"state": "s", "verifier": "v"}, "oauth_state", timedelta(minutes=5)).split(".")
    forged = f"{header}.{payload}.{signature[::-1]}"
    client.cookies.set(OAUTH_COOKIE, forged, path="/auth/google")

    assert finish_login(client, "s").status_code == 400


def test_access_token_cannot_be_used_as_state_cookie(client, provider):
    client.cookies.set(OAUTH_COOKIE, create_access_token(1), path="/auth/google")

    assert finish_login(client, "s").status_code == 400


def test_user_cancelled_at_provider(client, provider):
    response = client.get("/auth/google/callback", params={"error": "access_denied", "state": start_login(client)})

    assert response.status_code == 401


def test_provider_failure_gives_401(client, provider):
    provider.fail = True

    assert finish_login(client, start_login(client)).status_code == 401


def test_blocked_user_cannot_login_with_google(client, storage, provider):
    finish_login(client, start_login(client))
    next(iter(storage.users.values())).is_blocked = True

    assert finish_login(client, start_login(client)).status_code == 403


def test_google_account_cannot_login_with_empty_password(client, provider):
    finish_login(client, start_login(client))

    response = client.post("/auth/login", json={"email": "student@gmail.com", "password": ""})

    assert response.status_code == 401


def test_not_configured_gives_503(client, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "")

    assert client.get("/auth/google/login", follow_redirects=False).status_code == 503


def test_pkce_pair():
    verifier, challenge = new_pkce_pair()

    assert 43 <= len(verifier) <= 128
    assert challenge == base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def google_with(handler) -> GoogleOAuthProvider:
    return GoogleOAuthProvider(
        "client-id",
        "client-secret",
        "http://localhost:8000/auth/google/callback",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_google_authorization_url():
    url = google_with(lambda r: httpx.Response(500)).authorization_url("st", "ch")

    parsed = urlparse(url)
    query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == GoogleOAuthProvider.AUTHORIZE_URL
    assert query["response_type"] == "code"
    assert query["client_id"] == "client-id"
    assert query["redirect_uri"] == "http://localhost:8000/auth/google/callback"
    assert query["scope"] == "openid email profile"
    assert (query["state"], query["code_challenge"], query["code_challenge_method"]) == ("st", "ch", "S256")
    assert "client-secret" not in url


def test_google_exchanges_code_and_reads_userinfo():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if str(request.url) == GoogleOAuthProvider.TOKEN_URL:
            return httpx.Response(200, json={"access_token": "google-access", "token_type": "Bearer"})
        if str(request.url) == GoogleOAuthProvider.USERINFO_URL:
            assert request.headers["Authorization"] == "Bearer google-access"
            return httpx.Response(200, json={"sub": "1234", "email": "a@gmail.com", "email_verified": True})
        return httpx.Response(404)

    identity = google_with(handler).fetch_identity("the-code", "the-verifier")

    assert identity == ExternalIdentity("google", "1234", "a@gmail.com", True)
    form = parse_qs(calls[0].content.decode())
    assert form["grant_type"] == ["authorization_code"]
    assert form["code"] == ["the-code"]
    assert form["code_verifier"] == ["the-verifier"]
    assert form["client_secret"] == ["client-secret"]


@pytest.mark.parametrize("verified", ["true", None, False])
def test_google_email_verified_must_be_boolean_true(verified):
    def handler(request):
        if str(request.url) == GoogleOAuthProvider.TOKEN_URL:
            return httpx.Response(200, json={"access_token": "t"})
        return httpx.Response(200, json={"sub": "1", "email": "a@gmail.com", "email_verified": verified})

    assert google_with(handler).fetch_identity("c", "v").email_verified is False


@pytest.mark.parametrize(
    "token_response",
    [httpx.Response(400, json={"error": "invalid_grant"}), httpx.Response(200, json={}), httpx.Response(200, text="oops")],
)
def test_google_errors_become_oauth_error(token_response):
    with pytest.raises(OAuthError):
        google_with(lambda request: token_response).fetch_identity("c", "v")


def test_password_user_keeps_password_after_linking(client, storage, provider):
    client.post("/users/register", json={"email": "student@gmail.com", "password": "password123"})

    finish_login(client, start_login(client))

    assert client.post("/auth/login", json={"email": "student@gmail.com", "password": "password123"}).status_code == 200
