"""Zəif mövzu analizi (Faza 2 PR 2, 2026-11-03) — `server/topic_stats.py` +
`GET /me/topics`. Fixture naxışı `tests/server/test_history_endpoints.py`-dən
götürülüb (eyni iki mənbə: canlı sessiya + ev tapşırığı)."""

import json

import pytest
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion
from server.app import (
    app,
    get_chat_store,
    get_homework_store,
    get_lesson_store,
    get_live_session_store,
    get_question_set_store,
    get_token_secret,
    get_user_store,
)
from server.auth import create_token
from server.chat_store import ChatStore
from server.homework_store import HomeworkStore
from server.lesson_store import LessonStore
from server.live_session_store import LiveSessionStore
from server.question_set_store import QuestionSetStore
from server.topic_stats import split_strong_weak, topic_stats_for_student
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


@pytest.fixture
def env():
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    question_sets = QuestionSetStore(":memory:")
    homework = HomeworkStore(":memory:")
    live_sessions = LiveSessionStore(":memory:")
    lessons = LessonStore(":memory:")

    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_chat_store] = lambda: chats
    app.dependency_overrides[get_question_set_store] = lambda: question_sets
    app.dependency_overrides[get_homework_store] = lambda: homework
    app.dependency_overrides[get_live_session_store] = lambda: live_sessions
    app.dependency_overrides[get_lesson_store] = lambda: lessons
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
        "homework": homework, "live_sessions": live_sessions, "lessons": lessons,
        "teacher": teacher, "student": student, "chat": chat,
    }
    app.dependency_overrides.clear()


def _auth(user) -> dict:
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


def _question_set(env, topics, subject="hüquq", title="Konstitusiya"):
    """`topics[i]` - i-ci sualın mövzusu (`None` = köhnə, mövzusuz sual)."""
    qs = env["question_sets"].create(
        subject=subject, title=title, material_kind="link",
        material_location="https://x.az", created_by=env["teacher"]["id"],
    )
    for i, topic in enumerate(topics):
        env["question_sets"].add_question(
            qs["id"],
            MCQQuestion(
                question=f"Sual {i}?", options=["A", "B", "C", "D", "E"],
                correct_index=0, explanation=f"izah {i}", topic=topic,
            ),
        )
    env["question_sets"].mark_ready(qs["id"])
    return qs


def _live_session_with_answers(env, qs, *, user_id, correctness: list[bool]):
    session = env["live_sessions"].create_session(qs["id"])
    participant = env["live_sessions"].add_participant(session["id"], "Ad", user_id=user_id)
    for i, correct in enumerate(correctness):
        env["live_sessions"].record_answer(
            session["id"], participant["id"], i, chosen_index=0 if correct else 1, is_correct=correct,
        )
    report = {
        "session_id": session["id"], "total_questions": len(correctness),
        "rankings": [{"rank": 1, "participant_id": participant["id"], "display_name": "Ad",
                      "score": sum(correctness)}],
        "per_question": [],
    }
    env["live_sessions"].save_report(session["id"], json.dumps(report))
    env["live_sessions"].set_status(session["id"], "finished")
    return session


def _homework_with_answers(env, qs, *, student_id, correctness: list[bool]):
    assignment = env["homework"].create_assignment(
        env["chat"]["id"], qs["id"], "2026-11-14", created_by=env["teacher"]["id"]
    )
    attempt = env["homework"].get_or_create_attempt(assignment["id"], student_id=student_id)
    for i, correct in enumerate(correctness):
        env["homework"].answer(
            attempt["id"], i, chosen_index=0 if correct else 1, is_correct=correct,
            total_questions=len(correctness),
        )
    return assignment


class TestTopicStatsForStudent:
    def test_empty_history(self, env):
        stats = topic_stats_for_student(
            env["student"]["id"], live_sessions=env["live_sessions"],
            homework=env["homework"], question_sets=env["question_sets"],
        )
        assert stats == []

    def test_legacy_topicless_questions_excluded(self, env):
        qs = _question_set(env, [None, None])
        _live_session_with_answers(env, qs, user_id=env["student"]["id"], correctness=[True, False])
        stats = topic_stats_for_student(
            env["student"]["id"], live_sessions=env["live_sessions"],
            homework=env["homework"], question_sets=env["question_sets"],
        )
        assert stats == []

    def test_groups_by_topic_across_both_sources(self, env):
        qs1 = _question_set(env, ["seçki hüququ", "seçki hüququ"])
        _live_session_with_answers(env, qs1, user_id=env["student"]["id"], correctness=[True, False])
        qs2 = _question_set(env, ["seçki hüququ", "əmək hüququ"])
        _homework_with_answers(env, qs2, student_id=env["student"]["id"], correctness=[True, True])

        stats = topic_stats_for_student(
            env["student"]["id"], live_sessions=env["live_sessions"],
            homework=env["homework"], question_sets=env["question_sets"],
        )
        by_topic = {s["topic"]: s for s in stats}
        assert by_topic["seçki hüququ"]["correct"] == 2
        assert by_topic["seçki hüququ"]["total"] == 3
        assert by_topic["əmək hüququ"] == {"topic": "əmək hüququ", "correct": 1, "total": 1, "percent": 100}

    def test_sorted_weakest_first(self, env):
        qs = _question_set(env, ["zəif", "zəif", "güclü", "güclü"])
        _live_session_with_answers(env, qs, user_id=env["student"]["id"],
                                   correctness=[False, False, True, True])
        stats = topic_stats_for_student(
            env["student"]["id"], live_sessions=env["live_sessions"],
            homework=env["homework"], question_sets=env["question_sets"],
        )
        assert [s["topic"] for s in stats] == ["zəif", "güclü"]


