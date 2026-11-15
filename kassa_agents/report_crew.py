"""Aylıq Kassa hesabatı: üç agentli CrewAI komandası.

    Maliyyə analitiki ──▶ Risk analitiki ──▶ Hesabat redaktoru ──▶ markdown hesabat

- **Maliyyə analitiki**: gəlir, yığım faizi, xərc, xalis qalıq və son ayların trendi.
- **Risk analitiki**: borclular, 2+ aydır ödəməyənlər (tərk riski), yığımı zəif qruplar.
- **Hesabat redaktoru**: rəhbər üçün qısa hesabat (3 bölmə + bu həftə üçün 3 addım).

Qoruyucu qat (`facts.py`): komanda yalnız ANONİM fakt vərəqini görür, cavabda
xülasədə olmayan rəqəm daşıyan cümlə atılır, adlar sonra rəhbərin kompüterində
qaytarılır. LLM bizim fallback zəncirimizdir (`course_planner.crew.MasterAILLM`).
CrewAI serverə QOYULMUR (`requirements-agents.txt`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from course_planner.crew import MasterAILLM  # telemetriyanı idxaldan əvvəl söndürür
from crewai import Agent, Crew, Process, Task  # noqa: E402

from kassa_agents.facts import allowed_numbers, anonymize, deanonymize, facts_text, ground_report

RULES = ("Yalnız fakt vərəqindəki rəqəmləri işlət, yeni rəqəm hesablama və təxmin etmə. "
         "Şagirdləri ləqəbi ilə yaz («Şagird 2»). Azərbaycan dilində yaz.")


@dataclass
class KassaReport:
    markdown: str
    dropped: list[str] = field(default_factory=list)   # rəqəmi yoxlanmayan, atılan cümlələr


def build_crew(llm) -> Crew:
    finance = Agent(
        role="Maliyyə analitiki",
        goal="Kursun bu ayki gəlirini, yığım faizini, xərclərini və trendini qısa təhlil etmək",
        backstory="Kiçik təhsil müəssisələrinin kassasını aparırsan; rəhbər rəqəmi yox, mənasını bilmək istəyir.",
        llm=llm, allow_delegation=False, verbose=False,
    )
    risk = Agent(
        role="Risk analitiki",
        goal="Kimin borcu var, kim kursu tərk edə bilər, hansı qrupda yığım zəifdir - tapmaq",
        backstory="Şagird itkisini erkən görürsən: 2+ ay ödəməyən çox vaxt artıq gedib, ona zəng lazımdır.",
        llm=llm, allow_delegation=False, verbose=False,
    )
    editor = Agent(
        role="Hesabat redaktoru",
        goal="Kurs rəhbəri üçün bir dəqiqədə oxunan aylıq hesabat yazmaq",
        backstory="Rəhbər telefonda oxuyur: qısa başlıqlar, qısa cümlələr, konkret addımlar.",
        llm=llm, allow_delegation=False, verbose=False,
    )
    money = Task(
        description=f"Fakt vərəqi:\n{{facts}}\n\nAyın maliyyə vəziyyətini 4-6 cümlə ilə təhlil et. {RULES}",
        expected_output="Gəlir, yığım, xərc, xalis qalıq və trend haqqında 4-6 cümlə",
        agent=finance,
    )
    risks = Task(
        description=(f"Fakt vərəqi:\n{{facts}}\n\nBorcluları prioritetlə sırala: əvvəl tərk riski olanlar, "
                     f"sonra ən çox borcu olanlar. Yığımı zəif qrupu göstər. {RULES}"),
        expected_output="Prioritetli borclu siyahısı və zəif qruplar",
        agent=risk,
    )
    report = Task(
        description=("Analitiklərin qeydlərindən {month} ayı üçün markdown hesabat yaz, ən çox 250 söz:\n"
                     "## Pul\n## Risk\n## Bu həftə\n(«Bu həftə» bölməsində 3 konkret addım, məs. kimə zəng etmək.) "
                     f"{RULES}"),
        expected_output="Yalnız markdown hesabat",
        agent=editor, context=[money, risks],
    )
    return Crew(agents=[finance, risk, editor], tasks=[money, risks, report],
                process=Process.sequential, verbose=False)


def monthly_report(summary: dict, *, llm=None) -> KassaReport:
    anon = anonymize(summary)
    crew = build_crew(llm or MasterAILLM())
    result = crew.kickoff(inputs={"facts": facts_text(anon.summary), "month": summary["month"]})
    text, dropped = ground_report(getattr(result, "raw", str(result)), allowed_numbers(anon.summary))
    return KassaReport(deanonymize(text, anon.names), [deanonymize(d, anon.names) for d in dropped])
