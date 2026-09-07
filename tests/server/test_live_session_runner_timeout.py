import pytest

from pipeline.models import MCQQuestion
from server.live_session_runner import check_timeout, join_session, record_answer, start_session
from server.live_session_store import LiveSessionStore
from server.question_set_store import QuestionSetStore

_TEST_TIMEOUT = 0.2


class FakeConnectionManager:
    def __init__(self):
        self.host_sent: list[tuple[int, dict]] = []
        self.player_sent: list[tuple[int, dict]] = []

    async def broadcast_host(self, session_id: int, message: dict) -> None:
        self.host_sent.append((session_id, message))

    async def broadcast_players(self, session_id: int, message: dict) -> None:
        self.player_sent.append((session_id, message))


@pytest.fixture
def env(tmp_path):
    question_sets = QuestionSetStore(path=str(tmp_path / "question_sets.db"))
    sessions = LiveSessionStore(path=str(tmp_path / "live_sessions.db"))
    manager = FakeConnectionManager()

    qs = question_sets.create(
        subject="mentiq", title="Test", material_kind="link",
        material_location="https://x.az", created_by=1,
    )
    question_sets.mark_ready(qs["id"])
    question_sets.add_question(
        qs["id"],
        MCQQuestion(question="Sual 1?", options=["A", "B", "C", "D", "E"], correct_index=0, explanation="izah 1"),
    )
    question_sets.add_question(
        qs["id"],
        MCQQuestion(question="Sual 2?", options=["A", "B", "C", "D", "E"], correct_index=1, explanation="izah 2"),
    )

    return {"question_sets": question_sets, "sessions": sessions, "manager": manager, "question_set_id": qs["id"]}


def _kwargs(env):
    return dict(session_store=env["sessions"], question_set_store=env["question_sets"], connection_manager=env["manager"])


@pytest.mark.asyncio
async def test_advances_after_timeout_when_nobody_answered(env):
    session = env["sessions"].create_session(env["question_set_id"])
    await start_session(session["id"], **_kwargs(env))

    await check_timeout(session["id"], expected_index=0, timeout_seconds=_TEST_TIMEOUT, **_kwargs(env))

    updated = env["sessions"].get(session["id"])
    assert updated["current_question_index"] == 1

    types = [m["type"] for _, m in env["manager"].player_sent]
    assert types == ["question", "result", "question"]
    result_frame = env["manager"].player_sent[1][1]
    assert result_frame["answered_count"] == 0


@pytest.mark.asyncio
async def test_is_noop_when_question_already_advanced_early(env):
    session = env["sessions"].create_session(env["question_set_id"])
    _, p1 = await join_session(session["pin"], "Əli", session_store=env["sessions"], connection_manager=env["manager"])
    await start_session(session["id"], **_kwargs(env))

    # tək iştirakçı dərhal cavablayır — erkən keçid baş verməlidir
    await record_answer(session["id"], p1["id"], 0, chosen_index=0, **_kwargs(env))

    updated = env["sessions"].get(session["id"])
    assert updated["current_question_index"] == 1
    sent_count_before_timeout = len(env["manager"].player_sent)

    # 0-cı sual üçün planlaşdırılmış timeout indi çatır — artıq keçilib, no-op
    result = await check_timeout(session["id"], expected_index=0, timeout_seconds=_TEST_TIMEOUT, **_kwargs(env))

    assert result is None
    assert len(env["manager"].player_sent) == sent_count_before_timeout


@pytest.mark.asyncio
async def test_is_noop_when_session_already_finished(env):
    session = env["sessions"].create_session(env["question_set_id"])
    await start_session(session["id"], **_kwargs(env))

    await check_timeout(session["id"], expected_index=0, timeout_seconds=_TEST_TIMEOUT, **_kwargs(env))
    await check_timeout(session["id"], expected_index=1, timeout_seconds=_TEST_TIMEOUT, **_kwargs(env))

    updated = env["sessions"].get(session["id"])
    assert updated["status"] == "finished"

    sent_count_before = len(env["manager"].player_sent)
    result = await check_timeout(session["id"], expected_index=1, timeout_seconds=_TEST_TIMEOUT, **_kwargs(env))

    assert result is None
    assert len(env["manager"].player_sent) == sent_count_before
