"""Canlı sinif sessiyası orkestrasiyası — qoşulma, başlatma, cavab qəbulu,
fərdi templi sual keçidi. `quiz_runner.py`-nin naxışını təkrarlayır, amma
çat/mesaj sisteminə bağlı deyil (bax dizayn sənədi).

**Fərdi tempo modeli** (bax `.planning/2026-09-08-masterai-live-session-
pacing/`): hər iştirakçı öz sürəti ilə "Növbəti sual" ilə irəliləyir —
sual-üzrə paylaşılan `current_question_index`/timeout ARTIQ YOXDUR.
İştirakçının cari indeksi onun artıq verdiyi cavabların SAYINDAN törəyir
(`LiveSessionStore.count_answers_by_participant`). Yalnız BİR ÜMUMİ
(sessiya-səviyyəli) vaxt büdcəsi var — sessiya başlayanda müəllim təyin
edir, bitəndə kim harada qalıbsa sessiya ORADA bağlanır.

Sinxronizasiya qeydi `quiz_runner.py`-nin modul qeydinin eynisidir: real
(tək prosesli, tək event loop) `uvicorn` deploy-unda əlavə kilid lazım
deyil (kök səbəb Store qatındadır), test mühitində isə Starlette
`TestClient`-in hər WS bağlantısını ayrı thread-də işlətməsi üçün hər
Store öz daxili kilidini işlədir.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

DEFAULT_SESSION_DURATION_SECONDS = 180


class LiveSessionError(Exception):
    """Ümumi canlı sessiya xətası."""


class SessionNotFound(LiveSessionError):
    """Belə sessiya yoxdur."""


class SessionNotJoinable(LiveSessionError):
    """Sessiya BİTİB — yeni iştirakçı qəbul etmir.

    Əvvəl «artıq başlayıb» da bura düşürdü; gec qoşulma açıldıqdan sonra
    (2026-09-11) yalnız bitmiş sessiya rədd edilir — real sinifdə tələbə
    gecikir, telefonu söndürülür, dərsə sonradan qoşulur.
    """


class NotCurrentQuestion(LiveSessionError):
    """Cavab bu iştirakçının hazırkı (fərdi) sualından fərqli sual üçündür."""


class AlreadyAnswered(LiveSessionError):
    """İştirakçı bu sualı artıq cavablayıb."""


class SessionTimeExpired(LiveSessionError):
    """Sessiyanın ümumi vaxt büdcəsi artıq bitib — yeni cavab qəbul edilmir."""


def _question_payload(index: int, total: int, question: dict) -> dict:
    # correct_index/explanation QƏSDƏN yoxdur — cavab sızmasın (bax spec).
    return {
        "index": index,
        "total": total,
        "question": question["question"],
        "options": question["options"],
    }


def _elapsed_seconds(session: dict) -> float:
    started = datetime.fromisoformat(session["started_at"])
    return (datetime.now(timezone.utc) - started).total_seconds()


def _remaining_seconds(session: dict) -> float:
    if session["duration_seconds"] is None or session["started_at"] is None:
        return 0.0
    return max(0.0, session["duration_seconds"] - _elapsed_seconds(session))


def _time_expired(session: dict) -> bool:
    if session["duration_seconds"] is None or session["started_at"] is None:
        return False
    return _elapsed_seconds(session) >= session["duration_seconds"]


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
    bax dizayn sənədi, bölmə 5). Fərdi templi modeldə iştirakçılar fərqli
    sayda sual cavablamış ola bilər (vaxt bitəndə kim harada qalıbsa) —
    `compute_scores`/`list_answers_for_question` bunu artıq nəzərə alır
    (yalnız faktiki verilmiş cavabları sayır)."""
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
    session_id: int, display_name: str, *, session_store, connection_manager, user_id: int
) -> tuple[dict, dict]:
    """İştirakçını sessiyaya əlavə edir və host-a bildirir.

    PIN yerinə SESSİYA ID-si (2026-09-11): sessiya artıq bir sinfə
    bağlıdır, üzvlüyü çağıran (endpoint) çat üzərindən yoxlayır.
    `user_id` MƏCBURİDİR — anonim iştirakçı yolu silindi, yəni hər
    nəticə bir hesaba bağlanır və tələbənin tarixçəsinə düşür.
    """
    session = session_store.get(session_id)
    if session is None:
        raise SessionNotFound(session_id)
    if session["status"] == "finished":
        raise SessionNotJoinable(session_id)

    participant = session_store.add_participant(session["id"], display_name, user_id=user_id)
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
    session_id: int, duration_seconds: int = DEFAULT_SESSION_DURATION_SECONDS,
    *, session_store, question_set_store, connection_manager,
) -> dict:
    """Sessiyanı başladır — ÜMUMİ (`duration_seconds`) vaxt büdcəsi ilə.
    Bütün hazırda qoşulmuş iştirakçılara öz ilk sualları (index 0) eyni
    anda göndərilir, sonrakı hər keçid isə fərdi olaraq `request_next`
    vasitəsilə aparılır."""
    session = session_store.get(session_id)
    if session is None:
        raise SessionNotFound(session_id)
    if session["status"] != "waiting":
        raise LiveSessionError("Sessiya artıq başlayıb")

    questions = question_set_store.list_questions(session["question_set_id"])
    if not questions:
        raise LiveSessionError("Sual bankında sual yoxdur")

    session = session_store.start(session_id, duration_seconds)

    await connection_manager.broadcast_host(
        session_id,
        {
            "type": "started",
            "duration_seconds": duration_seconds,
            "total_questions": len(questions),
        },
    )
    payload = _question_payload(0, len(questions), questions[0])
    await connection_manager.broadcast_players(
        session_id, {"type": "question", **payload, "remaining_seconds": _remaining_seconds(session)}
    )
    return session_store.get(session_id)


