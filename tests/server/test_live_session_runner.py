import json

import pytest

from server.live_session_runner import (
    LiveSessionError,
    NotCurrentQuestion,
    SessionNotFound,
    SessionNotJoinable,
    SessionTimeExpired,
    compute_report,
    join_session,
    record_answer,
    request_next,
    start_session,
)
from server.live_session_store import LiveSessionStore
from server.question_set_store import QuestionSetStore


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


def _direct_messages(env, participant_id):
    return [m for _, pid, m in env["manager"].direct_sent if pid == participant_id]


class TestJoinSession:
    @pytest.mark.asyncio
    async def test_join_creates_participant_and_notifies_host(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        _, participant = await join_session(session["id"], "Əli", user_id=1, session_store=env["sessions"], connection_manager=env["manager"]
        )

        assert participant["display_name"] == "Əli"
        assert len(env["manager"].host_sent) == 1
        _, payload = env["manager"].host_sent[0]
        assert payload["type"] == "participant_joined"
        assert payload["display_name"] == "Əli"
        assert payload["count"] == 1

    @pytest.mark.asyncio
    async def test_participant_is_linked_to_the_account(self, env):
        """`user_id` artıq MƏCBURİDİR (Faza 4) — anonim yol silindi.
        Fərdi tarixçə buna söykənir."""
        session = env["sessions"].create_session(env["question_set_id"])
        _, participant = await join_session(
            session["id"], "Aygün", user_id=42,
            session_store=env["sessions"], connection_manager=env["manager"],
        )
        assert participant["user_id"] == 42

    @pytest.mark.asyncio
    async def test_rejoin_reuses_the_participant_and_does_not_renotify(self, env):
        """REAL BUG (sessiya #31): tələbə səhifəni yeniləyəndə host-a
        ikinci `participant_joined` gedirdi və host siyahısında eyni
        adam iki dəfə görünürdü (siyahı hadisələri sadəcə `concat`
        edir). Təkrar qoşulma yeni hadisə DEYİL."""
        session = env["sessions"].create_session(env["question_set_id"])
        _, first = await join_session(
            session["id"], "Amil", user_id=5,
            session_store=env["sessions"], connection_manager=env["manager"],
        )
        _, again = await join_session(
            session["id"], "Amil", user_id=5,
            session_store=env["sessions"], connection_manager=env["manager"],
        )

        assert again["id"] == first["id"]
        assert env["sessions"].count_participants(session["id"]) == 1
        assert len(env["manager"].host_sent) == 1

    @pytest.mark.asyncio
    async def test_raises_for_unknown_session(self, env):
        with pytest.raises(SessionNotFound):
            await join_session(
                9999, "Əli", user_id=1,
                session_store=env["sessions"], connection_manager=env["manager"],
            )

    @pytest.mark.asyncio
    async def test_joining_an_active_session_is_ALLOWED(self, env):
        """GEC QOŞULMA (Faza 3 qərarı). Əvvəl burada `LiveSessionError`
        gözlənilirdi — real sinifdə tələbə gecikir, telefonu söndürülür,
        dərsə sonradan qoşulur, ona görə həmin davranış dəyişdirildi."""
        session = env["sessions"].create_session(env["question_set_id"])
        await start_session(session["id"], 180, **_kwargs(env))

        _, participant = await join_session(
            session["id"], "Gecikən", user_id=7,
            session_store=env["sessions"], connection_manager=env["manager"],
        )
        assert participant["id"] is not None

    @pytest.mark.asyncio
    async def test_joining_a_finished_session_raises(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        env["sessions"].set_status(session["id"], "finished")
        with pytest.raises(SessionNotJoinable):
            await join_session(
                session["id"], "Əli", user_id=1,
                session_store=env["sessions"], connection_manager=env["manager"],
            )


class TestStartSession:
    @pytest.mark.asyncio
    async def test_broadcasts_started_to_host_and_first_question_to_players(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        updated = await start_session(session["id"], 180, **_kwargs(env))

        assert updated["status"] == "active"
        assert updated["duration_seconds"] == 180
        assert updated["started_at"] is not None

        assert len(env["manager"].host_sent) == 1
        host_payload = env["manager"].host_sent[0][1]
        assert host_payload == {"type": "started", "duration_seconds": 180, "total_questions": 2}

        assert len(env["manager"].player_sent) == 1
        player_payload = env["manager"].player_sent[0][1]
        assert player_payload["type"] == "question"
        assert player_payload["question"] == "Sual 1?"
        assert "correct_index" not in player_payload
        assert player_payload["remaining_seconds"] == pytest.approx(180, abs=1)

    @pytest.mark.asyncio
    async def test_raises_for_unknown_session(self, env):
        with pytest.raises(SessionNotFound):
            await start_session(999, 180, **_kwargs(env))

    @pytest.mark.asyncio
    async def test_raises_when_already_started(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        await start_session(session["id"], 180, **_kwargs(env))
        with pytest.raises(LiveSessionError):
            await start_session(session["id"], 180, **_kwargs(env))

    @pytest.mark.asyncio
    async def test_raises_when_question_set_empty(self, env):
        empty_qs = env["question_sets"].create(
            subject="mentiq", title="Boş", material_kind="link",
            material_location="https://y.az", created_by=1,
        )
        env["question_sets"].mark_ready(empty_qs["id"])
        session = env["sessions"].create_session(empty_qs["id"])
        with pytest.raises(LiveSessionError):
            await start_session(session["id"], 180, **_kwargs(env))


class TestRecordAnswer:
    @pytest.mark.asyncio
    async def test_computes_correctness_and_sends_result_only_to_answerer(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        _, p1 = await join_session(session["id"], "Əli", user_id=1, session_store=env["sessions"], connection_manager=env["manager"])
        _, p2 = await join_session(session["id"], "Vəli", user_id=2, session_store=env["sessions"], connection_manager=env["manager"])
        await start_session(session["id"], 180, **_kwargs(env))

        answer = await record_answer(session["id"], p1["id"], 0, chosen_index=0, **_kwargs(env))
        assert answer["is_correct"] is True

        p1_messages = _direct_messages(env, p1["id"])
        assert len(p1_messages) == 1
        assert p1_messages[0]["type"] == "result"
        assert p1_messages[0]["is_correct"] is True
        assert p1_messages[0]["correct_index"] == 0
        assert p1_messages[0]["explanation"] == "izah 1"

        # p2 hələ cavablamayıb — heç bir "result" almamalıdır (broadcast YOXDUR)
        assert _direct_messages(env, p2["id"]) == []
        assert [m for _, m in env["manager"].player_sent if m["type"] == "result"] == []

    @pytest.mark.asyncio
    async def test_notifies_host_of_this_participants_progress(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        _, p1 = await join_session(session["id"], "Əli", user_id=1, session_store=env["sessions"], connection_manager=env["manager"])
        await start_session(session["id"], 180, **_kwargs(env))
        await record_answer(session["id"], p1["id"], 0, chosen_index=0, **_kwargs(env))

        progress = [m for _, m in env["manager"].host_sent if m["type"] == "participant_progress"]
        assert progress == [
            {"type": "participant_progress", "participant_id": p1["id"], "answered_count": 1, "total_questions": 2}
        ]

    @pytest.mark.asyncio
    async def test_raises_for_no_active_session(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        with pytest.raises(LiveSessionError):
            await record_answer(session["id"], 1, 0, chosen_index=0, **_kwargs(env))

    @pytest.mark.asyncio
    async def test_raises_when_question_index_does_not_match_own_progress(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        _, p1 = await join_session(session["id"], "Əli", user_id=1, session_store=env["sessions"], connection_manager=env["manager"])
        await start_session(session["id"], 180, **_kwargs(env))
        with pytest.raises(NotCurrentQuestion):
            await record_answer(session["id"], p1["id"], 1, chosen_index=0, **_kwargs(env))

    @pytest.mark.asyncio
    async def test_participants_progress_independently(self, env):
        """Fərdi tempo — p1 hər ikisini cavablaya bilər, p2 hələ 0-cıda
        qalsa da bu, p1-in irəliləməsinə mane olmur (köhnə sinxron model
        ləğv olunub)."""
        session = env["sessions"].create_session(env["question_set_id"])
        _, p1 = await join_session(session["id"], "Əli", user_id=1, session_store=env["sessions"], connection_manager=env["manager"])
        _, p2 = await join_session(session["id"], "Vəli", user_id=2, session_store=env["sessions"], connection_manager=env["manager"])
        await start_session(session["id"], 180, **_kwargs(env))

        await record_answer(session["id"], p1["id"], 0, chosen_index=0, **_kwargs(env))
        await request_next(session["id"], p1["id"], **_kwargs(env))
        # p1 artıq 1-ci sualdadır, p2 hələ 0-cıda — hər ikisi öz sürəti ilə davam edə bilməlidir
        answer = await record_answer(session["id"], p1["id"], 1, chosen_index=1, **_kwargs(env))
        assert answer["is_correct"] is True
        # p2 hələ 0-cı sualı cavablaya bilməlidir (heç kim onu qabaqlamayıb)
        answer2 = await record_answer(session["id"], p2["id"], 0, chosen_index=0, **_kwargs(env))
        assert answer2["is_correct"] is True

    @pytest.mark.asyncio
    async def test_raises_session_time_expired(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        _, p1 = await join_session(session["id"], "Əli", user_id=1, session_store=env["sessions"], connection_manager=env["manager"])
        await start_session(session["id"], 0, **_kwargs(env))  # 0 saniyəlik büdcə — dərhal bitmiş sayılır

        with pytest.raises(SessionTimeExpired):
            await record_answer(session["id"], p1["id"], 0, chosen_index=0, **_kwargs(env))


class TestRequestNext:
    @pytest.mark.asyncio
    async def test_sends_own_next_question(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        _, p1 = await join_session(session["id"], "Əli", user_id=1, session_store=env["sessions"], connection_manager=env["manager"])
        await start_session(session["id"], 180, **_kwargs(env))
        await record_answer(session["id"], p1["id"], 0, chosen_index=0, **_kwargs(env))

        await request_next(session["id"], p1["id"], **_kwargs(env))

        messages = _direct_messages(env, p1["id"])
        question_messages = [m for m in messages if m["type"] == "question"]
        assert len(question_messages) == 1
        assert question_messages[0]["index"] == 1
        assert question_messages[0]["question"] == "Sual 2?"

    @pytest.mark.asyncio
    async def test_early_finisher_sees_personal_result_immediately_without_full_leaderboard(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        _, p1 = await join_session(session["id"], "Əli", user_id=1, session_store=env["sessions"], connection_manager=env["manager"])
        _, p2 = await join_session(session["id"], "Vəli", user_id=2, session_store=env["sessions"], connection_manager=env["manager"])
        await start_session(session["id"], 180, **_kwargs(env))

        await record_answer(session["id"], p1["id"], 0, chosen_index=0, **_kwargs(env))
        await request_next(session["id"], p1["id"], **_kwargs(env))
        await record_answer(session["id"], p1["id"], 1, chosen_index=1, **_kwargs(env))
        # p1 bütün sualları bitirdi, p2 hələ heç birini cavablamayıb
        await request_next(session["id"], p1["id"], **_kwargs(env))

        personal = [m for m in _direct_messages(env, p1["id"]) if m["type"] == "personal_finished"]
        assert personal == [
            {"type": "personal_finished", "correct_count": 2, "answered_count": 2, "total_questions": 2}
        ]
        # sessiya HƏLƏ bitməyib (p2 davam edir) — tam "finished" broadcast YOXDUR
        assert [m for _, m in env["manager"].player_sent if m["type"] == "finished"] == []
        assert env["sessions"].get(session["id"])["status"] == "active"

    @pytest.mark.asyncio
    async def test_session_finishes_with_full_leaderboard_when_all_participants_done(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        _, p1 = await join_session(session["id"], "Əli", user_id=1, session_store=env["sessions"], connection_manager=env["manager"])
        _, p2 = await join_session(session["id"], "Vəli", user_id=2, session_store=env["sessions"], connection_manager=env["manager"])
        await start_session(session["id"], 180, **_kwargs(env))

        await record_answer(session["id"], p1["id"], 0, chosen_index=0, **_kwargs(env))
        await request_next(session["id"], p1["id"], **_kwargs(env))
        await record_answer(session["id"], p1["id"], 1, chosen_index=1, **_kwargs(env))
        await request_next(session["id"], p1["id"], **_kwargs(env))  # p1 fərdi bitir, sessiya hələ bitmir

        await record_answer(session["id"], p2["id"], 0, chosen_index=1, **_kwargs(env))
        await request_next(session["id"], p2["id"], **_kwargs(env))
        await record_answer(session["id"], p2["id"], 1, chosen_index=1, **_kwargs(env))
        await request_next(session["id"], p2["id"], **_kwargs(env))  # indi HAMI bitirdi

        finished_frames = [m for _, m in env["manager"].player_sent if m["type"] == "finished"]
        assert len(finished_frames) == 1
        assert finished_frames[0]["total_questions"] == 2
        leaderboard = {row["participant_id"]: row["score"] for row in finished_frames[0]["leaderboard"]}
        assert leaderboard == {p1["id"]: 2, p2["id"]: 1}

        assert env["sessions"].get(session["id"])["status"] == "finished"
        assert env["sessions"].get(session["id"])["report_json"] is not None

    @pytest.mark.asyncio
    async def test_time_expired_forces_finish_regardless_of_progress(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        _, p1 = await join_session(session["id"], "Əli", user_id=1, session_store=env["sessions"], connection_manager=env["manager"])
        await start_session(session["id"], 0, **_kwargs(env))  # dərhal bitmiş sayılır

        await request_next(session["id"], p1["id"], **_kwargs(env))

        assert env["sessions"].get(session["id"])["status"] == "finished"
        finished_frames = [m for _, m in env["manager"].player_sent if m["type"] == "finished"]
        assert len(finished_frames) == 1

    @pytest.mark.asyncio
    async def test_raises_for_no_active_session(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        with pytest.raises(LiveSessionError):
            await request_next(session["id"], 1, **_kwargs(env))


class TestComputeReport:
    @pytest.mark.asyncio
    async def test_rankings_sorted_by_score_descending(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        _, p1 = await join_session(session["id"], "Əli", user_id=1, session_store=env["sessions"], connection_manager=env["manager"])
        _, p2 = await join_session(session["id"], "Vəli", user_id=2, session_store=env["sessions"], connection_manager=env["manager"])
        await start_session(session["id"], 180, **_kwargs(env))

        await record_answer(session["id"], p1["id"], 0, chosen_index=0, **_kwargs(env))  # düzgün
        await record_answer(session["id"], p2["id"], 0, chosen_index=1, **_kwargs(env))  # səhv
        await request_next(session["id"], p1["id"], **_kwargs(env))
        await request_next(session["id"], p2["id"], **_kwargs(env))
        await record_answer(session["id"], p1["id"], 1, chosen_index=1, **_kwargs(env))  # düzgün
        await record_answer(session["id"], p2["id"], 1, chosen_index=1, **_kwargs(env))  # düzgün

        report = compute_report(session["id"], session_store=env["sessions"], question_set_store=env["question_sets"])

        assert report["session_id"] == session["id"]
        assert report["total_questions"] == 2
        assert report["rankings"] == [
            {"rank": 1, "participant_id": p1["id"], "display_name": "Əli", "score": 2},
            {"rank": 2, "participant_id": p2["id"], "display_name": "Vəli", "score": 1},
        ]

    @pytest.mark.asyncio
    async def test_per_question_reports_correct_count_and_most_common_wrong(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        _, p1 = await join_session(session["id"], "Əli", user_id=1, session_store=env["sessions"], connection_manager=env["manager"])
        _, p2 = await join_session(session["id"], "Vəli", user_id=2, session_store=env["sessions"], connection_manager=env["manager"])
        _, p3 = await join_session(session["id"], "Səbinə", user_id=3, session_store=env["sessions"], connection_manager=env["manager"])
        await start_session(session["id"], 180, **_kwargs(env))

        # 0-cı sual (correct_index=0): p1 düzgün, p2 və p3 eyni səhv variantı (2) seçir
        await record_answer(session["id"], p1["id"], 0, chosen_index=0, **_kwargs(env))
        await record_answer(session["id"], p2["id"], 0, chosen_index=2, **_kwargs(env))
        await record_answer(session["id"], p3["id"], 0, chosen_index=2, **_kwargs(env))

        report = compute_report(session["id"], session_store=env["sessions"], question_set_store=env["question_sets"])
        q0 = report["per_question"][0]

        assert q0["question"] == "Sual 1?"
        assert q0["correct_index"] == 0
        assert q0["correct_count"] == 1
        assert q0["total_answers"] == 3
        assert q0["most_common_wrong_index"] == 2

    @pytest.mark.asyncio
    async def test_report_groups_results_by_difficulty(self, env):
        """Sual 1 «asan», Sual 2 səviyyəsiz (köhnə) — ayrı sətirlərdə."""
        env["question_sets"].update_question(
            env["q1"]["id"], question="Sual 1?", options=["A", "B", "C", "D", "E"],
            correct_index=0, explanation="izah 1", difficulty="asan",
        )
        session = env["sessions"].create_session(env["question_set_id"])
        _, p1 = await join_session(session["id"], "Əli", user_id=1, session_store=env["sessions"], connection_manager=env["manager"])
        _, p2 = await join_session(session["id"], "Vəli", user_id=2, session_store=env["sessions"], connection_manager=env["manager"])
        await start_session(session["id"], 180, **_kwargs(env))
        await record_answer(session["id"], p1["id"], 0, chosen_index=0, **_kwargs(env))
        await record_answer(session["id"], p2["id"], 0, chosen_index=3, **_kwargs(env))

        report = compute_report(session["id"], session_store=env["sessions"], question_set_store=env["question_sets"])
        assert report["per_question"][0]["difficulty"] == "asan"
        assert report["by_difficulty"] == [
            {"level": "asan", "question_count": 1, "correct_count": 1, "total_answers": 2},
            {"level": None, "question_count": 1, "correct_count": 0, "total_answers": 0},
        ]

    @pytest.mark.asyncio
    async def test_most_common_wrong_index_is_none_when_no_wrong_answers(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        _, p1 = await join_session(session["id"], "Əli", user_id=1, session_store=env["sessions"], connection_manager=env["manager"])
        await start_session(session["id"], 180, **_kwargs(env))
        await record_answer(session["id"], p1["id"], 0, chosen_index=0, **_kwargs(env))

        report = compute_report(session["id"], session_store=env["sessions"], question_set_store=env["question_sets"])
        assert report["per_question"][0]["most_common_wrong_index"] is None

    @pytest.mark.asyncio
    async def test_session_finish_caches_report_json(self, env):
        session = env["sessions"].create_session(env["question_set_id"])
        _, p1 = await join_session(session["id"], "Əli", user_id=1, session_store=env["sessions"], connection_manager=env["manager"])
        await start_session(session["id"], 180, **_kwargs(env))

        await record_answer(session["id"], p1["id"], 0, chosen_index=0, **_kwargs(env))
        await request_next(session["id"], p1["id"], **_kwargs(env))
        await record_answer(session["id"], p1["id"], 1, chosen_index=1, **_kwargs(env))
        await request_next(session["id"], p1["id"], **_kwargs(env))

        finished = env["sessions"].get(session["id"])
        assert finished["status"] == "finished"
        assert finished["report_json"] is not None

        cached_report = json.loads(finished["report_json"])
        assert cached_report["total_questions"] == 2
        assert cached_report["rankings"][0]["participant_id"] == p1["id"]
