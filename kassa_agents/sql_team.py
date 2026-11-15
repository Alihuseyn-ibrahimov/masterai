"""«Kassaya sual ver»: iki agentli AutoGen komandası.

    sual ─(guardrails: injection blok, şəxsi məlumat maskası)─▶ SQL analitiki
        ─(alət: run_sql, yalnız oxuyan surət)─▶ Yoxlayıcı ─▶ cavab ─(rəqəm yoxlaması)─▶ rəhbər

- **SQL analitiki** sualı anonim surətə (`facts.snapshot_db`) SQL sorğusu ilə cavablayır.
  `run_sql` aləti `safe_query`-dir: yalnız SELECT, bir ifadə, sətir/addım limiti.
- **Yoxlayıcı** cavabı alətin nəticəsi ilə tutuşdurur, səhv varsa analitikdən yenidən
  soruşur, düzgündürsə qısa yekun cavab yazıb «YEKUN» ilə bitirir.
- Yekun cavabda alət nəticələrində (və sualda) olmayan rəqəm daşıyan cümlə atılır.

AutoGen CrewAI ilə BİR venv-ə qoyulmur (`requirements-autogen.txt`), serverə də qoyulmur.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
from autogen_agentchat.messages import TextMessage
from autogen_agentchat.teams import RoundRobinGroupChat

from kassa_agents.facts import (
    SCHEMA, QueryRejected, alias_names, anonymize, deanonymize, format_rows, ground_report, numbers_in, safe_query, snapshot_db,
)
from pipeline.guardrails import check_input

ANALYST_PROMPT = (
    "Sən hazırlıq kursunun kassa analitikisən. Suala cavab vermək üçün run_sql alətini çağır. Cədvəllər:\n"
    f"{SCHEMA}\n"
    "Şagirdlər ləqəblədir («Şagird 2»), real ad yoxdur. Rəqəmləri YALNIZ alətin nəticəsindən götür. "
    "Qısa cavab yaz."
)
CHECKER_PROMPT = (
    "Sən yoxlayıcısan. Analitikin cavabını alətin nəticəsi ilə tutuşdur: rəqəmlər nəticədə varmı, sual "
    "cavablanıbmı? Səhv varsa analitikə nəyi düzəltməli olduğunu yaz. Düzgündürsə rəhbər üçün 1-3 cümləlik "
    "yekun cavab yaz və ayrıca sətirdə YEKUN yaz. Azərbaycan dilində."
)
NOT_FOUND = "Bu suala Kassa məlumatından etibarlı cavab tapmadım."


@dataclass
class Answer:
    text: str
    status: str = "ok"                 # ok | blocked | not_found
    queries: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    rails: list[str] = field(default_factory=list)


async def ask_async(question: str, summary: dict, *, analyst_client, checker_client=None) -> Answer:
    guard = check_input(question)
    if guard.blocked:
        return Answer(guard.message, "blocked", rails=guard.rails)
    anon = anonymize(summary)
    conn = snapshot_db(anon.summary)
    queries: list[str] = []
    outputs: list[str] = []

    async def run_sql(sql: str) -> str:
        """Kassa surətində bir SELECT sorğusu işlədir və nəticə cədvəlini qaytarır."""
        queries.append(sql)
        try:
            text = format_rows(*safe_query(conn, sql))
        except QueryRejected as exc:
            text = f"XƏTA: {exc}"
        outputs.append(text)
        return text

    analyst = AssistantAgent("analitik", analyst_client, tools=[run_sql], system_message=ANALYST_PROMPT,
                             reflect_on_tool_use=True, max_tool_iterations=4)
    checker = AssistantAgent("yoxlayici", checker_client or analyst_client, system_message=CHECKER_PROMPT)
    team = RoundRobinGroupChat(
        [analyst, checker],
        termination_condition=TextMentionTermination("YEKUN", sources=["yoxlayici"]) | MaxMessageTermination(8),
    )
    task = alias_names(guard.text, anon.names)          # «Kamran nə qədər borcludur?» → «Şagird 2 ...»
    result = await team.run(task=task)
    finals = [m.content for m in result.messages if isinstance(m, TextMessage) and m.source == "yoxlayici"]
    raw = finals[-1].replace("YEKUN", "").strip() if finals else ""
    allowed = numbers_in("\n".join(outputs) + "\n" + task)
    text, dropped = ground_report(raw, allowed)
    if not outputs or not text:
        return Answer(NOT_FOUND, "not_found", queries, dropped, guard.rails)
    return Answer(deanonymize(text, anon.names), "ok", queries,
                  [deanonymize(d, anon.names) for d in dropped], guard.rails)


def ask(question: str, summary: dict, **kwargs) -> Answer:
    return asyncio.run(ask_async(question, summary, **kwargs))


def model_client_from_env():
    from code_checker.team import model_client_from_env as build

    return build()
