"""Gün 18: CrewAI kurs planlayıcısı - plan sxemi, cədvəl, REST ilə yazma və (crewai varsa) komanda."""

import json
from datetime import date, time

import pytest
from fastapi.testclient import TestClient

from course_planner.cli import main, push
from course_planner.models import (
    CoursePlan, PlanError, lesson_description, lesson_requests, parse_plan, plan_markdown, schedule_dates,
)
from server.app import app, get_chat_store, get_lesson_store, get_token_secret, get_user_store
from server.auth import hash_password
from server.chat_store import ChatStore
from server.lesson_store import LessonStore
from server.models import LessonCreate
from server.user_store import UserStore
from teacher_mcp.server import MasterAIClient

_SECRET = "test-secret-key-32-chars-minimum!!"

PLAN = {
    "title": "Azərbaycan Konstitusiyası", "audience": "Dövlət qulluğuna hazırlaşanlar", "summary": "Qısa kurs.",
    "lessons": [
        {"number": 1, "title": "Konstitusiyanın qəbulu", "objectives": ["1995 referendumunu izah edə bilir"],
         "activities": ["Lövhədə xronologiya"], "homework": "Preambulanı oxu", "quiz_focus": "tarixlər"},
        {"number": 1, "title": "Hakimiyyətlərin bölünməsi", "objectives": ["Üç qolu fərqləndirir", " "],
         "activities": [], "homework": "", "quiz_focus": "orqanlar"},
        {"number": 7, "title": "Milli Məclis", "objectives": ["Deputat sayını və müddəti bilir"]},
    ],
}


def test_parse_plan_handles_fences_and_renumbers():
    plan = parse_plan("Budur plan:\n```json\n" + json.dumps(PLAN, ensure_ascii=False) + "\n```")
    assert [l.number for l in plan.lessons] == [1, 2, 3]
    assert plan.lessons[1].objectives == ["Üç qolu fərqləndirir"]   # boş məqsəd atılır
    with pytest.raises(PlanError, match="JSON tapılmadı"):
        parse_plan("Bağışlayın.")
    with pytest.raises(PlanError, match="sxemə"):
        parse_plan('{"title": "x", "lessons": []}')


def test_schedule_dates_weekdays_and_baku_time():
    starts = schedule_dates(date(2026, 11, 10), 4, [1, 3], time(18, 0))   # 10 noyabr = çərşənbə axşamı
    assert [d.date().isoformat() for d in starts] == ["2026-11-11", "2026-11-16", "2026-11-18", "2026-11-23"]
    assert starts[0].isoformat() == "2026-11-11T18:00:00+04:00"
    with pytest.raises(ValueError):
        schedule_dates(date(2026, 11, 10), 1, [9], time(18, 0))


def test_lesson_requests_fit_server_model():
    plan = CoursePlan.model_validate(PLAN)
    bodies = lesson_requests(plan, schedule_dates(date(2026, 11, 10), 3, [1], time(10, 0)), mode="offline")
    for body in bodies:
        LessonCreate.model_validate(body)   # server bu gövdəni qəbul edir
    assert bodies[0]["title"] == "1. Konstitusiyanın qəbulu" and bodies[0]["mode"] == "offline"
    assert "Ev tapşırığı: Preambulanı oxu" in bodies[0]["description"]
    long = plan.lessons[0].model_copy(update={"objectives": ["x" * 400] * 6})
    assert len(lesson_description(long)) <= 2000
    with pytest.raises(ValueError):
        lesson_requests(plan, [])


def test_markdown():
    text = plan_markdown(CoursePlan.model_validate(PLAN))
    assert text.startswith("# Azərbaycan Konstitusiyası") and "## 3. Milli Məclis" in text


@pytest.fixture
def api():
    users, chats, lessons = UserStore(":memory:"), ChatStore(":memory:"), LessonStore(":memory:")
    for dep, value in {get_user_store: users, get_chat_store: chats, get_lesson_store: lessons,
                       get_token_secret: _SECRET}.items():
        app.dependency_overrides[dep] = (lambda v: lambda: v)(value)
    course = users.courses.create("Kurs", "exam_prep", trial_days=30, seat_limit=30)
    teacher = users.create("t@x.az", hash_password("sirr-12345"), "Müəllim", course_id=course["id"])
    users.set_teacher(teacher["id"], True)
    chat = chats.create(kind="group", created_by=teacher["id"], name="Sinif", course_id=course["id"])
    chats.add_member(chat["id"], teacher["id"])
    client = MasterAIClient("http://testserver", email="t@x.az", password="sirr-12345", http=TestClient(app))
    yield {"client": client, "chat": chat, "lessons": lessons}
    app.dependency_overrides.clear()


