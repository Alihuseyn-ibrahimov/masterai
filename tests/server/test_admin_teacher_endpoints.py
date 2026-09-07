import pytest
from fastapi.testclient import TestClient

from server.app import app, get_token_secret, get_user_store
from server.auth import create_token
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


@pytest.fixture
def env():
    users = UserStore(":memory:")
    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_token_secret] = lambda: _SECRET

    client = TestClient(app)
    admin = users.create("admin@masternr1.az", "hash", "Admin")
    users.set_admin(admin["id"], True)
    admin = users.get_by_id(admin["id"])
    plain = users.create("aygun@masternr1.az", "hash", "Aygün")

    yield {"client": client, "users": users, "admin": admin, "plain": plain}
    app.dependency_overrides.clear()


def _auth(user) -> dict:
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


class TestSetTeacherRole:
    def test_requires_auth(self, env):
        r = env["client"].post("/admin/teachers", json={"email": "aygun@masternr1.az", "is_teacher": True})
        assert r.status_code == 401

    def test_non_admin_gets_403(self, env):
        r = env["client"].post(
            "/admin/teachers",
            json={"email": "aygun@masternr1.az", "is_teacher": True},
            headers=_auth(env["plain"]),
        )
        assert r.status_code == 403

    def test_unknown_email_returns_404(self, env):
        r = env["client"].post(
            "/admin/teachers",
            json={"email": "yoxdur@masternr1.az", "is_teacher": True},
            headers=_auth(env["admin"]),
        )
        assert r.status_code == 404

    def test_admin_grants_teacher_role(self, env):
        r = env["client"].post(
            "/admin/teachers",
            json={"email": "aygun@masternr1.az", "is_teacher": True},
            headers=_auth(env["admin"]),
        )
        assert r.status_code == 200
        assert r.json()["is_teacher"] is True
        assert env["users"].get_by_id(env["plain"]["id"])["is_teacher"] == 1

    def test_admin_revokes_teacher_role(self, env):
        env["users"].set_teacher(env["plain"]["id"], True)
        r = env["client"].post(
            "/admin/teachers",
            json={"email": "aygun@masternr1.az", "is_teacher": False},
            headers=_auth(env["admin"]),
        )
        assert r.status_code == 200
        assert r.json()["is_teacher"] is False

    def test_email_lookup_is_case_insensitive(self, env):
        r = env["client"].post(
            "/admin/teachers",
            json={"email": "AYGUN@Masternr1.az", "is_teacher": True},
            headers=_auth(env["admin"]),
        )
        assert r.status_code == 200
        assert r.json()["is_teacher"] is True
