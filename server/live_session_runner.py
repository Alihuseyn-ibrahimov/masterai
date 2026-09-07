"""Canlı sinif sessiyası orkestrasiyası — qoşulma, başlatma, cavab qəbulu,
növbə keçidi. `quiz_runner.py`-nin naxışını təkrarlayır, amma çat/mesaj
sisteminə bağlı deyil (bax dizayn sənədi).

Sinxronizasiya qeydi `quiz_runner.py`-nin modul qeydinin eynisidir: real
(tək prosesli, tək event loop) `uvicorn` deploy-unda əlavə kilid lazım
deyil (kök səbəb Store qatındadır), test mühitində isə Starlette
`TestClient`-in hər WS bağlantısını ayrı thread-də işlətməsi üçün hər
Store öz daxili kilidini işlədir.
"""

from __future__ import annotations

import asyncio
import json

DEFAULT_QUESTION_TIMEOUT_SECONDS = 20


class LiveSessionError(Exception):
    """Ümumi canlı sessiya xətası."""


class SessionNotFound(LiveSessionError):
    """Bu PIN-ə uyğun bitməmiş sessiya yoxdur."""


class SessionNotJoinable(LiveSessionError):
    """Sessiya artıq başlayıb/bitib — yeni iştirakçı qəbul etmir."""


class NotCurrentQuestion(LiveSessionError):
    """Cavab hazırkı aktiv sualdan fərqli (köhnə) sual üçündür."""


class AlreadyAnswered(LiveSessionError):
    """İştirakçı bu sualı artıq cavablayıb."""


def _question_payload(index: int, total: int, question: dict) -> dict:
    # correct_index/explanation QƏSDƏN yoxdur — cavab sızmasın (bax spec).
    return {
        "index": index,
        "total": total,
        "question": question["question"],
        "options": question["options"],
    }


async def _broadcast_question(
    session_id: int, index: int, questions: list[dict], *, connection_manager
) -> None:
    payload = _question_payload(index, len(questions), questions[index])
    await connection_manager.broadcast_host(session_id, {"type": "question", **payload})
    await connection_manager.broadcast_players(session_id, {"type": "question", **payload})


def _leaderboard(session_id: int, *, session_store) -> list[dict]:
    scores = session_store.compute_scores(session_id)
    names = {p["id"]: p["display_name"] for p in session_store.list_participants(session_id)}
    rows = [
        {"participant_id": pid, "display_name": names.get(pid, "?"), "score": score}
        for pid, score in scores.items()
    ]
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows


def compute_report(session_id: int, *, session_store, question_set_store) -> dict:
    """Sessiya sonu hesabatı: yekun sıralama + sual-sual təhlil (ən çox
    seçilən səhv variant daxil — "sinif harada çətinlik çəkir" göstəricisi,
    bax dizayn sənədi, bölmə 5). Sessiya bitəndə `advance_question`
    tərəfindən bir dəfə hesablanıb `report_json`-a keşlənir."""
    session = session_store.get(session_id)
    questions = question_set_store.list_questions(session["question_set_id"])

    scores = session_store.compute_scores(session_id)
    participants = session_store.list_participants(session_id)
    ranking_rows = sorted(
        (
            {"participant_id": p["id"], "display_name": p["display_name"], "score": scores.get(p["id"], 0)}
            for p in participants
        ),
        key=lambda r: r["score"],
        reverse=True,
    )
    rankings = [{"rank": i + 1, **row} for i, row in enumerate(ranking_rows)]

    per_question = []
    for index, question in enumerate(questions):
        answers = session_store.list_answers_for_question(session_id, index)
        correct_count = sum(1 for a in answers if a["is_correct"])
        wrong_counts: dict[int, int] = {}
        for a in answers:
            if not a["is_correct"]:
                wrong_counts[a["chosen_index"]] = wrong_counts.get(a["chosen_index"], 0) + 1
        most_common_wrong_index = max(wrong_counts, key=wrong_counts.get) if wrong_counts else None
        per_question.append(
            {
                "index": index,
                "question": question["question"],
                "correct_index": question["correct_index"],
                "correct_count": correct_count,
                "total_answers": len(answers),
                "most_common_wrong_index": most_common_wrong_index,
            }
        )

    return {
        "session_id": session_id,
        "total_questions": len(questions),
        "rankings": rankings,
        "per_question": per_question,
    }


async def join_session(
    pin: str, display_name: str, *, session_store, connection_manager
) -> tuple[dict, dict]:
    session = session_store.get_by_pin(pin)
    if session is None:
        raise SessionNotFound(pin)
    if session["status"] != "waiting":
        raise SessionNotJoinable(pin)

    participant = session_store.add_participant(session["id"], display_name)
    count = session_store.count_participants(session["id"])
    await connection_manager.broadcast_host(
        session["id"],
        {
            "type": "participant_joined",
            "participant_id": participant["id"],
            "display_name": display_name,
            "count": count,
        },
    )
    return session, participant


