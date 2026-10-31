"""Üç agentli kurs planlama komandası (CrewAI, gün 18).

    Kurikulum dizayneri ──▶ Metodist ──▶ Qiymətləndirmə mütəxəssisi ──▶ CoursePlan (JSON)

- **Kurikulum dizayneri** mövzunu dərslərə bölür: sadədən mürəkkəbə, hər dərs bir əsas fikir.
- **Metodist** hər dərsə ölçülə bilən məqsədlər və dərsdə nə ediləcəyini yazır
  (platformanın imkanları ilə: video dərs, lövhə şəkli, AI tutor, QR davamiyyət).
- **Qiymətləndirmə mütəxəssisi** hər dərsə ev tapşırığı və quizin yoxlayacağı
  bacarığı əlavə edir və planı YALNIZ JSON kimi qaytarır.

Proses ardıcıldır: hər tapşırıq əvvəlkinin nəticəsini `context` kimi görür.

LLM: CrewAI defolt olaraq litellm ilə özü provayderə gedir. Biz isə MasterAI-nin
öz fallback zəncirini (`complete_with_fallback`: vLLM → Groq → Claude) `BaseLLM`
adapteri ilə veririk: eyni açarlar, eyni LangSmith izi, ayrıca konfiqurasiya yox.

CrewAI ağırdır (~1 GB asılılıq) və SERVERƏ QOYULMUR: planlayıcı müəllimin
kompüterində işləyir və dərsləri mövcud REST API ilə yazır (`cli.py`, gün 11-in
MCP naxışı kimi).
"""

from __future__ import annotations

import os
from typing import Any

# CrewAI defolt olaraq anonim telemetriya göndərir; planda kursun mövzusu var -
# müəllimin icazəsi olmadan kənara heç nə getməsin. İdxaldan ƏVVƏL olmalıdır.
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

from crewai import Agent, Crew, Process, Task  # noqa: E402
from crewai.llms.base_llm import BaseLLM  # noqa: E402
from pydantic import PrivateAttr  # noqa: E402

from course_planner.models import CoursePlan, PlanError, parse_plan  # noqa: E402
from pipeline.providers import DEFAULT_ORDER, Completer, build_completers, complete_with_fallback  # noqa: E402

PLAN_SCHEMA = (
    '{"title": "...", "audience": "...", "summary": "2-3 cümlə", "lessons": [{"number": 1, '
    '"title": "...", "objectives": ["..."], "activities": ["..."], "homework": "...", "quiz_focus": "..."}]}'
)


class MasterAILLM(BaseLLM):
    """CrewAI → MasterAI provayder zənciri. Alət çağırışı (function calling) yoxdur:
    agentlərin aləti yoxdur, yalnız mətn yazırlar."""

    _completers: dict = PrivateAttr(default_factory=dict)
    _order: list = PrivateAttr(default_factory=list)

    def __init__(self, completers: dict[str, Completer] | None = None, order: list[str] | None = None,
                 **data: Any) -> None:
        super().__init__(model=data.pop("model", "masterai-fallback"), **data)
        self._completers = completers if completers is not None else build_completers()
        self._order = order or DEFAULT_ORDER

    def call(self, messages, tools=None, callbacks=None, available_functions=None, from_task=None,
             from_agent=None, response_model=None) -> str:
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        system = "\n\n".join(str(m["content"]) for m in messages if m["role"] == "system")
        rest = [m for m in messages if m["role"] != "system"]
        user = (str(rest[0]["content"]) if len(rest) == 1
                else "\n\n".join(f"[{m['role']}]\n{m['content']}" for m in rest))
        return complete_with_fallback(system, user, self._order, self._completers)

    def supports_function_calling(self) -> bool:
        return False

    def supports_stop_words(self) -> bool:
        return False

    def get_context_window_size(self) -> int:
        return 32_000


def build_crew(llm: BaseLLM) -> Crew:
    designer = Agent(
        role="Kurikulum dizayneri",
        goal="Mövzunu {lessons} dərsə bölmək: sadədən mürəkkəbə, hər dərsdə bir əsas fikir, təkrar yox",
        backstory=("Azərbaycanda dövlət qulluğu və magistratura imtahanlarına hazırlıq kursları qurursan. "
                   "Tələbələr işləyən gənclərdir, dərs 90 dəqiqədir."),
        llm=llm, allow_delegation=False, verbose=False,
    )
    methodist = Agent(
        role="Metodist",
        goal="Hər dərs üçün ölçülə bilən məqsədlər və dərsdə görüləcək işləri yazmaq",
        backstory=("Dərsləri MasterAI platformasında keçirən müəllimlərə kömək edirsən. Platformada canlı "
                   "video dərs, dərs səsindən avtomatik konspekt, lövhə şəklindən mətn, AI tutor və QR "
                   "davamiyyət var - fəaliyyətlərdə bunlardan yerində istifadə et."),
        llm=llm, allow_delegation=False, verbose=False,
    )
    assessor = Agent(
        role="Qiymətləndirmə mütəxəssisi",
        goal="Hər dərsə ev tapşırığı və quizin yoxlayacağı bacarığı əlavə edib planı JSON kimi təhvil vermək",
        backstory="İmtahan testləri hazırlayırsan və bilirsən ki, yoxlanılmayan məqsəd öyrənilmir.",
        llm=llm, allow_delegation=False, verbose=False,
    )
    outline = Task(
        description=("Mövzu: {topic}\nSəviyyə: {level}\nMəqsəd: {goal}\nDərs sayı: {lessons}\n\n"
                     "Tam {lessons} dərsin sıralı siyahısını yaz: nömrə, başlıq, bir cümləlik məzmun."),
        expected_output="{lessons} sətirlik nömrələnmiş dərs siyahısı",
        agent=designer,
    )
    methods = Task(
        description=("Hər dərs üçün 2-4 ölçülə bilən məqsəd («... izah edə bilir», «... fərqləndirir») və "
                     "2-3 fəaliyyət yaz. Dərs sayını və sırasını DƏYİŞMƏ."),
        expected_output="Hər dərs üçün məqsədlər və fəaliyyətlər",
        agent=methodist, context=[outline],
    )
    assessment = Task(
        description=("Hər dərsə qısa ev tapşırığı və quizin yoxlayacağı bacarığı əlavə et. Sonra bütün planı "
                     f"YALNIZ bu JSON formatında qaytar, başqa mətn yazma:\n{PLAN_SCHEMA}\n"
                     "Dərs sayı tam {lessons} olmalıdır. Mətnlər Azərbaycan dilində."),
        expected_output="Yalnız JSON: CoursePlan",
        agent=assessor, context=[outline, methods],
    )
    return Crew(agents=[designer, methodist, assessor], tasks=[outline, methods, assessment],
                process=Process.sequential, verbose=False)


def plan_course(topic: str, lessons: int, *, level: str = "orta", goal: str = "imtahana hazırlıq",
                llm: BaseLLM | None = None) -> CoursePlan:
    crew = build_crew(llm or MasterAILLM())
    result = crew.kickoff(inputs={"topic": topic, "lessons": lessons, "level": level, "goal": goal})
    plan = parse_plan(getattr(result, "raw", str(result)))
    if len(plan.lessons) != lessons:
        raise PlanError(f"Komanda {len(plan.lessons)} dərs qaytardı, istənilən {lessons}")
    return plan
