import pytest
from fastapi.testclient import TestClient

from server.app import app, get_chat_store, get_token_secret, get_user_store
from server.chat_store import ChatStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


@pytest.fixture
def client():
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_chat_store] = lambda: chats
    app.dependency_overrides[get_token_secret] = lambda: _SECRET
    yield TestClient(app)
    app.dependency_overrides.clear()


def _register(client, email="ali@example.com", password="Parol1234", display_name="Əli"):
    r = client.post(
        "/auth/register",
        json={"email": email, "password": password, "display_name": display_name},
    )
    return r.json()


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestCreateGroupChat:
    def test_creates_chat_and_adds_creator_as_member(self, client):
        auth = _register(client)
        r = client.post(
            "/chats",
            json={"kind": "group", "name": "Dövlət qulluğu qrupu"},
            headers=_auth_headers(auth["token"]),
        )
        assert r.status_code == 201
        body = r.json()
        assert body["kind"] == "group"
        assert body["name"] == "Dövlət qulluğu qrupu"
        assert body["created_by"] == auth["user"]["id"]

        listed = client.get("/chats", headers=_auth_headers(auth["token"])).json()
        assert [c["id"] for c in listed] == [body["id"]]

    def test_missing_name_returns_422(self, client):
        auth = _register(client)
        r = client.post("/chats", json={"kind": "group"}, headers=_auth_headers(auth["token"]))
        assert r.status_code == 422

    def test_requires_auth(self, client):
        r = client.post("/chats", json={"kind": "group", "name": "Qrup"})
        assert r.status_code == 401


class TestCreateDirectChat:
    def test_creates_chat_with_both_members(self, client):
        ali = _register(client, email="ali@example.com")
        vali = _register(client, email="vali@example.com")

        r = client.post(
            "/chats",
            json={"kind": "direct", "peer_user_id": vali["user"]["id"]},
            headers=_auth_headers(ali["token"]),
        )
        assert r.status_code == 201
        chat_id = r.json()["id"]

        ali_chats = client.get("/chats", headers=_auth_headers(ali["token"])).json()
        vali_chats = client.get("/chats", headers=_auth_headers(vali["token"])).json()
        assert [c["id"] for c in ali_chats] == [chat_id]
        assert [c["id"] for c in vali_chats] == [chat_id]

    def test_missing_peer_user_id_returns_422(self, client):
        auth = _register(client)
        r = client.post("/chats", json={"kind": "direct"}, headers=_auth_headers(auth["token"]))
        assert r.status_code == 422

    def test_unknown_peer_user_id_returns_404(self, client):
        auth = _register(client)
        r = client.post(
            "/chats",
            json={"kind": "direct", "peer_user_id": 9999},
            headers=_auth_headers(auth["token"]),
        )
        assert r.status_code == 404


class TestJoinGroupChat:
    def test_second_user_can_join(self, client):
        ali = _register(client, email="ali@example.com")
        vali = _register(client, email="vali@example.com")
        chat_id = client.post(
            "/chats", json={"kind": "group", "name": "Qrup"}, headers=_auth_headers(ali["token"])
        ).json()["id"]

        r = client.post(f"/chats/{chat_id}/join", headers=_auth_headers(vali["token"]))
        assert r.status_code == 200

        vali_chats = client.get("/chats", headers=_auth_headers(vali["token"])).json()
        assert [c["id"] for c in vali_chats] == [chat_id]

    def test_joining_direct_chat_returns_400(self, client):
        ali = _register(client, email="ali@example.com")
        vali = _register(client, email="vali@example.com")
        third = _register(client, email="uc@example.com")
        chat_id = client.post(
            "/chats",
            json={"kind": "direct", "peer_user_id": vali["user"]["id"]},
            headers=_auth_headers(ali["token"]),
        ).json()["id"]

        r = client.post(f"/chats/{chat_id}/join", headers=_auth_headers(third["token"]))
        assert r.status_code == 400

    def test_unknown_chat_returns_404(self, client):
        auth = _register(client)
        r = client.post("/chats/9999/join", headers=_auth_headers(auth["token"]))
        assert r.status_code == 404