class TestSplitStrongWeak:
    def test_below_min_answers_excluded(self):
        stats = [{"topic": "a", "correct": 0, "total": 1, "percent": 0}]
        strong, weak = split_strong_weak(stats)
        assert strong == [] and weak == []

    def test_weak_below_threshold(self):
        stats = [{"topic": "a", "correct": 1, "total": 2, "percent": 50}]
        strong, weak = split_strong_weak(stats)
        assert strong == []
        assert weak == stats

    def test_strong_at_or_above_threshold(self):
        stats = [{"topic": "a", "correct": 4, "total": 5, "percent": 80}]
        strong, weak = split_strong_weak(stats)
        assert strong == stats
        assert weak == []

    def test_middle_band_in_neither_list(self):
        stats = [{"topic": "a", "correct": 7, "total": 10, "percent": 70}]
        strong, weak = split_strong_weak(stats)
        assert strong == [] and weak == []


class TestMyTopicsEndpoint:
    def test_requires_auth(self, env):
        assert env["client"].get("/me/topics").status_code == 401

    def test_empty_when_nothing_done(self, env):
        r = env["client"].get("/me/topics", headers=_auth(env["student"]))
        assert r.status_code == 200
        assert r.json() == {"strong": [], "weak": []}

    def test_reports_strong_and_weak(self, env):
        qs = _question_set(env, ["zəif mövzu", "zəif mövzu", "güclü mövzu", "güclü mövzu"])
        _live_session_with_answers(env, qs, user_id=env["student"]["id"],
                                   correctness=[False, False, True, True])
        r = env["client"].get("/me/topics", headers=_auth(env["student"]))
        body = r.json()
        assert body["weak"] == [{"topic": "zəif mövzu", "correct": 0, "total": 2, "percent": 0}]
        assert body["strong"] == [{"topic": "güclü mövzu", "correct": 2, "total": 2, "percent": 100}]


class TestMyAdaptiveQuizEndpoint:
    """Faza 2 PR 3 - `GET /me/adaptive-quiz` (bax `server/adaptive_quiz.py`)."""

    def test_requires_auth(self, env):
        assert env["client"].get("/me/adaptive-quiz").status_code == 401

    def test_empty_when_no_weak_topics(self, env):
        r = env["client"].get("/me/adaptive-quiz", headers=_auth(env["student"]))
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_weak_topic_questions_with_answers(self, env):
        qs = _question_set(env, ["zəif mövzu", "zəif mövzu", "güclü mövzu", "güclü mövzu"])
        _live_session_with_answers(env, qs, user_id=env["student"]["id"],
                                   correctness=[False, False, True, True])
        r = env["client"].get("/me/adaptive-quiz", headers=_auth(env["student"]))
        assert r.status_code == 200
        questions = r.json()
        assert questions
        assert all(q["topic"] == "zəif mövzu" for q in questions)
        # Düzgün cavab+izah DAXİLDİR - bu sərbəst məşqdir, qiymətləndirmə yox.
        assert "correct_index" in questions[0] and "explanation" in questions[0]


class TestMyProgressEndpoint:
    """Faza 3 PR 1 - `GET /me/progress` (bax `server/progress_stats.py`)."""

    def test_requires_auth(self, env):
        assert env["client"].get("/me/progress").status_code == 401

    def test_empty_history_gives_empty_stats(self, env):
        r = env["client"].get("/me/progress", headers=_auth(env["student"]))
        assert r.status_code == 200
        body = r.json()
        assert body["weekly"] == []
        assert body["by_subject"] == []
        assert body["attendance"] == {"attended": 0, "total": 0, "percent": None}

    def test_includes_subject_breakdown(self, env):
        qs = _question_set(env, [None, None], subject="kimya")
        _live_session_with_answers(env, qs, user_id=env["student"]["id"], correctness=[True, False])
        r = env["client"].get("/me/progress", headers=_auth(env["student"]))
        body = r.json()
        assert body["by_subject"] == [{"subject": "kimya", "correct": 1, "total": 2, "percent": 50}]


class TestClassProgressEndpoint:
    """Faza 3 PR 1 - `GET /live/chats/{chat_id}/progress` (müəllim)."""

    def test_requires_auth(self, env):
        assert env["client"].get(f"/live/chats/{env['chat']['id']}/progress").status_code == 401

    def test_non_teacher_gets_403(self, env):
        r = env["client"].get(f"/live/chats/{env['chat']['id']}/progress", headers=_auth(env["student"]))
        assert r.status_code == 403

    def test_non_member_teacher_gets_403(self, env):
        other_teacher = env["users"].create("baska@masternr1.az", "hash", "Başqa")
        env["users"].set_teacher(other_teacher["id"], True)
        other_teacher = env["users"].get_by_id(other_teacher["id"])
        r = env["client"].get(f"/live/chats/{env['chat']['id']}/progress", headers=_auth(other_teacher))
        assert r.status_code == 403

    def test_unknown_chat_returns_404(self, env):
        r = env["client"].get("/live/chats/999/progress", headers=_auth(env["teacher"]))
        assert r.status_code == 404

    def test_aggregates_students_excludes_teacher(self, env):
        qs = _question_set(env, [None, None], subject="kimya")
        _live_session_with_answers(env, qs, user_id=env["student"]["id"], correctness=[True, False])
        r = env["client"].get(f"/live/chats/{env['chat']['id']}/progress", headers=_auth(env["teacher"]))
        assert r.status_code == 200
        body = r.json()
        assert body["by_subject"] == [{"subject": "kimya", "correct": 1, "total": 2, "percent": 50}]