async def record_answer(
    session_id: int, participant_id: int, question_index: int, chosen_index: int,
    *, session_store, question_set_store, connection_manager,
) -> dict:
    """Cavabı qeydə alır və NƏTİCƏNİ YALNIZ cavablayan iştirakçıya göndərir
    (əvvəlki paylaşılan modeldən fərqli olaraq broadcast YOXDUR) — növbəti
    suala keçid ayrıca `request_next` çağırışı ilə (tələbənin öz "Növbəti"
    düyməsi) baş verir, burada avtomatik irəliləmə YOXDUR."""
    session = session_store.get(session_id)
    if session is None or session["status"] != "active":
        raise LiveSessionError(f"session_id={session_id} üçün aktiv sessiya yoxdur")
    if _time_expired(session):
        raise SessionTimeExpired("Sessiyanın vaxtı bitib")

    current_index = session_store.count_answers_by_participant(session_id, participant_id)
    if question_index != current_index:
        raise NotCurrentQuestion(question_index)
    if session_store.has_answered(session_id, participant_id, question_index):
        raise AlreadyAnswered(participant_id, question_index)

    questions = question_set_store.list_questions(session["question_set_id"])
    question = questions[question_index]
    is_correct = chosen_index == question["correct_index"]
    answer = session_store.record_answer(
        session_id, participant_id, question_index, chosen_index, is_correct
    )

    await connection_manager.broadcast_host(
        session_id,
        {
            "type": "participant_progress",
            "participant_id": participant_id,
            "answered_count": question_index + 1,
            "total_questions": len(questions),
        },
    )
    await connection_manager.send_to_player(
        session_id,
        participant_id,
        {
            "type": "result",
            "index": question_index,
            "correct_index": question["correct_index"],
            "explanation": question["explanation"],
            "is_correct": is_correct,
        },
    )

    return answer


