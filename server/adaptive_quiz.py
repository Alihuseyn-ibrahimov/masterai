"""Fərdi məşq quizi (Faza 2 PR 3, 2026-11-03) - zəif mövzulardan.

`server/topic_stats.py`-in zəif mövzularından, tələbənin ARTIQ GÖRDÜYÜ
banklardan (canlı sessiya + ev tapşırığı - eyni iki mənbə) sual seçir.
Yeni kurs sərhədi yoxlaması lazım deyil: bu banklar onsuz da
`topic_stats_for_student`-in istifadə etdiyi, tələbənin əlçatan datasıdır.

Bu, QİYMƏTLƏNDİRİLƏN tapşırıq DEYİL - sərbəst məşqdir, nəticə heç
yerdə saxlanmır (yeni `attempt` cədvəli lazım deyil). Ona görə
`LiveQuestionInfo` düzgün cavab+izah DAXİL qaytarılır (müəllimin
redaktə ekranı ilə eyni, bax `list_live_questions`), client tərəf
sualları ardıcıl göstərib cavabı dərhal açır.

`difficulty_model` varsa, proqnozu 0.4-0.75 aralığında olan suallar
üstünlük alır - çox asan sual öyrətmir, çox çətin demoralizə edir
(bax `pipeline/difficulty_model.py`).
"""

from __future__ import annotations

from pipeline.models import MCQQuestion
from server.homework_store import HomeworkStore
from server.live_session_store import LiveSessionStore
from server.question_set_store import QuestionSetStore
from server.topic_stats import split_strong_weak, topic_stats_for_student

DEFAULT_LIMIT = 5
_TARGET_LOW = 0.4
_TARGET_HIGH = 0.75


def build_adaptive_quiz(
    student_id: int,
    *,
    live_sessions: LiveSessionStore,
    homework: HomeworkStore,
    question_sets: QuestionSetStore,
    difficulty_model=None,
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    """Zəif mövzudan ən çox `limit` sual, modeli varsa "orta çətinliyə"
    görə sıralanmış. Zəif mövzu yoxdursa boş siyahı."""
    stats = topic_stats_for_student(
        student_id, live_sessions=live_sessions, homework=homework, question_sets=question_sets,
    )
    _, weak = split_strong_weak(stats)
    weak_topics = {s["topic"] for s in weak}
    if not weak_topics:
        return []

    set_ids: set[int] = set()
    for row in live_sessions.list_participations_for_user(student_id):
        set_ids.add(row["question_set_id"])
    for attempt in homework.list_attempts_by_student(student_id):
        assignment = homework.get_assignment(attempt["assignment_id"])
        if assignment is not None:
            set_ids.add(assignment["question_set_id"])

    candidates = [
        q
        for qs_id in set_ids
        for q in question_sets.list_questions(qs_id)
        if q["topic"] in weak_topics
    ]

    if difficulty_model is not None:
        def _distance_from_target(q: dict) -> float:
            p = difficulty_model.predict(MCQQuestion(
                question=q["question"], options=q["options"], correct_index=q["correct_index"],
                explanation=q["explanation"], difficulty=q["difficulty"],
            ))
            if p < _TARGET_LOW:
                return _TARGET_LOW - p
            if p > _TARGET_HIGH:
                return p - _TARGET_HIGH
            return 0.0
        candidates.sort(key=_distance_from_target)

    return candidates[:limit]
