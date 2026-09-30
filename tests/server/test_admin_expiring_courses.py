"""Bitmə xəbərdarlığı — spec 2026-09-29 §2.

n8n-in gündəlik workflow-u `/admin/stats`-ı çağırır. Cavabda:
  - `expiring_courses`: açıq, müddətli və bitməyə ≤5 gün qalan kurslar
  - `expired_courses`: müddəti keçib BAĞLANMIŞ kurslar (ödəniş gözlənilir)
Müddətsiz (owner) və əl ilə dayandırılmış kurslar bu siyahılara DÜŞMÜR —
dayandırmanı sahib özü edib, xəbərdarlıq mənasızdır.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from server.app import (
    app,
    get_friendship_store,
    get_question_store,
    get_quiz_session_store,
    get_user_store,
)
from server.friendship_store import FriendshipStore
from server.question_store import QuestionStore
from server.quiz_session_store import QuizSessionStore
from server.user_store import UserStore


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    users = UserStore(":memory:")
    app.dependency_overrides[get_user_store] = lambda: users
    # Sayğac store-ları da yaddaşda — əks halda iş qovluğundakı real .db oxunur.
    questions, sessions, friendships = (
        QuestionStore(":memory:"), QuizSessionStore(":memory:"), FriendshipStore(":memory:"))
    app.dependency_overrides[get_question_store] = lambda: questions
    app.dependency_overrides[get_quiz_session_store] = lambda: sessions
    app.dependency_overrides[get_friendship_store] = lambda: friendships
    yield {"client": TestClient(app), "courses": users.courses}
    app.dependency_overrides.clear()


def _stats(env):
    r = env["client"].get("/admin/stats", headers={"X-Admin-Key": "test-admin-key"})
    assert r.status_code == 200
    return r.json()


def test_trial_ending_within_five_days_listed(env):
    env["courses"].create("Bitir", "english", trial_days=5, seat_limit=10)
    env["courses"].create("Uzaq", "english", trial_days=6, seat_limit=10)
    body = _stats(env)
    assert [(c["name"], c["days_left"]) for c in body["expiring_courses"]] == [("Bitir", 5)]
    assert body["expiring_courses"][0]["status"] == "trial"
    assert body["expiring_courses"][0]["ends_at"]


def test_paid_course_ending_soon_listed(env):
    course = env["courses"].create("Ödənişli", "english", trial_days=1, seat_limit=10)
    env["courses"].set_paid_until(course["id"], datetime.now(timezone.utc) + timedelta(days=2))
    names = {c["name"]: c["status"] for c in _stats(env)["expiring_courses"]}
    assert names == {"Ödənişli": "active"}


def test_expired_course_listed_separately(env):
    env["courses"].create("Bitib", "english", trial_days=-3, seat_limit=10)
    body = _stats(env)
    assert body["expiring_courses"] == []
    assert [c["name"] for c in body["expired_courses"]] == ["Bitib"]


def test_owner_and_suspended_excluded(env):
    suspended = env["courses"].create("Dayandırılıb", "english", trial_days=2, seat_limit=10)
    env["courses"].set_status(suspended["id"], "suspended")
    body = _stats(env)
    names = [c["name"] for c in body["expiring_courses"] + body["expired_courses"]]
    assert names == []  # kurs #1 (owner) və dayandırılmış siyahıda yoxdur


def test_soonest_first(env):
    env["courses"].create("Üç", "english", trial_days=3, seat_limit=10)
    env["courses"].create("Bir", "english", trial_days=1, seat_limit=10)
    assert [c["name"] for c in _stats(env)["expiring_courses"]] == ["Bir", "Üç"]


def test_requires_admin_key(env):
    assert env["client"].get("/admin/stats").status_code == 403


def test_threshold_matches_teacher_banner():
    """Sahibin Telegram xəbərdarlığı və müəllimin banneri EYNİ gündə
    başlamalıdır — biri dəyişib o biri unudulmasın."""
    import re
    from pathlib import Path

    from server.app import EXPIRY_WARNING_DAYS

    js = (Path(__file__).resolve().parents[2] / "web/assets/js/license.js").read_text(encoding="utf-8")
    match = re.search(r"EXPIRY_WARNING_DAYS = (\d+);", js)
    assert match and int(match.group(1)) == EXPIRY_WARNING_DAYS
