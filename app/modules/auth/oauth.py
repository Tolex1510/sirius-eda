"""
Внешние OAuth2-провайдеры (круг 3: Interface Adapters).
AuthService зависит только от OAuthProvider, HTTP-детали Google спрятаны здесь.
"""
import base64
import hashlib
import secrets
from abc import ABC, abstractmethod
from urllib.parse import urlencode

import httpx

from app.domain.entities import ExternalIdentity


class OAuthError(Exception):
    """Провайдер отказал или ответил не так, как ожидалось."""


def new_pkce_pair() -> tuple[str, str]:
    """PKCE (RFC 7636): verifier остаётся у нас, в URL уходит только его SHA-256."""
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


class OAuthProvider(ABC):
    name: str

    @abstractmethod
    def authorization_url(self, state: str, code_challenge: str) -> str:
        """Адрес страницы входа провайдера, куда перенаправляется браузер."""

    @abstractmethod
    def fetch_identity(self, code: str, code_verifier: str) -> ExternalIdentity:
        """Обменивает code на токен провайдера и возвращает данные пользователя."""


class GoogleOAuthProvider(OAuthProvider):
    name = "google"

    AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
    SCOPES = "openid email profile"

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, http: httpx.Client | None = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.http = http or httpx.Client(timeout=10)

    def authorization_url(self, state: str, code_challenge: str) -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.SCOPES,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
        return f"{self.AUTHORIZE_URL}?{urlencode(params)}"

    def fetch_identity(self, code: str, code_verifier: str) -> ExternalIdentity:
        try:
            token_response = self.http.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "code_verifier": code_verifier,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": self.redirect_uri,
                },
            )
            token_response.raise_for_status()
            access_token = token_response.json()["access_token"]

            # Данные берутся с userinfo по TLS, а не из id_token: так не нужно
            # самостоятельно проверять подпись id_token ключами Google.
            userinfo_response = self.http.get(
                self.USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            userinfo_response.raise_for_status()
            info = userinfo_response.json()
            return ExternalIdentity(
                provider=self.name,
                subject=str(info["sub"]),
                email=info.get("email"),
                email_verified=info.get("email_verified") is True,
            )
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise OAuthError(str(e)) from e
