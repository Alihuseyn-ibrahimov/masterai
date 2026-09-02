import pytest
from fastapi.testclient import TestClient

from server.app import app, get_friendship_store, get_token_secret, get_user_store
from server.auth import create_token
from server.friendship_store import FriendshipStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


@pytest.fixture
def env():
    users = UserStore(":memory:")
    friendships = FriendshipStore(":memory:")

    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_friendship_store] = lambda: friendships
    app.dependency_overrides[get_token_secret] = lambda: _SECRET

    client = TestClient(app)

    ali = users.create("ali@example.com", "hash", "Əli")
    vali = users.create("vali@example.com", "hash", "Vəli")
    zaur = users.create("zaur@example.com", "hash", "Zaur")

    yield {
        "client": client,
        "friendships": friendships,
        "ali": ali,
        "vali": vali,
        "zaur": zaur,
    }
    app.dependency_overrides.clear()


def _auth(user) -> dict:
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


class TestSendFriendRequest:
    def test_by_email_creates_pending(self, env):
        r = env["client"].post(
            "/friends/requests",
            json={"addressee_email": env["vali"]["email"]},
            headers=_auth(env["ali"]),
        )
        assert r.status_code == 201
        body = r.json()
        assert body["requester_id"] == env["ali"]["id"]
        assert body["addressee_id"] == env["vali"]["id"]
        assert body["status"] == "pending"

    def test_by_user_id_creates_pending(self, env):
        r = env["client"].post(
            "/friends/requests",
            json={"addressee_user_id": env["vali"]["id"]},
            headers=_auth(env["ali"]),
        )
        assert r.status_code == 201
        assert r.json()["status"] == "pending"

    def test_requires_auth(self, env):
        r = env["client"].post("/friends/requests", json={"addressee_user_id": env["vali"]["id"]})
        assert r.status_code == 401

    def test_missing_both_fields_returns_422(self, env):
        r = env["client"].post("/friends/requests", json={}, headers=_auth(env["ali"]))
        assert r.status_code == 422

    def test_both_fields_returns_422(self, env):
        r = env["client"].post(
            "/friends/requests",
            json={"addressee_email": env["vali"]["email"], "addressee_user_id": env["vali"]["id"]},
            headers=_auth(env["ali"]),
        )
        assert r.status_code == 422

    def test_unknown_email_returns_404(self, env):
        r = env["client"].post(
            "/friends/requests",
            json={"addressee_email": "yoxdur@example.com"},
            headers=_auth(env["ali"]),
        )
        assert r.status_code == 404

    def test_unknown_user_id_returns_404(self, env):
        r = env["client"].post(
            "/friends/requests", json={"addressee_user_id": 9999}, headers=_auth(env["ali"])
        )
        assert r.status_code == 404

    def test_self_request_returns_400(self, env):
        r = env["client"].post(
            "/friends/requests", json={"addressee_user_id": env["ali"]["id"]}, headers=_auth(env["ali"])
        )
        assert r.status_code == 400

    def test_duplicate_pending_returns_409(self, env):
        env["client"].post(
            "/friends/requests", json={"addressee_user_id": env["vali"]["id"]}, headers=_auth(env["ali"])
        )
        r = env["client"].post(
            "/friends/requests", json={"addressee_user_id": env["vali"]["id"]}, headers=_auth(env["ali"])
        )
        assert r.status_code == 409

    def test_already_friends_returns_409(self, env):
        friendships = env["friendships"]
        created = friendships.create(env["ali"]["id"], env["vali"]["id"])
        friendships.update_status(created["id"], "accepted")

        r = env["client"].post(
            "/friends/requests", json={"addressee_user_id": env["vali"]["id"]}, headers=_auth(env["ali"])
        )
        assert r.status_code == 409


class TestListFriendRequests:
    def test_requires_auth(self, env):
        r = env["client"].get("/friends/requests")
        assert r.status_code == 401

    def test_lists_pending_incoming_and_outgoing(self, env):
        env["friendships"].create(env["ali"]["id"], env["vali"]["id"])  # ali -> vali
        env["friendships"].create(env["zaur"]["id"], env["ali"]["id"])  # zaur -> ali

        r = env["client"].get("/friends/requests", headers=_auth(env["ali"]))
        assert r.status_code == 200
        pairs = {(f["requester_id"], f["addressee_id"]) for f in r.json()}
        assert pairs == {(env["ali"]["id"], env["vali"]["id"]), (env["zaur"]["id"], env["ali"]["id"])}

    def test_excludes_non_pending(self, env):
        created = env["friendships"].create(env["ali"]["id"], env["vali"]["id"])
        env["friendships"].update_status(created["id"], "accepted")

        r = env["client"].get("/friends/requests", headers=_auth(env["ali"]))
        assert r.json() == []


class TestAcceptFriendRequest:
    def test_addressee_can_accept(self, env):
        created = env["friendships"].create(env["ali"]["id"], env["vali"]["id"])
        r = env["client"].post(f"/friends/requests/{created['id']}/accept", headers=_auth(env["vali"]))
        assert r.status_code == 200
        assert r.json()["status"] == "accepted"

    def test_requester_cannot_accept(self, env):
        created = env["friendships"].create(env["ali"]["id"], env["vali"]["id"])
        r = env["client"].post(f"/friends/requests/{created['id']}/accept", headers=_auth(env["ali"]))
        assert r.status_code == 403

    def test_unrelated_user_cannot_accept(self, env):
        created = env["friendships"].create(env["ali"]["id"], env["vali"]["id"])
        r = env["client"].post(f"/friends/requests/{created['id']}/accept", headers=_auth(env["zaur"]))
        assert r.status_code == 403

    def test_unknown_id_returns_404(self, env):
        r = env["client"].post("/friends/requests/9999/accept", headers=_auth(env["vali"]))
        assert r.status_code == 404

    def test_non_pending_returns_409(self, env):
        created = env["friendships"].create(env["ali"]["id"], env["vali"]["id"])
        env["client"].post(f"/friends/requests/{created['id']}/accept", headers=_auth(env["vali"]))
        r = env["client"].post(f"/friends/requests/{created['id']}/accept", headers=_auth(env["vali"]))
        assert r.status_code == 409

    def test_requires_auth(self, env):
        created = env["friendships"].create(env["ali"]["id"], env["vali"]["id"])
        r = env["client"].post(f"/friends/requests/{created['id']}/accept")
        assert r.status_code == 401


