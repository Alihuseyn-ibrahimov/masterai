"""Müəllim konsolunun xülasə endpoint-i.

NİYƏ LAZIMDIR: konsol yalnız sual bankları siyahısını görürdü. Müəllimin
işi üçün lazım olan iki şey heç yerdə göstərilmirdi:
  - hansı ev tapşırığı son tarixə yaxınlaşır və neçə tələbə həll edib,
  - son canlı sessiya necə keçdi.

Bu məlumat bazada VAR idi, sadəcə bir yerə yığılmamışdı — müəllim üç
ayrı səhifəni gəzməli olurdu.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion
from server.app import (
    app,
    get_homework_store,
    get_live_session_store,
    get_question_set_store,
    get_token_secret,
    get_user_store,
)
from server.auth import create_token
from server.homework_store import HomeworkStore
from server.live_session_store import LiveSessionStore
from server.question_set_store import QuestionSetStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


def _question(n: int) -> MCQQuestion:
    return MCQQuestion(
        question=f"Sual {n}?",
        options=["A", "B", "C", "D", "E"],
        correct_index=0,
        explanation="İzah mətni burada, kifayət qədər uzun.",
    )


@pytest.fixture
def env():
    users = UserStore(":memory:")
    question_sets = QuestionSetStore(":memory:")
    live_sessions = LiveSessionStore(":memory:")
    homework = HomeworkStore(":memory:")

    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_question_set_store] = lambda: question_sets
    app.dependency_overrides[get_live_session_store] = lambda: live_sessions
    app.dependency_overrides[get_homework_store] = lambda: homework
    app.dependency_overrides[get_token_secret] = lambda: _SECRET

    client = TestClient(app)
    teacher = users.create("muellim@masternr1.az", "hash", "Müəllim")
    # `set_teacher` MƏCBURİDİR: `/live/*` endpointləri artıq müəllim
    # qapısından keçir (bax `get_current_teacher`). Əvvəl bu fixture
    # «müəllim» adlı ADİ istifadəçi yaradırdı - qapının beş yerdə
    # unudulmasının görünməməsinin səbəbi məhz bu idi.
    users.set_teacher(teacher["id"], True)
    teacher = users.get_by_id(teacher["id"])
    yield {
        "client": client,
        "question_sets": question_sets,
        "live_sessions": live_sessions,
        "homework": homework,
        "teacher": teacher,
    }
    app.dependency_overrides.clear()


def _auth(user) -> dict:
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


class TestAccess:
    def test_requires_authentication(self, env):
        assert env["client"].get("/live/teacher-summary").status_code == 401


class TestQuestionSetCounts:
    def test_empty_state_reports_zeroes(self, env):
        r = env["client"].get("/live/teacher-summary", headers=_auth(env["teacher"]))
        assert r.status_code == 200
        assert r.json()["question_sets"] == {
            "ready": 0, "processing": 0, "failed": 0, "total": 0
        }

    def test_each_status_is_counted(self, env):
        store = env["question_sets"]
        ready = store.create("mentiq", "Hazır", "link", "https://n.az", env["teacher"]["id"])
        store.add_question(ready["id"], _question(1))
        store.mark_ready(ready["id"])
        store.create("mentiq", "Emalda", "link", "https://n.az", env["teacher"]["id"])
        failed = store.create("mentiq", "Sınıq", "link", "https://n.az", env["teacher"]["id"])
        store.mark_failed(failed["id"], "Sayt yüklənmədi")

        counts = env["client"].get(
            "/live/teacher-summary", headers=_auth(env["teacher"])
        ).json()["question_sets"]
        assert counts == {"ready": 1, "processing": 1, "failed": 1, "total": 3}


class TestHomework:
    def test_no_assignments_reports_none(self, env):
        body = env["client"].get("/live/teacher-summary", headers=_auth(env["teacher"])).json()
        assert body["homework"]["active"] == 0
        assert body["homework"]["next_due"] is None

    def test_the_nearest_deadline_is_reported_with_progress(self, env):
        store = env["question_sets"]
        qs = store.create("mentiq", "Bank", "link", "https://n.az", env["teacher"]["id"])
        store.add_question(qs["id"], _question(1))
        store.add_question(qs["id"], _question(2))
        store.mark_ready(qs["id"])

        homework = env["homework"]
        far = homework.create_assignment(1, qs["id"], "2099-12-31", env["teacher"]["id"])
        near = homework.create_assignment(2, qs["id"], "2099-01-01", env["teacher"]["id"])
        # Bir tələbə yaxın tapşırığı başlayıb.
        homework.get_or_create_attempt(near["id"], 42)

        body = env["client"].get("/live/teacher-summary", headers=_auth(env["teacher"])).json()
        assert body["homework"]["active"] == 2
        next_due = body["homework"]["next_due"]
        assert next_due["assignment_id"] == near["id"], "ən yaxın son tarix seçilməlidir"
        assert next_due["due_date"] == "2099-01-01"
        assert next_due["title"] == "Bank"
        assert next_due["started"] == 1
        assert far["id"] != near["id"]


class TestLastSession:
    def test_no_sessions_reports_none(self, env):
        body = env["client"].get("/live/teacher-summary", headers=_auth(env["teacher"])).json()
        assert body["last_session"] is None

    def test_the_most_recent_session_is_reported(self, env):
        store = env["question_sets"]
        qs = store.create("mentiq", "Məntiq bankı", "link", "https://n.az", env["teacher"]["id"])
        store.add_question(qs["id"], _question(1))
        store.add_question(qs["id"], _question(2))
        store.mark_ready(qs["id"])

        sessions = env["live_sessions"]
        first = sessions.create_session(qs["id"])
        latest = sessions.create_session(qs["id"])
        sessions.add_participant(latest["id"], "Aysel")
        sessions.add_participant(latest["id"], "Elvin")

        body = env["client"].get("/live/teacher-summary", headers=_auth(env["teacher"])).json()
        last = body["last_session"]
        assert last is not None
        assert last["session_id"] == latest["id"], "ən son sessiya seçilməlidir"
        assert last["title"] == "Məntiq bankı"
        assert last["participants"] == 2
        assert first["id"] != latest["id"]
