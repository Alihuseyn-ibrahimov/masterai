import pytest
from fastapi.testclient import TestClient

from server.app import app, get_chat_store, get_friendship_store, get_token_secret, get_user_store
from server.chat_store import ChatStore
from server.friendship_store import FriendshipStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


@pytest.fixture
def client():
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    friendships = FriendshipStore(":memory:")
    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_chat_store] = lambda: chats
    app.dependency_overrides[get_friendship_store] = lambda: friendships
    app.dependency_overrides[get_token_secret] = lambda: _SECRET
    yield TestClient(app)
    app.dependency_overrides.clear()



def _default_course_code() -> str:
    """Qeydiyyat qapalıdır (kurs kodu məcburi) — bu testlər mövcud
    kurs #1-ə qeydiyyatdan keçir. Store testin override-ındadır."""
    return app.dependency_overrides[get_user_store]().courses.get(1)["join_code"]

def _register(client, email="ali@example.com", password="Parol1234", display_name="Əli"):
    r = client.post(
        "/auth/register",
        json={"email": email, "password": password, "display_name": display_name,
              "course_code": _default_course_code()},
    )
    return r.json()


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _befriend(client, a, b) -> None:
    """İki istifadəçini real dostluq endpoint-ləri ilə dost edir (sorğu+qəbul)."""
    req = client.post(
        "/friends/requests",
        json={"addressee_user_id": b["user"]["id"]},
        headers=_auth_headers(a["token"]),
    ).json()
    client.post(f"/friends/requests/{req['id']}/accept", headers=_auth_headers(b["token"]))


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
        _befriend(client, ali, vali)

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

    def test_non_friends_cannot_create_direct_chat(self, client):
        ali = _register(client, email="ali@example.com")
        vali = _register(client, email="vali@example.com")

        r = client.post(
            "/chats",
            json={"kind": "direct", "peer_user_id": vali["user"]["id"]},
            headers=_auth_headers(ali["token"]),
        )
        assert r.status_code == 403

    def test_pending_request_not_enough_to_create_chat(self, client):
        ali = _register(client, email="ali@example.com")
        vali = _register(client, email="vali@example.com")
        client.post(
            "/friends/requests",
            json={"addressee_user_id": vali["user"]["id"]},
            headers=_auth_headers(ali["token"]),
        )

        r = client.post(
            "/chats",
            json={"kind": "direct", "peer_user_id": vali["user"]["id"]},
            headers=_auth_headers(ali["token"]),
        )
        assert r.status_code == 403


# `TestJoinGroupChat` BURADAN SİLİNDİ (2026-09-11): `POST /chats/{id}/join`
# artıq yoxdur — çat ID-ləri ARDICIL olduğu üçün həmin endpoint hər qrup
# çatına sərbəst giriş verirdi. Yerini tutan kod + təsdiq axınının
# testləri: `tests/server/test_chat_join_requests_endpoints.py`.
