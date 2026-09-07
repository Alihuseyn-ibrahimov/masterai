import pytest

from server.live_session_runner import (
    AlreadyAnswered,
    LiveSessionError,
    NotCurrentQuestion,
    SessionNotFound,
    SessionNotJoinable,
    advance_question,
    join_session,
    record_answer,
    start_session,
)
from server.live_session_store import LiveSessionStore
from server.question_set_store import QuestionSetStore


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
    from pipeline.models import MCQQuestion

    q1 = question_sets.add_question(
        qs["id"],
        MCQQuestion(question="Sual 1?", options=["A", "B", "C", "D", "E"], correct_index=0, explanation="izah 1"),
    )
    q2 = question_sets.add_question(
        qs["id"],
        MCQQuestion(question="Sual 2?", options=["A", "B", "C", "D", "E"], correct_index=1, explanation="izah 2"),
    )

    return {
        "question_sets": question_sets,
        "sessions": sessions,
        "manager": manager,
        "question_set_id": qs["id"],
        "q1": q1,
        "q2": q2,
    }


def _kwargs(env, **overrides):
    base = dict(
        session_store=env["sessions"],
        question_set_store=env["question_sets"],
        connection_manager=env["manager"],
    )
    base.update(overrides)
    return base


class TestJoinSession:
    @pytest.mark.asyncio
    async def test_join_creates_participant_and_notifies_host(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        _, participant = await join_session(
            session["pin"], "Əli", session_store=env["sessions"], connection_manager=env["manager"]
        )

        assert participant["display_name"] == "Əli"
        assert len(env["manager"].host_sent) == 1
        _, payload = env["manager"].host_sent[0]
        assert payload["type"] == "participant_joined"
        assert payload["display_name"] == "Əli"
        assert payload["count"] == 1

    @pytest.mark.asyncio
    async def test_raises_for_unknown_pin(self, env):
        with pytest.raises(SessionNotFound):
            await join_session("000000", "Əli", session_store=env["sessions"], connection_manager=env["manager"])

    @pytest.mark.asyncio
    async def test_raises_when_session_already_active(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        await start_session(session["id"], **_kwargs(env))
        with pytest.raises(SessionNotJoinable):
            await join_session(session["pin"], "Əli", session_store=env["sessions"], connection_manager=env["manager"])


class TestStartSession:
    @pytest.mark.asyncio
    async def test_broadcasts_first_question_to_host_and_players(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        updated = await start_session(session["id"], **_kwargs(env))

        assert updated["status"] == "active"
        assert len(env["manager"].host_sent) == 1
        assert len(env["manager"].player_sent) == 1
        host_payload = env["manager"].host_sent[0][1]
        player_payload = env["manager"].player_sent[0][1]
        assert host_payload["type"] == "question"
        assert host_payload["question"] == "Sual 1?"
        assert "correct_index" not in host_payload
        assert player_payload == host_payload

    @pytest.mark.asyncio
    async def test_raises_for_unknown_session(self, env):
        with pytest.raises(SessionNotFound):
            await start_session(999, **_kwargs(env))

    @pytest.mark.asyncio
    async def test_raises_when_already_started(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        await start_session(session["id"], **_kwargs(env))
        with pytest.raises(LiveSessionError):
            await start_session(session["id"], **_kwargs(env))

    @pytest.mark.asyncio
    async def test_raises_when_question_set_empty(self, env):
        empty_qs = env["question_sets"].create(
            subject="mentiq", title="Boş", material_kind="link",
            material_location="https://y.az", created_by=1,
        )
        env["question_sets"].mark_ready(empty_qs["id"])
        session = env["sessions"].create_session(empty_qs["id"])
        with pytest.raises(LiveSessionError):
            await start_session(session["id"], **_kwargs(env))


class TestRecordAnswer:
    @pytest.mark.asyncio
    async def test_computes_correctness(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        _, p1 = await join_session(session["pin"], "Əli", session_store=env["sessions"], connection_manager=env["manager"])
        await start_session(session["id"], **_kwargs(env))

        answer = await record_answer(session["id"], p1["id"], 0, chosen_index=0, **_kwargs(env))
        assert answer["is_correct"] is True

    @pytest.mark.asyncio
    async def test_raises_for_no_active_session(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        with pytest.raises(LiveSessionError):
            await record_answer(session["id"], 1, 0, chosen_index=0, **_kwargs(env))

    @pytest.mark.asyncio
    async def test_raises_for_stale_question_index(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        await start_session(session["id"], **_kwargs(env))
        with pytest.raises(NotCurrentQuestion):
            await record_answer(session["id"], 1, 1, chosen_index=0, **_kwargs(env))

    @pytest.mark.asyncio
    async def test_raises_for_duplicate_answer(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        await start_session(session["id"], **_kwargs(env))
        await record_answer(session["id"], 1, 0, chosen_index=0, **_kwargs(env))
        with pytest.raises(AlreadyAnswered):
            await record_answer(session["id"], 1, 0, chosen_index=1, **_kwargs(env))

    @pytest.mark.asyncio
    async def test_all_participants_answered_triggers_immediate_advance(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        _, p1 = await join_session(session["pin"], "Əli", session_store=env["sessions"], connection_manager=env["manager"])
        _, p2 = await join_session(session["pin"], "Vəli", session_store=env["sessions"], connection_manager=env["manager"])
        await start_session(session["id"], **_kwargs(env))

        await record_answer(session["id"], p1["id"], 0, chosen_index=0, **_kwargs(env))
        # hələ p2 cavablamayıb — irəliləmə olmamalıdır
        result_events = [m for _, m in env["manager"].player_sent if m["type"] == "result"]
        assert result_events == []

        await record_answer(session["id"], p2["id"], 0, chosen_index=1, **_kwargs(env))
        # indi hamı cavablayıb — result + növbəti sual gəlməlidir
        types = [m["type"] for _, m in env["manager"].player_sent]
        assert types == ["question", "result", "question"]
        assert env["manager"].player_sent[2][1]["question"] == "Sual 2?"

        updated_session = env["sessions"].get(session["id"])
        assert updated_session["current_question_index"] == 1
        assert updated_session["status"] == "active"


class TestAdvanceQuestion:
    @pytest.mark.asyncio
    async def test_last_question_finishes_with_leaderboard(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        _, p1 = await join_session(session["pin"], "Əli", session_store=env["sessions"], connection_manager=env["manager"])
        _, p2 = await join_session(session["pin"], "Vəli", session_store=env["sessions"], connection_manager=env["manager"])
        await start_session(session["id"], **_kwargs(env))

        await record_answer(session["id"], p1["id"], 0, chosen_index=0, **_kwargs(env))
        await record_answer(session["id"], p2["id"], 0, chosen_index=1, **_kwargs(env))
        await record_answer(session["id"], p1["id"], 1, chosen_index=1, **_kwargs(env))
        await record_answer(session["id"], p2["id"], 1, chosen_index=1, **_kwargs(env))

        finished_frames = [m for _, m in env["manager"].player_sent if m["type"] == "finished"]
        assert len(finished_frames) == 1
        assert finished_frames[0]["total_questions"] == 2
        leaderboard = {row["participant_id"]: row["score"] for row in finished_frames[0]["leaderboard"]}
        assert leaderboard == {p1["id"]: 2, p2["id"]: 1}

        updated_session = env["sessions"].get(session["id"])
        assert updated_session["status"] == "finished"

    @pytest.mark.asyncio
    async def test_is_idempotent_no_op_when_no_active_session(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        result = await advance_question(session["id"], **_kwargs(env))
        assert result is None
        assert env["manager"].host_sent == []
        assert env["manager"].player_sent == []

    @pytest.mark.asyncio
    async def test_expected_index_guards_against_double_advance(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        await start_session(session["id"], **_kwargs(env))
        # 0-cı sual üçün irəliləmə (müəllimin "Növbəti sual"ı)
        await advance_question(session["id"], expected_index=0, **_kwargs(env))
        sent_count_before = len(env["manager"].player_sent)

        # gecikmiş timeout HƏLƏ DƏ 0-cı indeksi gözləyir — artıq keçilib, no-op
        result = await advance_question(session["id"], expected_index=0, **_kwargs(env))
        assert result is None
        assert len(env["manager"].player_sent) == sent_count_before