async def _finish_session_if_ready(
    session_id: int, *, session_store, question_set_store, connection_manager
) -> bool:
    """BÜTÜN iştirakçılar fərdi bitiribsə (bütün suallarını cavablayıb),
    YA DA sessiyanın ümumi vaxtı artıq bitibsə, sessiyanı ZORLA/tam bitirir
    (hesabatı hesablayıb keşləyir, host+bütün oyunçulara YEKUN `finished`
    (tam liderlik lövhəsi ilə) broadcast edir). Əks halda heç nə etmir."""
    session = session_store.get(session_id)
    if session is None or session["status"] != "active":
        return False

    questions = question_set_store.list_questions(session["question_set_id"])
    total = len(questions)
    participants = session_store.list_participants(session_id)
    all_done = bool(participants) and all(
        session_store.count_answers_by_participant(session_id, p["id"]) >= total for p in participants
    )
    if not (all_done or _time_expired(session)):
        return False

    session_store.set_status(session_id, "finished")
    report = compute_report(session_id, session_store=session_store, question_set_store=question_set_store)
    session_store.save_report(session_id, json.dumps(report, ensure_ascii=False))
    finish_payload = {
        "total_questions": total,
        "leaderboard": _leaderboard(session_id, session_store=session_store),
    }
    await connection_manager.broadcast_host(session_id, {"type": "finished", **finish_payload})
    await connection_manager.broadcast_players(session_id, {"type": "finished", **finish_payload})
    return True


async def request_next(
    session_id: int, participant_id: int, *, session_store, question_set_store, connection_manager
) -> None:
    """Tələbənin "Növbəti sual" düyməsi bunu çağırır. Bu iştirakçı üçün
    suallar bitibsə (və ya ümumi vaxt artıq bitibsə) ona DƏRHAL öz şəxsi
    nəticəsini göndərir (`personal_finished`) və sessiyanın TAM bitib-
    bitmədiyini yoxlayır (bax `_finish_session_if_ready`) — yekun tam
    liderlik lövhəsi YALNIZ sessiya həqiqətən bitəndə gəlir. Əks halda bu
    iştirakçıya öz növbəti sualını göndərir."""
    session = session_store.get(session_id)
    if session is None or session["status"] != "active":
        raise LiveSessionError(f"session_id={session_id} üçün aktiv sessiya yoxdur")

    questions = question_set_store.list_questions(session["question_set_id"])
    total = len(questions)
    index = session_store.count_answers_by_participant(session_id, participant_id)

    if _time_expired(session) or index >= total:
        answers = session_store.list_answers_for_participant(session_id, participant_id)
        correct_count = sum(1 for a in answers if a["is_correct"])
        await connection_manager.send_to_player(
            session_id,
            participant_id,
            {
                "type": "personal_finished",
                "correct_count": correct_count,
                "answered_count": len(answers),
                "total_questions": total,
            },
        )
        await _finish_session_if_ready(
            session_id, session_store=session_store, question_set_store=question_set_store,
            connection_manager=connection_manager,
        )
        return

    payload = _question_payload(index, total, questions[index])
    await connection_manager.send_to_player(
        session_id, participant_id,
        {"type": "question", **payload, "remaining_seconds": _remaining_seconds(session)},
    )


async def force_finish_if_expired(
    session_id: int, *, session_store, question_set_store, connection_manager
) -> bool:
    """Sessiya başlayanda BİR DƏFƏLİK fon tapşırığı kimi planlaşdırılır
    (`duration_seconds` sonra) — o anda sessiya hələ 'active'dirsə, kim
    harada qalıbsa sessiyanı ORADA zorla bitirir (bax `_finish_session_if_ready`,
    eyni yoxlama vaxt bitdiyi üçün onsuz da müsbət nəticələnir)."""
    return await _finish_session_if_ready(
        session_id, session_store=session_store, question_set_store=question_set_store,
        connection_manager=connection_manager,
    )


async def watch_session_duration(
    session_id: int, duration_seconds: float, *, session_store, question_set_store, connection_manager
) -> bool:
    await asyncio.sleep(duration_seconds)
    return await force_finish_if_expired(
        session_id, session_store=session_store, question_set_store=question_set_store,
        connection_manager=connection_manager,
    )
