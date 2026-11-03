"""İnkişaf qrafikləri (Faza 3 PR 1, 2026-11-03).

Tarixçə ilə EYNİ data mənbəyi üzərində qurulur
(`app.py::_history_entries_for_student`-in qaytardığı `HistoryEntry`
siyahısı) — canlı sessiya + ev tapşırığı nəticələrini HƏFTƏ (ISO,
bazar ertəsi başlayır) və FƏNN üzrə qruplaşdırıb faiz hesablayır.

Davamiyyət ayrı mənbədir (`server/lesson_store.py`): bitmiş dərslərin
neçəsində iştirak qeydi var.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from server.lesson_store import LessonStore


def _week_start(date_str: str) -> str:
    dt = datetime.fromisoformat(date_str)
    d = dt.date()
    return (d - timedelta(days=d.weekday())).isoformat()


def weekly_percent(entries) -> list[dict]:
    """`[{"week_start", "correct", "total", "percent"}, ...]`, ən köhnə
    həftə əvvəldə."""
    buckets: dict[str, list[int]] = {}
    for e in entries:
        bucket = buckets.setdefault(_week_start(e.date), [0, 0])
        bucket[0] += e.score
        bucket[1] += e.total_questions
    result = [
        {"week_start": week, "correct": c, "total": t, "percent": round(c / t * 100) if t else 0}
        for week, (c, t) in buckets.items()
    ]
    result.sort(key=lambda r: r["week_start"])
    return result


def subject_percent(entries) -> list[dict]:
    """`[{"subject", "correct", "total", "percent"}, ...]`, faizə görə
    ARTAN sırada (ən zəif fənn əvvəl — eyni naxış `topic_stats.py`-də)."""
    buckets: dict[str, list[int]] = {}
    for e in entries:
        bucket = buckets.setdefault(e.subject, [0, 0])
        bucket[0] += e.score
        bucket[1] += e.total_questions
    result = [
        {"subject": subject, "correct": c, "total": t, "percent": round(c / t * 100) if t else 0}
        for subject, (c, t) in buckets.items()
    ]
    result.sort(key=lambda r: r["percent"])
    return result


def attendance_stats_for_users(user_ids: list[int], chat_ids: list[int], lessons: LessonStore) -> dict:
    """Yalnız BİTMİŞ (`ended`) dərslər sayılır — planlaşdırılmış dərsə
    hələ gəlinməyib deyə onu hesaba qatmaq ədalətsiz olardı. Birdən çox
    istifadəçi verilsə (sinif üzrə), məxrəc dərs × tələbə sayıdır - bu,
    hər tələbənin faizini ayrı hesablayıb ORTALAMAQDAN fərqlidir: az
    dərsi olan tələbənin bir buraxması faizi ortalamada həddən artıq
    aşağı salmasın. Dərs (və ya istifadəçi) yoxdursa `percent: None` -
    uydurma 0% göstərmək yanlış olardı (eyni qayda
    `web/assets/js/difficulty.js::statPercent`-də var)."""
    ended = [lesson for lesson in lessons.list_for_chats(chat_ids) if lesson["status"] == "ended"]
    if not ended or not user_ids:
        return {"attended": 0, "total": 0, "percent": None}
    total = len(ended) * len(user_ids)
    attended = 0
    for lesson in ended:
        present = {row["user_id"] for row in lessons.list_attendance(lesson["id"])}
        attended += sum(1 for uid in user_ids if uid in present)
    return {"attended": attended, "total": total, "percent": round(attended / total * 100)}


def attendance_stats(user_id: int, chat_ids: list[int], lessons: LessonStore) -> dict:
    return attendance_stats_for_users([user_id], chat_ids, lessons)
