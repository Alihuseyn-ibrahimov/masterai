"""Sinif liderlik lövhəsi — ev tapşırığı + canlı sessiya CƏMİ.

DƏYİŞƏN NƏDİR: lövhə əvvəl YALNIZ ev tapşırığı xallarını sayırdı,
çünki canlı sessiyalar heç bir çata bağlı deyildi (bax Faza 6 dizayn
sənədi). İndi sessiya çata bağlıdır, ona görə hər iki mənbə sayılır.

Spec qərarı: sıralama CƏMİYƏ görədir, amma komponentlər ayrıca
görünür — «hansı sahədə geridəyəm» sualı cavabsız qalmamalıdır.

Müəllim siyahıdan ÇIXARILIR: o, tapşırığı təyin edən tərəfdir, tələbə
ilə yarışmır.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server.app import (
    app,
    get_chat_store,
    get_homework_store,
    get_live_session_store,
    get_token_secret,
    get_user_store,
)
from server.auth import create_token
from server.chat_store import ChatStore
from server.homework_store import HomeworkStore
from server.live_session_store import LiveSessionStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


@pytest.fixture
def env():
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    homework = HomeworkStore(":memory:")
    live = LiveSessionStore(":memory:")

    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_chat_store] = lambda: chats
    app.dependency_overrides[get_homework_store] = lambda: homework
    app.dependency_overrides[get_live_session_store] = lambda: live
    app.dependency_overrides[get_token_secret] = lambda: _SECRET

    def _user(email, name, *, teacher=False):
        row = users.create(email, "hash", name)
        if teacher:
            users.set_teacher(row["id"], True)
        return users.get_by_id(row["id"])

    teacher = _user("m@masternr1.az", "Müəllim", teacher=True)
    nermin = _user("n@masternr1.az", "Nərmin")
    resad = _user("r@masternr1.az", "Rəşad")
    kenar = _user("k@masternr1.az", "Kənar")

    chat = chats.create(kind="group", created_by=teacher["id"], name="11-A")
    for member in (teacher, nermin, resad):
        chats.add_member(chat["id"], member["id"])

    yield {
        "client": TestClient(app), "users": users, "chats": chats,
        "homework": homework, "live": live, "chat": chat,
        "teacher": teacher, "nermin": nermin, "resad": resad, "kenar": kenar,
    }
    app.dependency_overrides.clear()


def _auth(user: dict) -> dict:
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


def _live_points(env, user, count: int) -> None:
    """Tələbəyə canlı sessiyada `count` düzgün cavab yazır."""
    session = env["live"].create_session(
        question_set_id=1, chat_id=env["chat"]["id"], created_by=env["teacher"]["id"]
    )
    p = env["live"].add_participant(session["id"], user["display_name"], user_id=user["id"])
    for index in range(count):
        env["live"].record_answer(session["id"], p["id"], index, 0, True)


def _homework_points(env, user, score: int, total_questions: int = 5) -> None:
    """Tələbəyə ev tapşırığında `score` düzgün cavab yazır —
    `test_badge_endpoints.py`-dakı eyni naxış (real store metodları ilə,
    DB-yə birbaşa yazmadan)."""
    assignment = env["homework"].create_assignment(
        env["chat"]["id"], 1, "2026-12-31", created_by=env["teacher"]["id"]
    )
    attempt = env["homework"].get_or_create_attempt(assignment["id"], student_id=user["id"])
    for index in range(score):
        env["homework"].answer(
            attempt["id"], index, chosen_index=0, is_correct=True,
            total_questions=total_questions,
        )
    for index in range(score, total_questions):
        env["homework"].answer(
            attempt["id"], index, chosen_index=1, is_correct=False,
            total_questions=total_questions,
        )


def _rows(env, viewer=None):
    viewer = viewer or env["nermin"]
    r = env["client"].get(
        f"/chats/{env['chat']['id']}/leaderboard", headers=_auth(viewer)
    )
    assert r.status_code == 200, r.text
    return r.json()


class TestBothSourcesCount:
    def test_homework_points_are_counted(self, env):
        _homework_points(env, env["nermin"], 3)
        row = next(r for r in _rows(env) if r["user_id"] == env["nermin"]["id"])
        assert row["homework_score"] == 3
        assert row["live_score"] == 0
        assert row["total_score"] == 3

    def test_live_session_points_are_counted(self, env):
        """ƏSAS YENİLİK: əvvəl bu xallar lövhədə ÜMUMİYYƏTLƏ
        görünmürdü."""
        _live_points(env, env["nermin"], 2)
        row = next(r for r in _rows(env) if r["user_id"] == env["nermin"]["id"])
        assert row["live_score"] == 2
        assert row["homework_score"] == 0
        assert row["total_score"] == 2

    def test_the_two_sources_add_up(self, env):
        _homework_points(env, env["nermin"], 3)
        _live_points(env, env["nermin"], 2)
        row = next(r for r in _rows(env) if r["user_id"] == env["nermin"]["id"])
        assert row["total_score"] == 5

    def test_components_stay_visible(self, env):
        """Spec qərarı: sıralama cəmiyədir, amma komponentlər görünür —
        tələbə hansı sahədə geridə qaldığını bilməlidir."""
        _homework_points(env, env["nermin"], 3)
        _live_points(env, env["nermin"], 2)
        row = next(r for r in _rows(env) if r["user_id"] == env["nermin"]["id"])
        assert (row["homework_score"], row["live_score"]) == (3, 2)


class TestRanking:
    def test_sorted_by_the_total_not_by_one_source(self, env):
        """Yalnız ev tapşırığına görə sıralasaydıq, canlı sessiyada
        güclü tələbə aşağıda qalardı."""
        _homework_points(env, env["nermin"], 1)
        _live_points(env, env["nermin"], 5)   # cəmi 6
        _homework_points(env, env["resad"], 4)  # cəmi 4

        rows = _rows(env)
        assert [r["display_name"] for r in rows] == ["Nərmin", "Rəşad"]
        assert [r["rank"] for r in rows] == [1, 2]

    def test_members_without_any_points_are_still_listed(self, env):
        """Sıfır xallı üzv siyahıdan DÜŞMƏMƏLİDİR — əks halda tələbə
        «mən niyə yoxam?» sualı ilə qalır."""
        _homework_points(env, env["nermin"], 1)
        rows = _rows(env)
        assert {r["display_name"] for r in rows} == {"Nərmin", "Rəşad"}
        zero = next(r for r in rows if r["display_name"] == "Rəşad")
        assert zero["total_score"] == 0


class TestTeacherIsExcluded:
    def test_the_teacher_is_not_in_the_list(self, env):
        """Müəllim tapşırığı TƏYİN EDƏN tərəfdir, tələbə ilə yarışmır."""
        _homework_points(env, env["nermin"], 1)
        assert all(r["user_id"] != env["teacher"]["id"] for r in _rows(env))

    def test_the_teacher_can_still_view_the_board(self, env):
        """Siyahıdan çıxarılmaq BAXMAĞI qadağan etmir."""
        _homework_points(env, env["nermin"], 1)
        rows = _rows(env, viewer=env["teacher"])
        assert [r["display_name"] for r in rows] == ["Nərmin", "Rəşad"]

    def test_teacher_points_do_not_leak_into_the_totals(self, env):
        """Müəllim özü sessiyada iştirak etsə belə (sınaq üçün), onun
        xalı lövhədə görünməməlidir."""
        _live_points(env, env["teacher"], 9)
        _homework_points(env, env["nermin"], 1)
        rows = _rows(env)
        assert all(r["user_id"] != env["teacher"]["id"] for r in rows)
        assert max(r["total_score"] for r in rows) == 1


class TestAccess:
    def test_a_non_member_is_refused(self, env):
        r = env["client"].get(
            f"/chats/{env['chat']['id']}/leaderboard", headers=_auth(env["kenar"])
        )
        assert r.status_code == 403

    def test_unknown_chat_returns_404(self, env):
        r = env["client"].get("/chats/9999/leaderboard", headers=_auth(env["nermin"]))
        assert r.status_code == 404
