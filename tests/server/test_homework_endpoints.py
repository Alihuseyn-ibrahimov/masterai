import pytest
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion
from server.app import (
    app,
    get_chat_store,
    get_homework_store,
    get_question_set_store,
    get_token_secret,
    get_user_store,
)
from server.auth import create_token
from server.chat_store import ChatStore
from server.homework_store import HomeworkStore
from server.question_set_store import QuestionSetStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


@pytest.fixture
def env():
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    question_sets = QuestionSetStore(":memory:")
    homework = HomeworkStore(":memory:")

    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_chat_store] = lambda: chats
    app.dependency_overrides[get_question_set_store] = lambda: question_sets
    app.dependency_overrides[get_homework_store] = lambda: homework
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
        "homework": homework, "teacher": teacher, "student": student, "chat": chat,
    }
    app.dependency_overrides.clear()


def _auth(user) -> dict:
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


def _ready_question_set(env, n_questions=2):
    qs = env["question_sets"].create(
        subject="mentiq", title="Silloqizmlər", material_kind="link",
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


class TestCreateAssignment:
    def test_requires_auth(self, env):
        r = env["client"].post("/homework/assignments", json={"chat_id": 1, "question_set_id": 1, "due_date": "2026-09-14"})
        assert r.status_code == 401

    def test_non_teacher_gets_403(self, env):
        qs = _ready_question_set(env)
        r = env["client"].post(
            "/homework/assignments",
            json={"chat_id": env["chat"]["id"], "question_set_id": qs["id"], "due_date": "2026-09-14"},
            headers=_auth(env["student"]),
        )
        assert r.status_code == 403

    def test_unknown_chat_returns_404(self, env):
        qs = _ready_question_set(env)
        r = env["client"].post(
            "/homework/assignments",
            json={"chat_id": 999, "question_set_id": qs["id"], "due_date": "2026-09-14"},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 404

    def test_non_member_teacher_gets_403(self, env):
        qs = _ready_question_set(env)
        other_chat = env["chats"].create(kind="group", created_by=env["student"]["id"], name="Başqa")
        r = env["client"].post(
            "/homework/assignments",
            json={"chat_id": other_chat["id"], "question_set_id": qs["id"], "due_date": "2026-09-14"},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 403

    def test_unknown_question_set_returns_404(self, env):
        r = env["client"].post(
            "/homework/assignments",
            json={"chat_id": env["chat"]["id"], "question_set_id": 999, "due_date": "2026-09-14"},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 404

    def test_not_ready_question_set_returns_400(self, env):
        qs = env["question_sets"].create(
            subject="mentiq", title="A", material_kind="link", material_location="https://x.az",
            created_by=env["teacher"]["id"],
        )
        r = env["client"].post(
            "/homework/assignments",
            json={"chat_id": env["chat"]["id"], "question_set_id": qs["id"], "due_date": "2026-09-14"},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 400

    def test_creates_assignment(self, env):
        qs = _ready_question_set(env)
        r = env["client"].post(
            "/homework/assignments",
            json={"chat_id": env["chat"]["id"], "question_set_id": qs["id"], "due_date": "2026-09-14"},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 201
        body = r.json()
        assert body["chat_id"] == env["chat"]["id"]
        assert body["question_set_id"] == qs["id"]
        assert body["due_date"] == "2026-09-14"
        assert body["completed_count"] == 0
        assert body["total_members"] == 2


class TestListAssignments:
    def test_non_member_gets_403(self, env):
        r = env["client"].get("/homework/assignments", params={"chat_id": 999}, headers=_auth(env["teacher"]))
        assert r.status_code == 403

    def test_lists_only_own_assignments(self, env):
        qs = _ready_question_set(env)
        env["homework"].create_assignment(env["chat"]["id"], qs["id"], "2026-09-14", created_by=env["teacher"]["id"])
        r = env["client"].get("/homework/assignments", params={"chat_id": env["chat"]["id"]}, headers=_auth(env["teacher"]))
        assert r.status_code == 200
        assert len(r.json()) == 1
        # tələbə çat üzvüdür, amma bu tapşırığı YARATMAYIB (created_by şərtinə görə)
        r2 = env["client"].get("/homework/assignments", params={"chat_id": env["chat"]["id"]}, headers=_auth(env["student"]))
        assert r2.json() == []


class TestReport:
    def test_unknown_assignment_returns_404(self, env):
        r = env["client"].get("/homework/assignments/999/report", headers=_auth(env["teacher"]))
        assert r.status_code == 404

    def test_non_owner_gets_403(self, env):
        qs = _ready_question_set(env)
        a = env["homework"].create_assignment(env["chat"]["id"], qs["id"], "2026-09-14", created_by=env["teacher"]["id"])
        r = env["client"].get(f"/homework/assignments/{a['id']}/report", headers=_auth(env["student"]))
        assert r.status_code == 403

    def test_shows_waiting_and_completed_status(self, env):
        qs = _ready_question_set(env, n_questions=1)
        a = env["homework"].create_assignment(env["chat"]["id"], qs["id"], "2026-09-14", created_by=env["teacher"]["id"])

        r = env["client"].get(f"/homework/assignments/{a['id']}/report", headers=_auth(env["teacher"]))
        rows = {row["student_id"]: row for row in r.json()}
        assert rows[env["student"]["id"]]["status"] == "gözləyir"

        env["client"].post(f"/homework/assignments/{a['id']}/start", headers=_auth(env["student"]))
        attempt = env["homework"].get_attempt_for_student(a["id"], env["student"]["id"])
        env["homework"].answer(attempt["id"], 0, 0, True, total_questions=1)

        r2 = env["client"].get(f"/homework/assignments/{a['id']}/report", headers=_auth(env["teacher"]))
        rows2 = {row["student_id"]: row for row in r2.json()}
        assert rows2[env["student"]["id"]]["status"] == "tamamlanıb"
        assert rows2[env["student"]["id"]]["score"] == 1


class TestMyAssignments:
    def test_empty_when_no_assignments(self, env):
        r = env["client"].get("/homework/my-assignments", headers=_auth(env["student"]))
        assert r.json() == []

    def test_lists_assignment_with_status(self, env):
        qs = _ready_question_set(env)
        env["homework"].create_assignment(env["chat"]["id"], qs["id"], "2026-09-14", created_by=env["teacher"]["id"])
        r = env["client"].get("/homework/my-assignments", headers=_auth(env["student"]))
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["subject"] == "mentiq"
        assert body[0]["title"] == "Silloqizmlər"
        assert body[0]["status"] == "gözləyir"


class TestStartAttempt:
    def test_unknown_assignment_returns_404(self, env):
        r = env["client"].post("/homework/assignments/999/start", headers=_auth(env["student"]))
        assert r.status_code == 404

    def test_non_member_gets_403(self, env):
        qs = _ready_question_set(env)
        other_student = env["users"].create("kenar@x.az", "hash", "Kənar")
        a = env["homework"].create_assignment(env["chat"]["id"], qs["id"], "2026-09-14", created_by=env["teacher"]["id"])
        r = env["client"].post(f"/homework/assignments/{a['id']}/start", headers=_auth(other_student))
        assert r.status_code == 403

    def test_returns_first_question(self, env):
        qs = _ready_question_set(env, n_questions=2)
        a = env["homework"].create_assignment(env["chat"]["id"], qs["id"], "2026-09-14", created_by=env["teacher"]["id"])
        r = env["client"].post(f"/homework/assignments/{a['id']}/start", headers=_auth(env["student"]))
        assert r.status_code == 200
        body = r.json()
        assert body["current_question_index"] == 0
        assert body["question"]["index"] == 0
        assert body["question"]["total"] == 2
        assert "correct_index" not in body["question"]

    def test_resumes_in_progress_attempt(self, env):
        qs = _ready_question_set(env, n_questions=2)
        a = env["homework"].create_assignment(env["chat"]["id"], qs["id"], "2026-09-14", created_by=env["teacher"]["id"])
        first = env["client"].post(f"/homework/assignments/{a['id']}/start", headers=_auth(env["student"])).json()
        env["client"].post(
            f"/homework/attempts/{first['attempt_id']}/answer",
            json={"question_index": 0, "chosen_index": 0},
            headers=_auth(env["student"]),
        )
        second = env["client"].post(f"/homework/assignments/{a['id']}/start", headers=_auth(env["student"])).json()
        assert second["attempt_id"] == first["attempt_id"]
        assert second["current_question_index"] == 1


class TestAnswer:
    def test_unknown_attempt_returns_404(self, env):
        r = env["client"].post(
            "/homework/attempts/999/answer", json={"question_index": 0, "chosen_index": 0},
            headers=_auth(env["student"]),
        )
        assert r.status_code == 404

    def test_other_students_attempt_returns_403(self, env):
        qs = _ready_question_set(env)
        a = env["homework"].create_assignment(env["chat"]["id"], qs["id"], "2026-09-14", created_by=env["teacher"]["id"])
        started = env["client"].post(f"/homework/assignments/{a['id']}/start", headers=_auth(env["student"])).json()
        r = env["client"].post(
            f"/homework/attempts/{started['attempt_id']}/answer",
            json={"question_index": 0, "chosen_index": 0}, headers=_auth(env["teacher"]),
        )
        assert r.status_code == 403

    def test_full_flow_ends_completed(self, env):
        qs = _ready_question_set(env, n_questions=2)
        a = env["homework"].create_assignment(env["chat"]["id"], qs["id"], "2026-09-14", created_by=env["teacher"]["id"])
        started = env["client"].post(f"/homework/assignments/{a['id']}/start", headers=_auth(env["student"])).json()

        r1 = env["client"].post(
            f"/homework/attempts/{started['attempt_id']}/answer",
            json={"question_index": 0, "chosen_index": 0}, headers=_auth(env["student"]),
        )
        assert r1.status_code == 200
        body1 = r1.json()
        assert body1["is_correct"] is True
        assert body1["next_question"]["index"] == 1

        r2 = env["client"].post(
            f"/homework/attempts/{started['attempt_id']}/answer",
            json={"question_index": 1, "chosen_index": 4}, headers=_auth(env["student"]),
        )
        body2 = r2.json()
        assert body2["is_correct"] is False
        assert body2["next_question"] is None

    def test_wrong_question_index_returns_400(self, env):
        qs = _ready_question_set(env, n_questions=2)
        a = env["homework"].create_assignment(env["chat"]["id"], qs["id"], "2026-09-14", created_by=env["teacher"]["id"])
        started = env["client"].post(f"/homework/assignments/{a['id']}/start", headers=_auth(env["student"])).json()
        r = env["client"].post(
            f"/homework/attempts/{started['attempt_id']}/answer",
            json={"question_index": 1, "chosen_index": 0}, headers=_auth(env["student"]),
        )
        assert r.status_code == 400

    def test_answering_completed_attempt_returns_400(self, env):
        qs = _ready_question_set(env, n_questions=1)
        a = env["homework"].create_assignment(env["chat"]["id"], qs["id"], "2026-09-14", created_by=env["teacher"]["id"])
        started = env["client"].post(f"/homework/assignments/{a['id']}/start", headers=_auth(env["student"])).json()
        env["client"].post(
            f"/homework/attempts/{started['attempt_id']}/answer",
            json={"question_index": 0, "chosen_index": 0}, headers=_auth(env["student"]),
        )
        r = env["client"].post(
            f"/homework/attempts/{started['attempt_id']}/answer",
            json={"question_index": 0, "chosen_index": 0}, headers=_auth(env["student"]),
        )
        assert r.status_code == 400
