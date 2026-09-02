import pytest

from pipeline.models import MCQQuestion
from server.chat_store import ChatStore
from server.material_store import MaterialStore
from server.message_store import MessageStore
from server.quiz_attempt_store import QuizAttemptStore
from server.quiz_runner import check_timeout, record_answer, start_quiz
from server.quiz_session_store import QuizSessionStore
from server.question_store import QuestionStore

_TEST_TIMEOUT = 0.2


class FakeConnectionManager:
    def __init__(self):
        self.sent: list[tuple[int, dict]] = []

    async def broadcast(self, chat_id: int, message: dict) -> None:
        self.sent.append((chat_id, message))


def _mcq(question: str, correct_index: int = 0) -> MCQQuestion:
    return MCQQuestion(
        question=question,
        options=["A", "B", "C", "D", "E"],
        correct_index=correct_index,
        explanation=f"İzah: {question}",
    )


@pytest.fixture
def env(tmp_path):
    chats = ChatStore(path=str(tmp_path / "chats.db"))
    materials = MaterialStore(path=str(tmp_path / "materials.db"))
    questions = QuestionStore(path=str(tmp_path / "questions.db"))
    sessions = QuizSessionStore(path=str(tmp_path / "quiz_sessions.db"))
    attempts = QuizAttemptStore(path=str(tmp_path / "attempts.db"))
    messages = MessageStore(path=str(tmp_path / "messages.db"))
    manager = FakeConnectionManager()

    chat = chats.create(kind="group", created_by=1, name="Qrup")
    chats.add_member(chat["id"], 1)
    chats.add_member(chat["id"], 2)

    material = materials.create(chat_id=chat["id"], uploaded_by=1, kind="pdf", location="/a.pdf")
    q1 = questions.create_from_mcq(material["id"], _mcq("Sual 1?"))
    q2 = questions.create_from_mcq(material["id"], _mcq("Sual 2?"))

    return {
        "chats": chats,
        "questions": questions,
        "sessions": sessions,
        "attempts": attempts,
        "messages": messages,
        "manager": manager,
        "chat_id": chat["id"],
        "material_id": material["id"],
        "q1": q1,
        "q2": q2,
    }


def _kwargs(env):
    return dict(
        session_store=env["sessions"],
        question_store=env["questions"],
        attempt_store=env["attempts"],
        message_store=env["messages"],
        connection_manager=env["manager"],
    )


@pytest.mark.asyncio
async def test_advances_after_timeout_when_nobody_answered(env):
    await start_quiz(
        env["chat_id"], env["material_id"],
        question_store=env["questions"], session_store=env["sessions"],
        message_store=env["messages"], connection_manager=env["manager"],
    )

    await check_timeout(
        env["chat_id"], expected_index=0, timeout_seconds=_TEST_TIMEOUT, **_kwargs(env)
    )

    session = env["sessions"].get(env["chat_id"])
    assert session["current_index"] == 1

    types = [m["type"] for _, m in env["manager"].sent]
    assert types == ["quiz_question", "quiz_result", "quiz_question"]
    # Timeout-da heç kim cavablamadığı üçün quiz_result-da answers boşdur
    result_frame = env["manager"].sent[1][1]
    assert result_frame["answers"] == []


@pytest.mark.asyncio
async def test_is_noop_when_question_already_advanced_early(env):
    chats = env["chats"]
    # Yalnız 1 üzv qoyuruq ki, tək cavabla dərhal irəliləmə tetiklənsin
    chats.add_member(env["chat_id"], 3)
    only_member_kwargs = dict(_kwargs(env), chat_store=chats)

    await start_quiz(
        env["chat_id"], env["material_id"],
        question_store=env["questions"], session_store=env["sessions"],
        message_store=env["messages"], connection_manager=env["manager"],
    )

    # 3 üzvün hamısı dərhal cavablayır — erkən keçid baş verməlidir
    for uid in (1, 2, 3):
        await record_answer(
            env["chat_id"], user_id=uid, question_id=env["q1"]["id"], chosen_index=0,
            **only_member_kwargs,
        )

    session_after_early_advance = env["sessions"].get(env["chat_id"])
    assert session_after_early_advance["current_index"] == 1
    sent_count_before_timeout = len(env["manager"].sent)

    # 0-cı sual üçün planlaşdırılmış timeout indi çatır — artıq keçilib, no-op olmalıdır
    result = await check_timeout(
        env["chat_id"], expected_index=0, timeout_seconds=_TEST_TIMEOUT, **_kwargs(env)
    )

    assert result is None
    assert len(env["manager"].sent) == sent_count_before_timeout  # yeni broadcast yoxdur


@pytest.mark.asyncio
async def test_is_noop_when_session_already_finished(env):
    await start_quiz(
        env["chat_id"], env["material_id"],
        question_store=env["questions"], session_store=env["sessions"],
        message_store=env["messages"], connection_manager=env["manager"],
    )
    # Materialda 2 sual var, hər ikisini timeout ilə keçirik ki, sessiya bitsin
    await check_timeout(
        env["chat_id"], expected_index=0, timeout_seconds=_TEST_TIMEOUT, **_kwargs(env)
    )
    await check_timeout(
        env["chat_id"], expected_index=1, timeout_seconds=_TEST_TIMEOUT, **_kwargs(env)
    )
    session = env["sessions"].get(env["chat_id"])
    assert session["status"] == "finished"

    sent_count_before = len(env["manager"].sent)
    result = await check_timeout(
        env["chat_id"], expected_index=1, timeout_seconds=_TEST_TIMEOUT, **_kwargs(env)
    )

    assert result is None
    assert len(env["manager"].sent) == sent_count_before
