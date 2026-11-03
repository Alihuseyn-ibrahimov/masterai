"""Zəif mövzu analizi (Faza 2 PR 2, 2026-11-03).

Hər sual bankının suallarına generasiya zamanı AI `topic` etiketi yazır
(bax `pipeline/generation.py`). Bu modul tələbənin CANLI SESSİYA VƏ EV
TAPŞIRIĞI cavablarını (tarixçə ilə eyni iki mənbə, bax
`app.py::_history_entries_for_student`) mövzu üzrə qruplaşdırıb faiz
hesablayır.

Mövzusuz (köhnə, 2026-11-03-dən əvvəl yaradılmış) suallar HESABA
QATILMIR — naməlum mövzunun faizi tələbəyə heç nə demir.
"""

from __future__ import annotations

from server.homework_store import HomeworkStore
from server.live_session_store import LiveSessionStore
from server.question_set_store import QuestionSetStore

# Bu qədər cavabdan az olan mövzu "güclü/zəif" sayılmır — 1 sualın 0%
# və ya 100% faizi mənalı siqnal deyil.
MIN_ANSWERS = 2
STRONG_THRESHOLD = 80
WEAK_THRESHOLD = 60


def topic_stats_for_student(
    student_id: int,
    *,
    live_sessions: LiveSessionStore,
    homework: HomeworkStore,
    question_sets: QuestionSetStore,
) -> list[dict]:
    """`[{"topic", "correct", "total", "percent"}, ...]`, faizə görə
    ARTAN sırada (ən zəif əvvəl)."""
    totals: dict[str, list[int]] = {}

    def _add(topic: str | None, is_correct: bool) -> None:
        if not topic:
            return
        bucket = totals.setdefault(topic, [0, 0])
        bucket[1] += 1
        if is_correct:
            bucket[0] += 1

    for row in live_sessions.list_participations_for_user(student_id):
        questions = question_sets.list_questions(row["question_set_id"])
        for answer in live_sessions.list_answers_for_participant(
            row["session_id"], row["participant_id"]
        ):
            idx = answer["question_index"]
            if 0 <= idx < len(questions):
                _add(questions[idx]["topic"], answer["is_correct"])

    for attempt in homework.list_attempts_by_student(student_id):
        assignment = homework.get_assignment(attempt["assignment_id"])
        if assignment is None:
            continue
        questions = question_sets.list_questions(assignment["question_set_id"])
        for answer in homework.list_answers_for_attempt(attempt["id"]):
            idx = answer["question_index"]
            if 0 <= idx < len(questions):
                _add(questions[idx]["topic"], answer["is_correct"])

    stats = [
        {"topic": topic, "correct": correct, "total": total,
         "percent": round(correct / total * 100)}
        for topic, (correct, total) in totals.items()
    ]
    stats.sort(key=lambda s: (s["percent"], -s["total"]))
    return stats


def split_strong_weak(stats: list[dict]) -> tuple[list[dict], list[dict]]:
    """Yetərli cavabı olan mövzuları güclü/zəifə bölür (plan: tələbə
    profilində "güclü / zəif mövzular"). Aradakı (60-80%) mövzu heç bir
    siyahıya düşmür — bu, "aydın deyil" vəziyyətidir."""
    eligible = [s for s in stats if s["total"] >= MIN_ANSWERS]
    weak = [s for s in eligible if s["percent"] < WEAK_THRESHOLD]
    strong = [s for s in eligible if s["percent"] >= STRONG_THRESHOLD]
    return strong, weak
