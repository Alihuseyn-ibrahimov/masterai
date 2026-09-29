"""Qapalı qeydiyyat — spec 2026-09-29 §4.1.

Qeydiyyat yalnız kurs kodu (tələbə) və ya sahibin birdəfəlik dəvəti
(müəllim) ilə. Səhv, bağlı və ya dolu kurs haqqında cavablar kənar
adama heç nə öyrətməməlidir; kod təxmini IP üzrə limitlənir, amma eyni
Wi-Fi-dan qeydiyyatdan keçən sinif bloklanmır.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server.app import app, get_register_rate_limiter, get_token_secret, get_user_store
from server.course_store import DEFAULT_COURSE_ID
from server.rate_limit import RateLimiter
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"
_GENERIC_404 = "Kurs kodu tapılmadı"


@pytest.fixture
def env():
    users = UserStore(":memory:")
    limiter = RateLimiter(max_attempts=5, window_seconds=60)
    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_token_secret] = lambda: _SECRET
    app.dependency_overrides[get_register_rate_limiter] = lambda: limiter
    courses = users.courses
    open_course = courses.create("English", "english", trial_days=30, seat_limit=2)
    expired = courses.create("Bitmiş", "english", trial_days=-1, seat_limit=30)
    suspended = courses.create("Dayandırılmış", "english", trial_days=30, seat_limit=30)
    courses.set_status(suspended["id"], "suspended")
    yield {
        "client": TestClient(app), "users": users, "courses": courses,
        "open": open_course, "expired": expired, "suspended": suspended,
    }
    app.dependency_overrides.clear()


def _register(client, email="a@x.az", *, code=None, invite=None, ip=None):
    body = {"email": email, "password": "Parol1234", "display_name": "Ad"}
    if code is not None:
        body["course_code"] = code
    if invite is not None:
        body["invite_token"] = invite
    headers = {"X-Real-IP": ip} if ip else {}
    return client.post("/auth/register", json=body, headers=headers)


class TestCourseCode:
    def test_valid_code_joins_course_as_student(self, env):
        r = _register(env["client"], code=env["open"]["join_code"])
        assert r.status_code == 201
        user = env["users"].get_by_email("a@x.az")
        assert user["course_id"] == env["open"]["id"]
        assert r.json()["user"]["is_teacher"] is False

    def test_code_is_normalized(self, env):
        code = env["open"]["join_code"]
        r = _register(env["client"], code=f" {code[:3].lower()}-{code[3:].lower()} ")
        assert r.status_code == 201

    def test_default_course_code_works(self, env):
        code = env["courses"].get(DEFAULT_COURSE_ID)["join_code"]
        assert _register(env["client"], code=code).status_code == 201

    def test_missing_code_and_invite_rejected(self, env):
        assert _register(env["client"]).status_code == 422
        assert env["users"].get_by_email("a@x.az") is None

    def test_both_code_and_invite_rejected(self, env):
        r = _register(env["client"], code=env["open"]["join_code"], invite="x")
        assert r.status_code == 422

    @pytest.mark.parametrize("which", ["wrong", "expired", "suspended"])
    def test_wrong_or_closed_code_same_404(self, env, which):
        """Bağlı kursun kodu «yanlış kod» ilə EYNİ cavabı alır — kənar
        adam kursun mövcudluğunu və vəziyyətini öyrənə bilməz."""
        code = "ZZZZZZ" if which == "wrong" else env[which]["join_code"]
        r = _register(env["client"], code=code)
        assert r.status_code == 404
        assert r.json()["detail"] == _GENERIC_404
        assert env["users"].get_by_email("a@x.az") is None

    def test_full_course_409(self, env):
        code = env["open"]["join_code"]
        assert _register(env["client"], "a@x.az", code=code).status_code == 201
        assert _register(env["client"], "b@x.az", code=code).status_code == 201
        r = _register(env["client"], "c@x.az", code=code)
        assert r.status_code == 409
        assert "yer" in r.json()["detail"].lower()

    def test_duplicate_email_checked_after_code(self, env):
        """Kod SƏHVdirsə e-poçtun mövcudluğu açılmır (404, 409 yox)."""
        code = env["open"]["join_code"]
        _register(env["client"], "a@x.az", code=code)
        assert _register(env["client"], "a@x.az", code="ZZZZZZ").status_code == 404
        assert _register(env["client"], "a@x.az", code=code).status_code == 409

    def test_response_does_not_leak_join_code(self, env):
        r = _register(env["client"], code=env["open"]["join_code"])
        assert env["open"]["join_code"] not in r.text


class TestTeacherInvite:
    def test_invite_registers_teacher(self, env):
        token = env["courses"].create_teacher_invite(env["open"]["id"], created_by=1)
        r = _register(env["client"], "t@x.az", invite=token)
        assert r.status_code == 201
        assert r.json()["user"]["is_teacher"] is True
        assert env["users"].get_by_email("t@x.az")["course_id"] == env["open"]["id"]

    def test_used_invite_404(self, env):
        token = env["courses"].create_teacher_invite(env["open"]["id"], created_by=1)
        _register(env["client"], "t@x.az", invite=token)
        r = _register(env["client"], "t2@x.az", invite=token)
        assert r.status_code == 404

    def test_unknown_invite_404(self, env):
        assert _register(env["client"], invite="uydurma-token").status_code == 404

    def test_invite_to_closed_course_404(self, env):
        token = env["courses"].create_teacher_invite(env["suspended"]["id"], created_by=1)
        assert _register(env["client"], "t@x.az", invite=token).status_code == 404


class TestRateLimit:
    def test_wrong_codes_block_ip_even_for_correct_code(self, env):
        for _ in range(5):
            assert _register(env["client"], code="ZZZZZZ", ip="1.1.1.1").status_code == 404
        r = _register(env["client"], code=env["open"]["join_code"], ip="1.1.1.1")
        assert r.status_code == 429

    def test_other_ip_not_blocked(self, env):
        for _ in range(5):
            _register(env["client"], code="ZZZZZZ", ip="1.1.1.1")
        r = _register(env["client"], code=env["open"]["join_code"], ip="2.2.2.2")
        assert r.status_code == 201

    def test_successful_registrations_do_not_count(self, env):
        """Bütün sinif eyni Wi-Fi-dan (bir IP) qeydiyyatdan keçir."""
        code = env["courses"].get(DEFAULT_COURSE_ID)["join_code"]
        for i in range(12):
            assert _register(env["client"], f"s{i}@x.az", code=code, ip="1.1.1.1").status_code == 201

    def test_wrong_invites_also_count(self, env):
        for _ in range(5):
            _register(env["client"], invite="uydurma", ip="1.1.1.1")
        r = _register(env["client"], code=env["open"]["join_code"], ip="1.1.1.1")
        assert r.status_code == 429
