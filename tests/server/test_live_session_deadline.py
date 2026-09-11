"""Sessiya-səviyyəli ÜMUMİ vaxt limiti (`.planning/2026-09-08-masterai-live-
session-pacing/`) — köhnə sual-üzrə `check_timeout` mexanizminin əvəzinə
gələn TƏK, bir dəfəlik `watch_session_duration`/`force_finish_if_expired`."""

import pytest

from pipeline.models import MCQQuestion
from server.live_session_runner import (
    force_finish_if_expired,
    join_session,
    record_answer,
    start_session,
    watch_session_duration,
)
from server.live_session_store import LiveSessionStore
from server.question_set_store import QuestionSetStore

_TEST_DURATION = 0.2


class FakeConnectionManager:
    def __init__(self):
        self.host_sent: list[tuple[int, dict]] = []
        self.player_sent: list[tuple[int, dict]] = []
        self.direct_sent: list[tuple[int, int, dict]] = []

    async def broadcast_host(self, session_id: int, message: dict) -> None:
        self.host_sent.append((session_id, message))

    async def broadcast_players(self, session_id: int, message: dict) -> None:
        self.player_sent.append((session_id, message))

    async def send_to_player(self, session_id: int, participant_id: int, message: dict) -> None:
        self.direct_sent.append((session_id, participant_id, message))


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
async def test_watch_session_duration_finishes_session_after_sleep_even_if_nobody_answered(env):
    session = env["sessions"].create_session(env["question_set_id"])
    await start_session(session["id"], _TEST_DURATION, **_kwargs(env))

    await watch_session_duration(session["id"], _TEST_DURATION, **_kwargs(env))

    updated = env["sessions"].get(session["id"])
    assert updated["status"] == "finished"
    finished_frames = [m for _, m in env["manager"].player_sent if m["type"] == "finished"]
    assert len(finished_frames) == 1
    assert finished_frames[0]["total_questions"] == 2


@pytest.mark.asyncio
async def test_force_finish_is_noop_when_time_not_yet_expired(env):
    session = env["sessions"].create_session(env["question_set_id"])
    await start_session(session["id"], 180, **_kwargs(env))

    result = await force_finish_if_expired(session["id"], **_kwargs(env))

    assert result is False
    assert env["sessions"].get(session["id"])["status"] == "active"
    assert [m for _, m in env["manager"].player_sent if m["type"] == "finished"] == []


@pytest.mark.asyncio
async def test_force_finish_is_noop_when_already_finished(env):
    session = env["sessions"].create_session(env["question_set_id"])
    await start_session(session["id"], _TEST_DURATION, **_kwargs(env))
    await watch_session_duration(session["id"], _TEST_DURATION, **_kwargs(env))
    sent_count_before = len(env["manager"].player_sent)

    result = await force_finish_if_expired(session["id"], **_kwargs(env))

    assert result is False
    assert len(env["manager"].player_sent) == sent_count_before


@pytest.mark.asyncio
async def test_partial_progress_is_kept_when_time_forces_finish(env):
    """Vaxt bitəndə kim harada qalıbsa sessiya ORADA bağlanır — cavablanmamış
    suallar sadəcə xalsız qalır (bax dizayn qərarı)."""
    session = env["sessions"].create_session(env["question_set_id"])
    _, p1 = await join_session(session["id"], "Əli", user_id=1, session_store=env["sessions"], connection_manager=env["manager"])
    await start_session(session["id"], _TEST_DURATION, **_kwargs(env))
    await record_answer(session["id"], p1["id"], 0, chosen_index=0, **_kwargs(env))  # yalnız 1-ci sualı cavablayır

    await watch_session_duration(session["id"], _TEST_DURATION, **_kwargs(env))

    finished_frames = [m for _, m in env["manager"].player_sent if m["type"] == "finished"]
    leaderboard = {row["participant_id"]: row["score"] for row in finished_frames[0]["leaderboard"]}
    assert leaderboard == {p1["id"]: 1}