async def start_session(
    session_id: int, *, session_store, question_set_store, connection_manager
) -> dict:
    session = session_store.get(session_id)
    if session is None:
        raise SessionNotFound(session_id)
    if session["status"] != "waiting":
        raise LiveSessionError("Sessiya artıq başlayıb")

    questions = question_set_store.list_questions(session["question_set_id"])
    if not questions:
        raise LiveSessionError("Sual bankında sual yoxdur")

    session_store.set_status(session_id, "active")
    await _broadcast_question(session_id, 0, questions, connection_manager=connection_manager)
    return session_store.get(session_id)


async def record_answer(
    session_id: int, participant_id: int, question_index: int, chosen_index: int,
    *, session_store, question_set_store, connection_manager,
) -> dict:
    session = session_store.get(session_id)
    if session is None or session["status"] != "active":
        raise LiveSessionError(f"session_id={session_id} üçün aktiv sessiya yoxdur")

    if question_index != session["current_question_index"]:
        raise NotCurrentQuestion(question_index)
    if session_store.has_answered(session_id, participant_id, question_index):
        raise AlreadyAnswered(participant_id, question_index)

    questions = question_set_store.list_questions(session["question_set_id"])
    question = questions[question_index]
    is_correct = chosen_index == question["correct_index"]
    answer = session_store.record_answer(
        session_id, participant_id, question_index, chosen_index, is_correct
    )

    answered_count = len(session_store.list_answers_for_question(session_id, question_index))
    total_participants = session_store.count_participants(session_id)
    await connection_manager.broadcast_host(
        session_id,
        {
            "type": "answer_progress",
            "answered_count": answered_count,
            "total_participants": total_participants,
        },
    )

    if total_participants and answered_count >= total_participants:
        await advance_question(
            session_id,
            expected_index=question_index,
            session_store=session_store,
            question_set_store=question_set_store,
            connection_manager=connection_manager,
        )

    return answer


async def advance_question(
    session_id: int, *, expected_index: int | None = None,
    session_store, question_set_store, connection_manager,
) -> dict | None:
    """Cari sualı bağlayıb növbətiyə keçir (və ya sessiyanı bitirir).

    `expected_index` verilibsə, sessiya HƏLƏ DƏ həmin indeksdə olmalıdır
    — əks halda (başqa çağırış artıq irəli aparıbsa) sakitcə no-op edilir
    (mövcud `quiz_runner.advance_question`-un eyni idempotentlik naxışı,
    `check_timeout`-un gecikmiş atəşinin erkən keçiddən sonra heç nə
    etməməsi üçün)."""
    session = session_store.get(session_id)
    if session is None or session["status"] != "active":
        return None
    if expected_index is not None and session["current_question_index"] != expected_index:
        return None

    questions = question_set_store.list_questions(session["question_set_id"])
    index = session["current_question_index"]
    question = questions[index]
    answers = session_store.list_answers_for_question(session_id, index)

    result_payload = {
        "index": index,
        "correct_index": question["correct_index"],
        "explanation": question["explanation"],
        "answered_count": len(answers),
        "leaderboard": _leaderboard(session_id, session_store=session_store)[:5],
    }
    await connection_manager.broadcast_host(session_id, {"type": "result", **result_payload})
    await connection_manager.broadcast_players(session_id, {"type": "result", **result_payload})

    updated = session_store.advance(session_id)
    if updated["current_question_index"] >= len(questions):
        session_store.set_status(session_id, "finished")
        report = compute_report(session_id, session_store=session_store, question_set_store=question_set_store)
        session_store.save_report(session_id, json.dumps(report, ensure_ascii=False))
        finish_payload = {
            "total_questions": len(questions),
            "leaderboard": _leaderboard(session_id, session_store=session_store),
        }
        await connection_manager.broadcast_host(session_id, {"type": "finished", **finish_payload})
        await connection_manager.broadcast_players(session_id, {"type": "finished", **finish_payload})
        return session_store.get(session_id)

    await _broadcast_question(
        session_id, updated["current_question_index"], questions, connection_manager=connection_manager
    )
    return updated


async def check_timeout(
    session_id: int, expected_index: int, *, session_store, question_set_store,
    connection_manager, timeout_seconds: float = DEFAULT_QUESTION_TIMEOUT_SECONDS,
) -> dict | None:
    """Sual göndəriləndə fon tapşırığı kimi planlaşdırılır. `timeout_seconds`
    sonra `advance_question`-u `expected_index` ilə çağırır — müəllim
    "Növbəti sual" ilə artıq irəli aparıbsa, `advance_question`-un öz
    yoxlaması sakitcə no-op edir."""
    await asyncio.sleep(timeout_seconds)
    return await advance_question(
        session_id,
        expected_index=expected_index,
        session_store=session_store,
        question_set_store=question_set_store,
        connection_manager=connection_manager,
    )
