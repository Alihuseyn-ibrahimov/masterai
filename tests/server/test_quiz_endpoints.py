import pytest
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion
from server.app import (
    app,
    get_chat_store,
    get_connection_manager,
    get_material_store,
    get_message_store,
    get_question_store,
    get_quiz_attempt_store,
    get_quiz_session_store,
    get_token_secret,
    get_user_store,
)
from server.auth import create_token
from server.chat_store import ChatStore
from server.connection_manager import ConnectionManager
from server.material_store import MaterialStore
from server.message_store import MessageStore
from server.question_store import QuestionStore
from server.quiz_attempt_store import QuizAttemptStore
from server.quiz_session_store import QuizSessionStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


def _mcq(question: str = "Sual 1?", correct_index: int = 0) -> MCQQuestion:
    return MCQQuestion(
        question=question,
        options=["A", "B", "C", "D", "E"],
        correct_index=correct_index,
        explanation=f"İzah: {question}",
    )


@pytest.fixture
def env():
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    materials = MaterialStore(":memory:")
    questions = QuestionStore(":memory:")
    sessions = QuizSessionStore(":memory:")
    attempts = QuizAttemptStore(":memory:")
    messages = MessageStore(":memory:")
    manager = ConnectionManager()

    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_chat_store] = lambda: chats
    app.dependency_overrides[get_material_store] = lambda: materials
    app.dependency_overrides[get_question_store] = lambda: questions
    app.dependency_overrides[get_quiz_session_store] = lambda: sessions
    app.dependency_overrides[get_quiz_attempt_store] = lambda: attempts
    app.dependency_overrides[get_message_store] = lambda: messages
    app.dependency_overrides[get_connection_manager] = lambda: manager
    app.dependency_overrides[get_token_secret] = lambda: _SECRET

    client = TestClient(app)

    uploader = users.create("uploader@example.com", "hash", "Yükləyən")
    other = users.create("other@example.com", "hash", "Başqası")
    chat = chats.create(kind="group", created_by=uploader["id"], name="Qrup")
    chats.add_member(chat["id"], uploader["id"])
    chats.add_member(chat["id"], other["id"])

    ready_material = materials.create(
        chat_id=chat["id"], uploaded_by=uploader["id"], kind="pdf", location="/a.pdf"
    )
    materials.update_status(ready_material["id"], "ready")
    questions.create_from_mcq(ready_material["id"], _mcq())

    yield {
        "client": client,
        "chats": chats,
        "materials": materials,
        "chat_id": chat["id"],
        "uploader": uploader,
        "other": other,
        "ready_material": ready_material,
    }
    app.dependency_overrides.clear()


def _auth(user) -> dict:
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


class TestStartQuiz:
    def test_uploader_can_start(self, env):
        r = env["client"].post(
            f"/chats/{env['chat_id']}/quiz/start",
            json={"material_id": env["ready_material"]["id"]},
            headers=_auth(env["uploader"]),
        )
        assert r.status_code == 201
        body = r.json()
        assert body["status"] == "active"
        assert body["current_index"] == 0

    def test_requires_auth(self, env):
        r = env["client"].post(
            f"/chats/{env['chat_id']}/quiz/start",
            json={"material_id": env["ready_material"]["id"]},
        )
        assert r.status_code == 401

    def test_non_uploader_gets_403(self, env):
        r = env["client"].post(
            f"/chats/{env['chat_id']}/quiz/start",
            json={"material_id": env["ready_material"]["id"]},
            headers=_auth(env["other"]),
        )
        assert r.status_code == 403

    def test_unknown_material_returns_404(self, env):
        r = env["client"].post(
            f"/chats/{env['chat_id']}/quiz/start",
            json={"material_id": 9999},
            headers=_auth(env["uploader"]),
        )
        assert r.status_code == 404

    def test_material_from_other_chat_returns_400(self, env):
        other_chat = env["chats"].create(kind="group", created_by=env["uploader"]["id"], name="Başqa")
        r = env["client"].post(
            f"/chats/{other_chat['id']}/quiz/start",
            json={"material_id": env["ready_material"]["id"]},
            headers=_auth(env["uploader"]),
        )
        assert r.status_code == 400

    def test_not_ready_material_returns_400(self, env):
        processing = env["materials"].create(
            chat_id=env["chat_id"], uploaded_by=env["uploader"]["id"], kind="pdf", location="/b.pdf"
        )
        r = env["client"].post(
            f"/chats/{env['chat_id']}/quiz/start",
            json={"material_id": processing["id"]},
            headers=_auth(env["uploader"]),
        )
        assert r.status_code == 400

    def test_already_active_session_returns_409(self, env):
        env["client"].post(
            f"/chats/{env['chat_id']}/quiz/start",
            json={"material_id": env["ready_material"]["id"]},
            headers=_auth(env["uploader"]),
        )
        r = env["client"].post(
            f"/chats/{env['chat_id']}/quiz/start",
            json={"material_id": env["ready_material"]["id"]},
            headers=_auth(env["uploader"]),
        )
        assert r.status_code == 409
