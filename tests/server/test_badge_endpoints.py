import json

import pytest
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion
from server.app import (
    app,
    get_badge_store,
    get_chat_store,
    get_homework_store,
    get_live_session_store,
    get_question_set_store,
    get_token_secret,
    get_user_store,
)
from server.auth import create_token
from server.badge_store import BadgeStore
from server.chat_store import ChatStore
from server.homework_store import HomeworkStore
from server.live_session_store import LiveSessionStore
from server.question_set_store import QuestionSetStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"
_ALL_BADGE_TYPES = {"ilk_addim", "yuz_faiz", "fenn_ustasi", "suretli_eqli", "silsile_5"}


@pytest.fixture
def env():
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    question_sets = QuestionSetStore(":memory:")
    homework = HomeworkStore(":memory:")
    live_sessions = LiveSessionStore(":memory:")
    badges = BadgeStore(":memory:")

    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_chat_store] = lambda: chats
    app.dependency_overrides[get_question_set_store] = lambda: question_sets
    app.dependency_overrides[get_homework_store] = lambda: homework
    app.dependency_overrides[get_live_session_store] = lambda: live_sessions
    app.dependency_overrides[get_badge_store] = lambda: badges
    app.dependency_overrides[get_token_secret] = lambda: _SECRET

    client = TestClient(app)
    teacher = users.create("teacher@masternr1.az", "hash", "Müəllim")
    users.set_teacher(teacher["id"], True)
    teacher = users.get_by_id(teacher["id"])
    student = users.create("tələbə@masternr1.az", "hash", "Tələbə")

    chat = chats.create(kind="group", created_by=teacher["id"], name="Sinif")
    chats.add_member(chat["id"], teacher["id"])
    chats.add_member(chat["id"], student["id"])

    yield {
        "client": client, "users": users, "chats": chats, "question_sets": question_sets,
        "homework": homework, "live_sessions": live_sessions, "badges": badges,
        "teacher": teacher, "student": student, "chat": chat,
    }
    app.dependency_overrides.clear()


def _auth(user) -> dict:
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


def _ready_question_set(env, n_questions=2, subject="mentiq", title="Silloqizmlər"):
    qs = env["question_sets"].create(
        subject=subject, title=title, material_kind="link",
        material_location="https://x.az", created_by=env["teacher"]["id"],
    )
    for i in range(n_questions):
        env["question_sets"].add_question(
            qs["id"],
            MCQQuestion(
                question=f"Sual {i}?", options=["A", "B", "C", "D", "E"],
                correct_index=0, explanation=f"izah {i}",
            ),
        )
    env["question_sets"].mark_ready(qs["id"])
    return qs


def _completed_homework(env, *, student_id, score, total_questions=2, subject="mentiq"):
    qs = _ready_question_set(env, n_questions=total_questions, subject=subject)
    assignment = env["homework"].create_assignment(
        env["chat"]["id"], qs["id"], "2026-09-14", created_by=env["teacher"]["id"]
    )
    attempt = env["homework"].get_or_create_attempt(assignment["id"], student_id=student_id)
    for i in range(score):
        env["homework"].answer(attempt["id"], i, chosen_index=0, is_correct=True, total_questions=total_questions)
    for i in range(score, total_questions):
        env["homework"].answer(attempt["id"], i, chosen_index=1, is_correct=False, total_questions=total_questions)
    return attempt["id"]


def _set_attempt_times(env, attempt_id, *, started_at, completed_at):
    """Testdə vaxta bağlı meyarları (sürətli əqli, silsilə) simulyasiya
    etmək üçün DB-ni birbaşa yeniləyir — real vaxt fərqi test icrası
    zamanı yaratmaq mümkün olmadığı üçün."""
    env["homework"]._conn.execute(
        "UPDATE homework_attempts SET started_at = ?, completed_at = ? WHERE id = ?",
        (started_at, completed_at, attempt_id),
    )
    env["homework"]._conn.commit()