def test_push_creates_scheduled_lessons_through_rest(api):
    created = push(CoursePlan.model_validate(PLAN), api["client"], class_id=api["chat"]["id"],
                   start=date(2026, 11, 10), weekdays=[2, 4], at=time(18, 30))
    assert len(created) == 3 and all(l["status"] == "scheduled" for l in created)
    stored = api["lessons"].list_for_chats([api["chat"]["id"]])
    assert sorted(l["title"] for l in stored)[0] == "1. Konstitusiyanın qəbulu" and len(stored) == 3
    assert created[0]["starts_at"].startswith("2026-11-10T14:30")   # 18:30 Bakı = 14:30 UTC


def test_cli_plan_then_push(api, tmp_path, capsys):
    out = tmp_path / "plan.json"
    seen = {}

    def fake_planner(topic, lessons, *, level, goal):
        seen.update(topic=topic, lessons=lessons, level=level)
        return CoursePlan.model_validate(PLAN)

    assert main(["plan", "--topic", "Konstitusiya", "--lessons", "3", "--out", str(out)], planner=fake_planner) == 0
    assert seen == {"topic": "Konstitusiya", "lessons": 3, "level": "orta"}
    assert (tmp_path / "plan.md").read_text(encoding="utf-8").startswith("# Azərbaycan")
    assert main(["push", str(out), "--class-id", str(api["chat"]["id"]), "--start", "2026-11-10",
                 "--weekdays", "1,3,5", "--time", "09:00"], client=api["client"]) == 0
    assert "3 dərs sinfin cədvəlinə yazıldı" in capsys.readouterr().out


def test_push_to_foreign_class_is_refused(api, tmp_path):
    from teacher_mcp.server import MasterAIError

    with pytest.raises(MasterAIError, match="404|403"):
        push(CoursePlan.model_validate(PLAN), api["client"], class_id=999, start=date(2026, 11, 10),
             weekdays=[1], at=time(9, 0))


# ---- CrewAI komandası (yalnız crewai quraşdırılıbsa: requirements-agents.txt) ------

def test_crew_runs_three_agents_in_order_with_our_fallback_chain():
    pytest.importorskip("crewai")
    from course_planner.crew import MasterAILLM, plan_course

    calls = []

    def fake(system, user):
        calls.append((system, user))
        if "Qiymətləndirmə mütəxəssisi" in system:
            assert "DİZAYNER-ÇIXIŞI" in user and "METODİST-ÇIXIŞI" in user   # context ötürülür
            return "Final Answer: " + json.dumps(PLAN, ensure_ascii=False)
        if "Metodist" in system:
            assert "DİZAYNER-ÇIXIŞI" in user
            return "Final Answer: METODİST-ÇIXIŞI: məqsədlər"
        return "Final Answer: DİZAYNER-ÇIXIŞI: 1. Qəbul 2. Hakimiyyət 3. Məclis"

    def broken(system, user):
        raise RuntimeError("vLLM düşdü")

    llm = MasterAILLM(completers={"vllm": broken, "groq": fake}, order=["vllm", "groq"])
    plan = plan_course("Konstitusiya", 3, llm=llm)
    assert len(plan.lessons) == 3 and plan.title == "Azərbaycan Konstitusiyası"
    roles = [next(r for r in ("Kurikulum dizayneri", "Metodist", "Qiymətləndirmə mütəxəssisi") if r in s)
             for s, _ in calls]
    assert roles == ["Kurikulum dizayneri", "Metodist", "Qiymətləndirmə mütəxəssisi"]


def test_crew_rejects_wrong_lesson_count():
    pytest.importorskip("crewai")
    from course_planner.crew import MasterAILLM, plan_course

    llm = MasterAILLM(completers={"x": lambda s, u: "Final Answer: " + json.dumps(PLAN, ensure_ascii=False)},
                      order=["x"])
    with pytest.raises(PlanError, match="3 dərs qaytardı, istənilən 5"):
        plan_course("Konstitusiya", 5, llm=llm)


def test_crewai_telemetry_disabled_before_import():
    pytest.importorskip("crewai")
    import importlib
    import os

    importlib.import_module("course_planner.crew")
    assert os.environ["CREWAI_DISABLE_TELEMETRY"] == "true" and os.environ["OTEL_SDK_DISABLED"] == "true"
