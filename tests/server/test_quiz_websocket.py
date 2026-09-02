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


def _mcq(question: str, correct_index: int = 0) -> MCQQuestion:
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

    ali = users.create("ali@example.com", "hash", "Əli")
    vali = users.create("vali@example.com", "hash", "Vəli")
    chat = chats.create(kind="group", created_by=ali["id"], name="Qrup")
    chats.add_member(chat["id"], ali["id"])
    chats.add_member(chat["id"], vali["id"])

    material = materials.create(chat_id=chat["id"], uploaded_by=ali["id"], kind="pdf", location="/a.pdf")
    materials.update_status(material["id"], "ready")
    q1 = questions.create_from_mcq(material["id"], _mcq("Sual 1?", correct_index=0))
    q2 = questions.create_from_mcq(material["id"], _mcq("Sual 2?", correct_index=1))

    client.post(
        f"/chats/{chat['id']}/quiz/start",
        json={"material_id": material["id"]},
        headers={"Authorization": f"Bearer {create_token(ali['id'], secret=_SECRET)}"},
    )

    yield {
        "client": client,
        "chats": chats,
        "materials": materials,
        "questions": questions,
        "chat_id": chat["id"],
        "ali": ali,
        "vali": vali,
        "q1": q1,
        "q2": q2,
    }
    app.dependency_overrides.clear()


def _ws_url(chat_id: int, user: dict) -> str:
    token = create_token(user["id"], secret=_SECRET)
    return f"/ws/chat/{chat_id}?token={token}"


def test_answering_completes_round_and_posts_result_then_next_question(env):
    # QEYD: bura qəsdən TƏK bağlantı ilə (yalnız ali üzv olan ayrıca çat)
    # sınanır, ali+vali-nin EYNİ ANDA (2 paralel WebSocket) cavablandığı
    # ssenari yox. Starlette `TestClient`-in hər WebSocket bağlantısını
    # ayrı OS thread-ində işlətdiyi aşkarlandı (real smoke debug-unda) —
    # iki bağlantı EYNİ ANDA cavablayanda advance_question-un ardıcıl 2
    # broadcast-ı cross-thread ötürülməli olur və test mühitində asma
    # yaradır (production-da olmayan, TestClient-ə xas məhdudiyyət).
    # "Hamı cavablayanda dərhal keçid" məntiqinin özü artıq
    # `test_quiz_runner.py`-də (FakeConnectionManager ilə, real thread
    # olmadan) tam doğrulanıb — bura yalnız tək-istifadəçili tam REST+WS
    # axınının qırılmadığını yoxlayır.
    solo_chat = env["chats"].create(kind="group", created_by=env["ali"]["id"], name="Tək üzvlü qrup")
    env["chats"].add_member(solo_chat["id"], env["ali"]["id"])
    solo_material = env["materials"].create(
        chat_id=solo_chat["id"], uploaded_by=env["ali"]["id"], kind="pdf", location="/solo.pdf"
    )
    env["materials"].update_status(solo_material["id"], "ready")
    solo_q1 = env["questions"].create_from_mcq(solo_material["id"], _mcq("Solo sual 1?", correct_index=0))
    solo_q2 = env["questions"].create_from_mcq(solo_material["id"], _mcq("Solo sual 2?", correct_index=1))

    env["client"].post(
        f"/chats/{solo_chat['id']}/quiz/start",
        json={"material_id": solo_material["id"]},
        headers={"Authorization": f"Bearer {create_token(env['ali']['id'], secret=_SECRET)}"},
    )

    with env["client"].websocket_connect(_ws_url(solo_chat["id"], env["ali"])) as ws:
        ws.receive_json()  # history (1-ci sual REST-dən artıq göndərilib)

        ws.send_json({"type": "answer", "question_id": solo_q1["id"], "chosen_index": 0})

        result = ws.receive_json()
        assert result["type"] == "quiz_result"
        assert result["correct_index"] == 0

        next_question = ws.receive_json()
        assert next_question["type"] == "quiz_question"
        assert next_question["question_id"] == solo_q2["id"]


def test_answer_to_stale_question_returns_error(env):
    with env["client"].websocket_connect(_ws_url(env["chat_id"], env["ali"])) as ws:
        ws.receive_json()  # history

        ws.send_json({"type": "answer", "question_id": env["q2"]["id"], "chosen_index": 0})
        error = ws.receive_json()
        assert error["type"] == "error"


def test_duplicate_answer_returns_error(env):
    with env["client"].websocket_connect(_ws_url(env["chat_id"], env["ali"])) as ws:
        ws.receive_json()  # history
        ws.send_json({"type": "answer", "question_id": env["q1"]["id"], "chosen_index": 0})
        # tək üzv cavablayıb (vali hələ qoşulmayıb) — irəliləmə tetiklənmir
        ws.send_json({"type": "answer", "question_id": env["q1"]["id"], "chosen_index": 1})
        error = ws.receive_json()
        assert error["type"] == "error"
