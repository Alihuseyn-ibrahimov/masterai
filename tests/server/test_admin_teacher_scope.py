"""`is_admin`-in «müəllim et» hüququ yalnız ÖZ KURSUNA şamil olunur.

Əks halda bir kursun admini başqa kursun tələbəsini müəllim edə, ya da
bütün platformanın müəllim siyahısını (e-poçtlarla) görə bilərdi.
Başqa kursun istifadəçisi «tapılmadı» ilə EYNİ cavabı alır.
"""

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
    a = users.courses.create("A", "english", trial_days=30, seat_limit=30)
    b = users.courses.create("B", "english", trial_days=30, seat_limit=30)
    admin = users.create("admin@a.az", "h", "Admin", course_id=a["id"])
    users.set_admin(admin["id"], True)
    users.set_teacher(admin["id"], True)
    same = users.create("same@a.az", "h", "Eyni kurs", course_id=a["id"])
    other = users.create("other@b.az", "h", "Başqa kurs", course_id=b["id"])
    other_teacher = users.create("teacher@b.az", "h", "B müəllimi", course_id=b["id"])
    users.set_teacher(other_teacher["id"], True)
    yield {"client": TestClient(app), "users": users, "admin": users.get_by_id(admin["id"]),
           "same": same, "other": other}
    app.dependency_overrides.clear()


def _auth(user):
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


def test_admin_promotes_user_in_own_course(env):
    r = env["client"].post("/admin/teachers", json={"email": "same@a.az", "is_teacher": True},
                           headers=_auth(env["admin"]))
    assert r.status_code == 200
    assert env["users"].get_by_email("same@a.az")["is_teacher"] == 1


def test_admin_cannot_touch_other_course(env):
    r = env["client"].post("/admin/teachers", json={"email": "other@b.az", "is_teacher": True},
                           headers=_auth(env["admin"]))
    missing = env["client"].post("/admin/teachers", json={"email": "yoxdur@x.az", "is_teacher": True},
                                 headers=_auth(env["admin"]))
    assert r.status_code == 404
    assert r.json() == missing.json()
    assert env["users"].get_by_email("other@b.az")["is_teacher"] == 0


def test_teacher_list_is_course_scoped(env):
    r = env["client"].get("/admin/teachers", headers=_auth(env["admin"]))
    emails = {t["email"] for t in r.json()}
    assert emails == {"admin@a.az"}
