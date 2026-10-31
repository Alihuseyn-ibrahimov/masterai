"""Kurs planının sxemi və cədvələ çevrilməsi - CrewAI-dan asılı DEYİL (CI-da sınanır)."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator

MAX_LESSONS = 40
DESCRIPTION_LIMIT = 2000  # server `LessonCreate.description` həddi


class PlannedLesson(BaseModel):
    number: int = Field(ge=1)
    title: str = Field(min_length=3, max_length=200)
    objectives: list[str] = Field(min_length=1, max_length=6)
    activities: list[str] = Field(default_factory=list, max_length=6)
    homework: str = ""
    quiz_focus: str = ""

    @field_validator("objectives", "activities")
    @classmethod
    def _clean(cls, items: list[str]) -> list[str]:
        return [s.strip() for s in items if isinstance(s, str) and s.strip()]


class CoursePlan(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    audience: str = ""
    summary: str = ""
    lessons: list[PlannedLesson] = Field(min_length=1, max_length=MAX_LESSONS)

    @field_validator("lessons")
    @classmethod
    def _renumber(cls, lessons: list[PlannedLesson]) -> list[PlannedLesson]:
        # Model nömrələri bəzən təkrarlayır və ya 0-dan başlayır: sıra mənbədir.
        for i, lesson in enumerate(lessons, start=1):
            lesson.number = i
        return lessons


class PlanError(ValueError):
    pass


def parse_plan(text: str) -> CoursePlan:
    """LLM cavabından JSON (```json``` hasarı, ön/son mətn ola bilər)."""
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        raise PlanError("Cavabda JSON tapılmadı")
    try:
        return CoursePlan.model_validate(json.loads(match.group(0)))
    except (json.JSONDecodeError, ValueError) as exc:
        raise PlanError(f"Plan sxemə uyğun deyil: {str(exc)[:300]}") from None


def schedule_dates(start: date, count: int, weekdays: list[int], at: time,
                   tz: str = "Asia/Baku") -> list[datetime]:
    """`start`-dan başlayaraq seçilmiş həftə günlərinə (1 = bazar ertəsi ... 7 = bazar) düşən
    ilk `count` tarix, yerli saatla (saat qurşağı ilə; server UTC-yə çevirir)."""
    days = sorted({d for d in weekdays if 1 <= d <= 7})
    if not days:
        raise ValueError("Ən azı bir həftə günü seçilməlidir (1-7)")
    zone, result, current = ZoneInfo(tz), [], start
    while len(result) < count:
        if current.isoweekday() in days:
            result.append(datetime.combine(current, at, tzinfo=zone))
        current += timedelta(days=1)
    return result


def lesson_description(lesson: PlannedLesson) -> str:
    parts = ["Məqsədlər:"] + [f"- {o}" for o in lesson.objectives]
    if lesson.activities:
        parts += ["", "Dərsdə:"] + [f"- {a}" for a in lesson.activities]
    if lesson.homework:
        parts += ["", f"Ev tapşırığı: {lesson.homework}"]
    if lesson.quiz_focus:
        parts += [f"Quizdə yoxlanılacaq: {lesson.quiz_focus}"]
    text = "\n".join(parts)
    return text if len(text) <= DESCRIPTION_LIMIT else text[:DESCRIPTION_LIMIT - 1] + "…"


def lesson_requests(plan: CoursePlan, starts: list[datetime], *, duration_min: int = 90,
                    mode: str = "online") -> list[dict]:
    """`POST /chats/{id}/lessons` gövdələri - planın hər dərsi bir sorğu."""
    if len(starts) < len(plan.lessons):
        raise ValueError("Tarix sayı dərs sayından azdır")
    return [{"title": f"{lesson.number}. {lesson.title}"[:200], "description": lesson_description(lesson),
             "starts_at": start.isoformat(), "duration_min": duration_min, "mode": mode}
            for lesson, start in zip(plan.lessons, starts)]


def plan_markdown(plan: CoursePlan) -> str:
    lines = [f"# {plan.title}", ""]
    if plan.audience:
        lines += [f"Kim üçün: {plan.audience}", ""]
    if plan.summary:
        lines += [plan.summary, ""]
    for lesson in plan.lessons:
        lines += [f"## {lesson.number}. {lesson.title}"] + [f"- {o}" for o in lesson.objectives]
        if lesson.homework:
            lines.append(f"- Ev tapşırığı: {lesson.homework}")
        if lesson.quiz_focus:
            lines.append(f"- Quiz: {lesson.quiz_focus}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