class TestDeclineFriendRequest:
    def test_addressee_can_decline(self, env):
        created = env["friendships"].create(env["ali"]["id"], env["vali"]["id"])
        r = env["client"].post(f"/friends/requests/{created['id']}/decline", headers=_auth(env["vali"]))
        assert r.status_code == 200
        assert r.json()["status"] == "declined"

    def test_requester_cannot_decline(self, env):
        created = env["friendships"].create(env["ali"]["id"], env["vali"]["id"])
        r = env["client"].post(f"/friends/requests/{created['id']}/decline", headers=_auth(env["ali"]))
        assert r.status_code == 403


class TestCancelFriendRequest:
    def test_requester_can_cancel(self, env):
        created = env["friendships"].create(env["ali"]["id"], env["vali"]["id"])
        r = env["client"].post(f"/friends/requests/{created['id']}/cancel", headers=_auth(env["ali"]))
        assert r.status_code == 200
        assert r.json()["status"] == "cancelled"

    def test_addressee_cannot_cancel(self, env):
        created = env["friendships"].create(env["ali"]["id"], env["vali"]["id"])
        r = env["client"].post(f"/friends/requests/{created['id']}/cancel", headers=_auth(env["vali"]))
        assert r.status_code == 403

    def test_non_pending_returns_409(self, env):
        created = env["friendships"].create(env["ali"]["id"], env["vali"]["id"])
        env["client"].post(f"/friends/requests/{created['id']}/cancel", headers=_auth(env["ali"]))
        r = env["client"].post(f"/friends/requests/{created['id']}/cancel", headers=_auth(env["ali"]))
        assert r.status_code == 409


class TestListFriends:
    def test_requires_auth(self, env):
        r = env["client"].get("/friends")
        assert r.status_code == 401

    def test_lists_accepted_only(self, env):
        accepted = env["friendships"].create(env["ali"]["id"], env["vali"]["id"])
        env["friendships"].update_status(accepted["id"], "accepted")
        env["friendships"].create(env["zaur"]["id"], env["ali"]["id"])  # hələ pending

        r = env["client"].get("/friends", headers=_auth(env["ali"]))
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["status"] == "accepted"


class TestUnfriend:
    def test_requester_can_unfriend(self, env):
        created = env["friendships"].create(env["ali"]["id"], env["vali"]["id"])
        env["friendships"].update_status(created["id"], "accepted")

        r = env["client"].post(f"/friends/{created['id']}/unfriend", headers=_auth(env["ali"]))
        assert r.status_code == 200
        assert r.json()["status"] == "unfriended"

    def test_addressee_can_unfriend(self, env):
        created = env["friendships"].create(env["ali"]["id"], env["vali"]["id"])
        env["friendships"].update_status(created["id"], "accepted")

        r = env["client"].post(f"/friends/{created['id']}/unfriend", headers=_auth(env["vali"]))
        assert r.status_code == 200

    def test_unrelated_user_returns_403(self, env):
        created = env["friendships"].create(env["ali"]["id"], env["vali"]["id"])
        env["friendships"].update_status(created["id"], "accepted")

        r = env["client"].post(f"/friends/{created['id']}/unfriend", headers=_auth(env["zaur"]))
        assert r.status_code == 403

    def test_non_accepted_returns_409(self, env):
        created = env["friendships"].create(env["ali"]["id"], env["vali"]["id"])  # hələ pending
        r = env["client"].post(f"/friends/{created['id']}/unfriend", headers=_auth(env["ali"]))
        assert r.status_code == 409

    def test_unknown_id_returns_404(self, env):
        r = env["client"].post("/friends/9999/unfriend", headers=_auth(env["ali"]))
        assert r.status_code == 404


class TestFullFlow:
    def test_request_accept_appears_in_friends_list(self, env):
        client = env["client"]
        req = client.post(
            "/friends/requests", json={"addressee_user_id": env["vali"]["id"]}, headers=_auth(env["ali"])
        ).json()
        client.post(f"/friends/requests/{req['id']}/accept", headers=_auth(env["vali"]))

        ali_friends = client.get("/friends", headers=_auth(env["ali"])).json()
        vali_friends = client.get("/friends", headers=_auth(env["vali"])).json()
        assert len(ali_friends) == 1
        assert len(vali_friends) == 1
        assert ali_friends[0]["id"] == req["id"]

    def test_decline_then_new_request_from_other_side_allowed(self, env):
        client = env["client"]
        req = client.post(
            "/friends/requests", json={"addressee_user_id": env["vali"]["id"]}, headers=_auth(env["ali"])
        ).json()
        client.post(f"/friends/requests/{req['id']}/decline", headers=_auth(env["vali"]))

        reopened = client.post(
            "/friends/requests", json={"addressee_user_id": env["ali"]["id"]}, headers=_auth(env["vali"])
        )
        assert reopened.status_code == 201
        body = reopened.json()
        assert body["requester_id"] == env["vali"]["id"]
        assert body["status"] == "pending"
