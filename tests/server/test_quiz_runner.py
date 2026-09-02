import json

import pytest

from pipeline.models import MCQQuestion
from server.chat_store import ChatStore
from server.material_store import MaterialStore
from server.message_store import MessageStore
from server.quiz_attempt_store import QuizAttemptStore
from server.quiz_runner import (
    AlreadyAnswered,
    NotCurrentQuestion,
    QuizError,
    advance_question,
    record_answer,
    start_quiz,
)
from server.quiz_session_store import QuizSessionStore
from server.question_store import QuestionStore


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
    q1 = questions.create_from_mcq(material["id"], _mcq("Sual 1?", correct_index=0))
    q2 = questions.create_from_mcq(material["id"], _mcq("Sual 2?", correct_index=1))

    return {
        "chats": chats,
        "materials": materials,
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


def _kwargs(env, **overrides):
    base = dict(
        session_store=env["sessions"],
        question_store=env["questions"],
        attempt_store=env["attempts"],
        chat_store=env["chats"],
        message_store=env["messages"],
        connection_manager=env["manager"],
    )
    base.update(overrides)
    return base


class TestStartQuiz:
    @pytest.mark.asyncio
    async def test_creates_session_and_posts_first_question(self, env):
        session = await start_quiz(
            env["chat_id"], env["material_id"],
            question_store=env["questions"], session_store=env["sessions"],
            message_store=env["messages"], connection_manager=env["manager"],
        )

        assert session["current_index"] == 0
        assert session["status"] == "active"

        assert len(env["manager"].sent) == 1
        chat_id, payload = env["manager"].sent[0]
        assert chat_id == env["chat_id"]
        assert payload["type"] == "quiz_question"
        assert payload["question_id"] == env["q1"]["id"]
        assert payload["question"] == "Sual 1?"
        assert "correct_index" not in payload
        assert "explanation" not in payload

    @pytest.mark.asyncio
    async def test_persisted_message_does_not_leak_answer(self, env):
        await start_quiz(
            env["chat_id"], env["material_id"],
            question_store=env["questions"], session_store=env["sessions"],
            message_store=env["messages"], connection_manager=env["manager"],
        )
        stored = env["messages"].list_by_chat(env["chat_id"])
        assert len(stored) == 1
        content = json.loads(stored[0]["content"])
        assert "correct_index" not in content
        assert "explanation" not in content

    @pytest.mark.asyncio
    async def test_raises_when_material_has_no_questions(self, env):
        empty_material = env["materials"].create(
            chat_id=env["chat_id"], uploaded_by=1, kind="pdf", location="/empty.pdf"
        )
        with pytest.raises(QuizError):
            await start_quiz(
                env["chat_id"], empty_material["id"],
                question_store=env["questions"], session_store=env["sessions"],
                message_store=env["messages"], connection_manager=env["manager"],
            )


class TestRecordAnswer:
    @pytest.mark.asyncio
    async def test_computes_correctness(self, env):
        await start_quiz(
            env["chat_id"], env["material_id"],
            question_store=env["questions"], session_store=env["sessions"],
            message_store=env["messages"], connection_manager=env["manager"],
        )

        correct = await record_answer(
            env["chat_id"], user_id=1, question_id=env["q1"]["id"], chosen_index=0,
            **_kwargs(env),
        )
        incorrect = await record_answer(
            env["chat_id"], user_id=2, question_id=env["q1"]["id"], chosen_index=1,
            **_kwargs(env),
        )

        assert correct["is_correct"] is True
        assert incorrect["is_correct"] is False

    @pytest.mark.asyncio
    async def test_raises_for_no_active_session(self, env):
        with pytest.raises(QuizError):
            await record_answer(
                env["chat_id"], user_id=1, question_id=env["q1"]["id"], chosen_index=0,
                **_kwargs(env),
            )

    @pytest.mark.asyncio
    async def test_raises_for_stale_question_id(self, env):
        await start_quiz(
            env["chat_id"], env["material_id"],
            question_store=env["questions"], session_store=env["sessions"],
            message_store=env["messages"], connection_manager=env["manager"],
        )
        with pytest.raises(NotCurrentQuestion):
            await record_answer(
                env["chat_id"], user_id=1, question_id=env["q2"]["id"], chosen_index=0,
                **_kwargs(env),
            )

    @pytest.mark.asyncio
    async def test_raises_for_duplicate_answer(self, env):
        await start_quiz(
            env["chat_id"], env["material_id"],
            question_store=env["questions"], session_store=env["sessions"],
            message_store=env["messages"], connection_manager=env["manager"],
        )
        await record_answer(
            env["chat_id"], user_id=1, question_id=env["q1"]["id"], chosen_index=0,
            **_kwargs(env),
        )
        with pytest.raises(AlreadyAnswered):
            await record_answer(
                env["chat_id"], user_id=1, question_id=env["q1"]["id"], chosen_index=1,
                **_kwargs(env),
            )

    @pytest.mark.asyncio
    async def test_all_members_answered_triggers_immediate_advance_to_next_question(self, env):
        await start_quiz(
            env["chat_id"], env["material_id"],
            question_store=env["questions"], session_store=env["sessions"],
            message_store=env["messages"], connection_manager=env["manager"],
        )
        await record_answer(
            env["chat_id"], user_id=1, question_id=env["q1"]["id"], chosen_index=0, **_kwargs(env)
        )
        # hələ 1 üzv qalıb — irəliləmə olmamalıdır
        assert len(env["manager"].sent) == 1

        await record_answer(
            env["chat_id"], user_id=2, question_id=env["q1"]["id"], chosen_index=1, **_kwargs(env)
        )
        # indi hamı cavablayıb — quiz_result + növbəti quiz_question gəlməlidir
        assert len(env["manager"].sent) == 3
        assert env["manager"].sent[1][1]["type"] == "quiz_result"
        assert env["manager"].sent[1][1]["correct_index"] == 0
        assert env["manager"].sent[2][1]["type"] == "quiz_question"
        assert env["manager"].sent[2][1]["question_id"] == env["q2"]["id"]

        session = env["sessions"].get(env["chat_id"])
        assert session["current_index"] == 1
        assert session["status"] == "active"


class TestAdvanceQuestion:
    @pytest.mark.asyncio
    async def test_last_question_posts_finished_with_scores(self, env):
        await start_quiz(
            env["chat_id"], env["material_id"],
            question_store=env["questions"], session_store=env["sessions"],
            message_store=env["messages"], connection_manager=env["manager"],
        )
        await record_answer(
            env["chat_id"], user_id=1, question_id=env["q1"]["id"], chosen_index=0, **_kwargs(env)
        )
        await record_answer(
            env["chat_id"], user_id=2, question_id=env["q1"]["id"], chosen_index=1, **_kwargs(env)
        )
        await record_answer(
            env["chat_id"], user_id=1, question_id=env["q2"]["id"], chosen_index=1, **_kwargs(env)
        )
        await record_answer(
            env["chat_id"], user_id=2, question_id=env["q2"]["id"], chosen_index=1, **_kwargs(env)
        )

        finished_frames = [m for _, m in env["manager"].sent if m["type"] == "quiz_finished"]
        assert len(finished_frames) == 1
        assert finished_frames[0]["total_questions"] == 2
        assert finished_frames[0]["scores"] == {1: 2, 2: 1}

        session = env["sessions"].get(env["chat_id"])
        assert session["status"] == "finished"

    @pytest.mark.asyncio
    async def test_is_idempotent_no_op_when_no_active_session(self, env):
        result = await advance_question(
            env["chat_id"],
            session_store=env["sessions"],
            question_store=env["questions"],
            attempt_store=env["attempts"],
            message_store=env["messages"],
            connection_manager=env["manager"],
        )
        assert result is None
        assert env["manager"].sent == []
