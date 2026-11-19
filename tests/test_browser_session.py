from tests.conftest import create_account


def test_refresh_is_httponly_and_not_returned_to_browser_javascript(client, storage):
    create_account(client, storage)
    headers = {'Origin': 'http://localhost:8080'}
    login = client.post('/auth/session/login', json={'email': next(iter(storage.users.values())).email,
                                                   'password': 'password123'}, headers=headers)
    assert login.status_code == 200
    assert 'refresh_token' not in login.json()
    cookie = login.headers['set-cookie']
    assert 'HttpOnly' in cookie and 'SameSite=lax' in cookie
    refresh = client.post('/auth/session/refresh', headers=headers)
    assert refresh.status_code == 200
    assert refresh.json()['access_token'] != login.json()['access_token']
    assert client.post('/auth/session/logout', headers=headers).status_code == 200
    assert client.post('/auth/session/refresh', headers=headers).status_code == 401


def test_session_rejects_cross_origin_and_missing_origin(client):
    for headers in [{}, {'Origin': 'https://evil.example'}]:
        assert client.post('/auth/session/refresh', headers=headers).status_code == 403
