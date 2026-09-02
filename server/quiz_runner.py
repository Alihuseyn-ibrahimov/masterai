"""Quiz orkestrasiyası — sessiya başlatma, cavab qəbulu, növbə keçidi.

Kritik bölmə (`record_answer`-də cavabı yaz + hamı cavablayıbmı yoxla)
tamamilə sinxron sqlite çağırışlarından ibarətdir, arada `await` yoxdur —
bu, əlavə kilid olmadan yarış vəziyyətinin qarşısını alır (bax spec,
bölmə 2). Store qatı gələcəkdə async DB driverinə keçsə, bu invariantı
qorumaq üçün açıq kilid (məs. per-chat `asyncio.Lock`) əlavə edilməlidir.
"""

from __future__ import annotations

import asyncio
import json

DEFAULT_QUESTION_TIMEOUT_SECONDS = 45


class QuizError(Exception):
    """Ümumi quiz xətası (aktiv sessiya yoxdur, material sualsızdır və s.)."""


class NotCurrentQuestion(Exception):
    """Cavab hazırkı aktiv sualdan fərqli (köhnə) sual üçündür."""


class AlreadyAnswered(Exception):
    """İstifadəçi bu sualı artıq cavablayıb."""


def _question_payload(question: dict) -> dict:
    # correct_index/explanation QƏSDƏN yoxdur — cavab sızmasın (bax spec, bölmə 5).
    return {
        "question_id": question["id"],
        "question": question["question"],
        "options": question["options"],
    }


async def _post_question(chat_id: int, question: dict, *, message_store, connection_manager) -> dict:
    payload = _question_payload(question)
    message = message_store.create(
        chat_id, None, "quiz_question", json.dumps(payload, ensure_ascii=False)
    )
    await connection_manager.broadcast(
        chat_id, {"type": "quiz_question", **payload, "message_id": message["id"]}
    )
    return message


async def start_quiz(
    chat_id: int,
    material_id: int,
    *,
    question_store,
    session_store,
    message_store,
    connection_manager,
) -> dict:
    questions = question_store.list_by_material(material_id)
    if not questions:
        raise QuizError(f"material_id={material_id} üçün hazır sual yoxdur")

    question_ids = [q["id"] for q in questions]
    session = session_store.create(chat_id, material_id, question_ids)
    await _post_question(
        chat_id, questions[0], message_store=message_store, connection_manager=connection_manager
    )
    return session


async def record_answer(
    chat_id: int,
    user_id: int,
    question_id: int,
    chosen_index: int,
    *,
    session_store,
    question_store,
    attempt_store,
    chat_store,
    message_store,
    connection_manager,
) -> dict:
    session = session_store.get(chat_id)
    if session is None or session["status"] != "active":
        raise QuizError(f"chat_id={chat_id} üçün aktiv quiz yoxdur")

    current_question_id = session["question_ids"][session["current_index"]]
    if question_id != current_question_id:
        raise NotCurrentQuestion(question_id)

    existing = attempt_store.list_by_question(question_id)
    if any(a["user_id"] == user_id for a in existing):
        raise AlreadyAnswered(user_id, question_id)

    question = question_store.get(question_id)
    is_correct = chosen_index == question["correct_index"]
    attempt = attempt_store.create(question_id, user_id, chosen_index, is_correct)

    # Yuxarıdakı bölmədə heç bir `await` yoxdur — bu yoxlama+irəliləmə
    # qərarı digər cavabla eyni vaxtda yarışa girə bilməz (bax modul qeydi).
    answered_user_ids = {a["user_id"] for a in attempt_store.list_by_question(question_id)}
    member_ids = set(chat_store.list_member_ids(chat_id))
    if member_ids and answered_user_ids >= member_ids:
        await advance_question(
            chat_id,
            session_store=session_store,
            question_store=question_store,
            attempt_store=attempt_store,
            message_store=message_store,
            connection_manager=connection_manager,
        )

    return attempt


async def advance_question(
    chat_id: int,
    *,
    session_store,
    question_store,
    attempt_store,
    message_store,
    connection_manager,
) -> dict | None:
    session = session_store.get(chat_id)
    if session is None or session["status"] != "active":
        return None  # artıq bağlanıb/yoxdur — idempotent no-op (timeout-un gec çatması)

    current_question_id = session["question_ids"][session["current_index"]]
    question = question_store.get(current_question_id)
    attempts = attempt_store.list_by_question(current_question_id)

    result_payload = {
        "question_id": current_question_id,
        "correct_index": question["correct_index"],
        "explanation": question["explanation"],
        "answers": [
            {"user_id": a["user_id"], "chosen_index": a["chosen_index"], "is_correct": a["is_correct"]}
            for a in attempts
        ],
    }
    result_message = message_store.create(
        chat_id, None, "quiz_result", json.dumps(result_payload, ensure_ascii=False)
    )
    await connection_manager.broadcast(
        chat_id, {"type": "quiz_result", **result_payload, "message_id": result_message["id"]}
    )

    updated_session = session_store.advance(chat_id)
    if updated_session["status"] == "finished":
        await _post_finish_summary(
            chat_id,
            updated_session,
            attempt_store=attempt_store,
            message_store=message_store,
            connection_manager=connection_manager,
        )
    else:
        next_question = question_store.get(
            updated_session["question_ids"][updated_session["current_index"]]
        )
        await _post_question(
            chat_id, next_question, message_store=message_store, connection_manager=connection_manager
        )

    return updated_session


async def check_timeout(
    chat_id: int,
    expected_index: int,
    *,
    session_store,
    question_store,
    attempt_store,
    message_store,
    connection_manager,
    timeout_seconds: float = DEFAULT_QUESTION_TIMEOUT_SECONDS,
) -> dict | None:
    """Sual göndəriləndə fon tapşırığı kimi planlaşdırılır. `timeout_seconds`
    sonra sessiyanın HƏLƏ DƏ `expected_index`-də olduğunu yoxlayır — erkən
    keçid artıq baş vermişsə (bax `record_answer`) sakitcə heç nə etmir."""
    await asyncio.sleep(timeout_seconds)

    session = session_store.get(chat_id)
    if session is None or session["status"] != "active" or session["current_index"] != expected_index:
        return None

    return await advance_question(
        chat_id,
        session_store=session_store,
        question_store=question_store,
        attempt_store=attempt_store,
        message_store=message_store,
        connection_manager=connection_manager,
    )


async def _post_finish_summary(
    chat_id: int, session: dict, *, attempt_store, message_store, connection_manager
) -> None:
    scores: dict[int, int] = {}
    for question_id in session["question_ids"]:
        for attempt in attempt_store.list_by_question(question_id):
            if attempt["is_correct"]:
                scores[attempt["user_id"]] = scores.get(attempt["user_id"], 0) + 1

    payload = {"total_questions": len(session["question_ids"]), "scores": scores}
    message = message_store.create(
        chat_id, None, "system", json.dumps({"kind": "quiz_finished", **payload}, ensure_ascii=False)
    )
    await connection_manager.broadcast(
        chat_id, {"type": "quiz_finished", **payload, "message_id": message["id"]}
    )
