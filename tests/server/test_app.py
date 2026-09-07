import pytest
from fastapi.testclient import TestClient

from server.app import app, get_token_secret, get_user_store
from server.auth import verify_token
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


@pytest.fixture
def client():
    store = UserStore(":memory:")
    app.dependency_overrides[get_user_store] = lambda: store
    app.dependency_overrides[get_token_secret] = lambda: _SECRET
    yield TestClient(app)
    app.dependency_overrides.clear()


def _register(client, email="ali@example.com", password="Parol1234", display_name="Əli"):
    return client.post(
        "/auth/register",
        json={"email": email, "password": password, "display_name": display_name},
    )


class TestRegister:
    def test_returns_token_and_user(self, client):
        r = _register(client)
        assert r.status_code == 201
        body = r.json()
        assert body["token"]
        assert body["user"]["email"] == "ali@example.com"
        assert body["user"]["display_name"] == "Əli"

    def test_password_hash_never_returned(self, client):
        r = _register(client)
        assert "password_hash" not in r.json()["user"]

    def test_token_is_valid_and_decodes_to_user_id(self, client):
        body = _register(client).json()
        user_id = verify_token(body["token"], secret=_SECRET)
        assert user_id == body["user"]["id"]

    def test_duplicate_email_409(self, client):
        _register(client)
        assert _register(client).status_code == 409

    def test_duplicate_is_case_insensitive(self, client):
        _register(client, email="ali@example.com")
        assert _register(client, email="ALI@Example.com").status_code == 409

    def test_invalid_email_422(self, client):
        assert _register(client, email="bu-email-deyil").status_code == 422

    def test_short_password_422(self, client):
        assert _register(client, password="123").status_code == 422


class TestLogin:
    def test_correct_credentials_return_token(self, client):
        _register(client, email="ali@example.com", password="Parol1234")
        r = client.post("/auth/login", json={"email": "ali@example.com", "password": "Parol1234"})
        assert r.status_code == 200
        assert r.json()["token"]

    def test_wrong_password_401(self, client):
        _register(client, email="ali@example.com", password="Parol1234")
        r = client.post("/auth/login", json={"email": "ali@example.com", "password": "Səhvdir1"})
        assert r.status_code == 401

    def test_unknown_email_401_same_message_as_wrong_password(self, client):
        _register(client, email="ali@example.com", password="Parol1234")
        wrong_pw = client.post(
            "/auth/login", json={"email": "ali@example.com", "password": "Səhvdir1"}
        )
        unknown_email = client.post(
            "/auth/login", json={"email": "yoxdur@example.com", "password": "Parol1234"}
        )
        assert wrong_pw.status_code == unknown_email.status_code == 401
        assert wrong_pw.json()["detail"] == unknown_email.json()["detail"]


class TestHealth:
    def test_returns_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


class TestCors:
    """Host konsolu (`app/` veb build-i) brauzerdə işlədiyi üçün CORS
    header-ləri lazımdır — bax Faza 4 real testində tapılan "bağlantı
    xətası" bug-ı, `masterai/CLAUDE.md`."""

    def test_allows_any_origin_on_actual_request(self, client):
        r = client.get("/health", headers={"Origin": "http://localhost:62270"})
        assert r.headers["access-control-allow-origin"] == "*"

    def test_preflight_allows_post_with_authorization_header(self, client):
        r = client.options(
            "/live/question-sets",
            headers={
                "Origin": "http://localhost:62270",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        assert r.status_code == 200
        assert r.headers["access-control-allow-origin"] == "*"