class TestMyBadges:
    def test_requires_auth(self, env):
        assert env["client"].get("/badges/me").status_code == 401

    def test_all_badges_unearned_when_nothing_done(self, env):
        r = env["client"].get("/badges/me", headers=_auth(env["student"]))
        assert r.status_code == 200
        body = r.json()
        assert {b["badge_type"] for b in body} == _ALL_BADGE_TYPES
        assert all(b["earned"] is False and b["earned_at"] is None for b in body)

    def test_ilk_addim_after_one_completed_homework(self, env):
        _completed_homework(env, student_id=env["student"]["id"], score=1)
        r = env["client"].get("/badges/me", headers=_auth(env["student"]))
        badges = {b["badge_type"]: b for b in r.json()}
        assert badges["ilk_addim"]["earned"] is True
        assert badges["ilk_addim"]["earned_at"]

    def test_yuz_faiz_when_perfect_score(self, env):
        _completed_homework(env, student_id=env["student"]["id"], score=2, total_questions=2)
        r = env["client"].get("/badges/me", headers=_auth(env["student"]))
        badges = {b["badge_type"]: b for b in r.json()}
        assert badges["yuz_faiz"]["earned"] is True

    def test_yuz_faiz_not_earned_with_imperfect_score(self, env):
        _completed_homework(env, student_id=env["student"]["id"], score=1, total_questions=2)
        r = env["client"].get("/badges/me", headers=_auth(env["student"]))
        badges = {b["badge_type"]: b for b in r.json()}
        assert badges["yuz_faiz"]["earned"] is False

    def test_fenn_ustasi_after_5_homework_in_same_subject(self, env):
        for _ in range(5):
            _completed_homework(env, student_id=env["student"]["id"], score=1, subject="mentiq")
        r = env["client"].get("/badges/me", headers=_auth(env["student"]))
        badges = {b["badge_type"]: b for b in r.json()}
        assert badges["fenn_ustasi"]["earned"] is True

    def test_fenn_ustasi_not_earned_when_spread_across_subjects(self, env):
        _completed_homework(env, student_id=env["student"]["id"], score=1, subject="mentiq")
        _completed_homework(env, student_id=env["student"]["id"], score=1, subject="informatika")
        r = env["client"].get("/badges/me", headers=_auth(env["student"]))
        badges = {b["badge_type"]: b for b in r.json()}
        assert badges["fenn_ustasi"]["earned"] is False

    def test_suretli_eqli_earned_on_fast_completion(self, env):
        attempt_id = _completed_homework(env, student_id=env["student"]["id"], score=1)
        _set_attempt_times(
            env, attempt_id,
            started_at="2026-09-08T10:00:00+00:00", completed_at="2026-09-08T10:01:00+00:00",
        )
        r = env["client"].get("/badges/me", headers=_auth(env["student"]))
        badges = {b["badge_type"]: b for b in r.json()}
        assert badges["suretli_eqli"]["earned"] is True

    def test_suretli_eqli_not_earned_when_slow(self, env):
        attempt_id = _completed_homework(env, student_id=env["student"]["id"], score=1)
        _set_attempt_times(
            env, attempt_id,
            started_at="2026-09-08T10:00:00+00:00", completed_at="2026-09-08T10:30:00+00:00",
        )
        r = env["client"].get("/badges/me", headers=_auth(env["student"]))
        badges = {b["badge_type"]: b for b in r.json()}
        assert badges["suretli_eqli"]["earned"] is False

    def test_silsile_5_after_5_distinct_days(self, env):
        days = ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05"]
        for day in days:
            attempt_id = _completed_homework(env, student_id=env["student"]["id"], score=1)
            _set_attempt_times(
                env, attempt_id, started_at=f"{day}T10:00:00+00:00", completed_at=f"{day}T10:01:00+00:00"
            )
        r = env["client"].get("/badges/me", headers=_auth(env["student"]))
        badges = {b["badge_type"]: b for b in r.json()}
        assert badges["silsile_5"]["earned"] is True

    def test_silsile_5_not_earned_with_fewer_distinct_days(self, env):
        for _ in range(3):
            attempt_id = _completed_homework(env, student_id=env["student"]["id"], score=1)
            _set_attempt_times(
                env, attempt_id,
                started_at="2026-09-01T10:00:00+00:00", completed_at="2026-09-01T10:01:00+00:00",
            )
        r = env["client"].get("/badges/me", headers=_auth(env["student"]))
        badges = {b["badge_type"]: b for b in r.json()}
        assert badges["silsile_5"]["earned"] is False

    def test_earned_at_stays_stable_across_calls(self, env):
        _completed_homework(env, student_id=env["student"]["id"], score=1)
        first = env["client"].get("/badges/me", headers=_auth(env["student"])).json()
        second = env["client"].get("/badges/me", headers=_auth(env["student"])).json()
        first_ts = {b["badge_type"]: b["earned_at"] for b in first}
        second_ts = {b["badge_type"]: b["earned_at"] for b in second}
        assert first_ts["ilk_addim"] == second_ts["ilk_addim"]

    def test_badges_do_not_leak_across_students(self, env):
        other = env["users"].create("basqa@masternr1.az", "hash", "Başqa")
        _completed_homework(env, student_id=env["student"]["id"], score=1)
        r = env["client"].get("/badges/me", headers=_auth(other))
        badges = {b["badge_type"]: b for b in r.json()}
        assert badges["ilk_addim"]["earned"] is False
