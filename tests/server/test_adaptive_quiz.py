"""Fərdi məşq quizi (Faza 2 PR 3, 2026-11-03) — `server/adaptive_quiz.py`.
Fixture naxışı `tests/server/test_topic_stats.py`-dən götürülüb."""

import json

import pytest

from pipeline.models import MCQQuestion
from server.adaptive_quiz import build_adaptive_quiz
from server.homework_store import HomeworkStore
from server.live_session_store import LiveSessionStore
from server.question_set_store import QuestionSetStore


@pytest.fixture
def env():
    return {
        "question_sets": QuestionSetStore(":memory:"),
        "homework": HomeworkStore(":memory:"),
        "live_sessions": LiveSessionStore(":memory:"),
    }


def _question_set(env, topics, subject="hüquq", title="Konstitusiya"):
    qs = env["question_sets"].create(
        subject=subject, title=title, material_kind="link",
        material_location="https://x.az", created_by=1,
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


def _live_session_with_answers(env, qs, *, user_id, correctness):
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


class TestBuildAdaptiveQuiz:
    def test_empty_when_no_weak_topics(self, env):
        assert build_adaptive_quiz(
            1, live_sessions=env["live_sessions"], homework=env["homework"],
            question_sets=env["question_sets"],
        ) == []

    def test_pulls_questions_from_weak_topic(self, env):
        qs = _question_set(env, ["zəif mövzu", "zəif mövzu", "güclü mövzu", "güclü mövzu"])
        _live_session_with_answers(env, qs, user_id=1, correctness=[False, False, True, True])
        questions = build_adaptive_quiz(
            1, live_sessions=env["live_sessions"], homework=env["homework"],
            question_sets=env["question_sets"],
        )
        assert questions
        assert all(q["topic"] == "zəif mövzu" for q in questions)

    def test_respects_limit(self, env):
        qs = _question_set(env, ["zəif"] * 8)
        _live_session_with_answers(env, qs, user_id=1, correctness=[False, False] + [False] * 6)
        questions = build_adaptive_quiz(
            1, live_sessions=env["live_sessions"], homework=env["homework"],
            question_sets=env["question_sets"], limit=3,
        )
        assert len(questions) == 3

    def test_ignores_other_students(self, env):
        qs = _question_set(env, ["zəif mövzu", "zəif mövzu"])
        _live_session_with_answers(env, qs, user_id=1, correctness=[False, False])
        assert build_adaptive_quiz(
            2, live_sessions=env["live_sessions"], homework=env["homework"],
            question_sets=env["question_sets"],
        ) == []

    def test_difficulty_model_prefers_moderate_questions(self, env):
        """Model `easy`-i çox yüksək, `hard`-ı çox aşağı proqnozlaşdırsın -
        `moderate` hədəf aralığına ən yaxın olmalıdır."""
        qs = _question_set(env, ["zəif"] * 3)
        _live_session_with_answers(env, qs, user_id=1, correctness=[False, False, False])

        class FakeModel:
            def predict(self, mcq):
                return {"Sual 0?": 0.95, "Sual 1?": 0.55, "Sual 2?": 0.05}[mcq.question]

        result = build_adaptive_quiz(
            1, live_sessions=env["live_sessions"], homework=env["homework"],
            question_sets=env["question_sets"], difficulty_model=FakeModel(), limit=3,
        )
        assert result[0]["question"] == "Sual 1?"


def test_default_limit_is_five():
    from server.adaptive_quiz import DEFAULT_LIMIT
    assert DEFAULT_LIMIT == 5
