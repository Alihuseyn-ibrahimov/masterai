"""İki agentli kod yoxlama komandası (AutoGen AgentChat, gün 19).

    testlər (Docker, LLM-siz) ──▶ Yoxlayıcı ──(alət: run_experiment, Docker)──▶ Mentor ──▶ rəy

- **Testlər** əvvəlcə LLM-siz işləyir: bal YALNIZ onlardandır, AI qiymət vermir.
- **Yoxlayıcı** (`AssistantAgent` + alət): tələbənin kodunu və test nəticəsini oxuyur,
  şübhəli halları özü yoxlamaq üçün `run_experiment` alətini çağırır - qısa Python
  parçası eyni Docker sandbox-unda, tələbənin `solution.py`-si yanında işləyir.
  Səhvin SƏBƏBİNİ tapır (hansı halda, niyə).
- **Mentor**: tələbəyə Azərbaycan dilində rəy yazır - nə düzgündür, nə səhvdir, bir
  ipucu. Tam həlli YAZMIR (`strip_solution` uzun kod bloklarını ayrıca da silir).
  «YEKUN» sözü ilə bitirir - komanda dayanır (`TextMentionTermination`).

Model: OpenAI-uyğun API (alət çağırışı lazımdır): Groq və ya öz vLLM modelimiz
(gün 17). Komanda müəllimin kompüterində işləyir (Docker lazımdır), serverə qoyulmur.
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
from autogen_agentchat.messages import TextMessage
from autogen_agentchat.teams import RoundRobinGroupChat

from code_checker.exercises import Exercise, CheckReport, run_tests
from code_checker.sandbox import run_python

REVIEWER_PROMPT = (
    "Sən Python kodu yoxlayıcısısan. Sənə tapşırıq, tələbənin kodu və avtomatik testlərin nəticəsi verilir. "
    "Səhvin SƏBƏBİNİ tap: hansı girişdə və niyə səhv işləyir. Lazım olsa run_experiment alətini çağır: "
    "ona qısa Python kodu ver (məs. `from solution import f; print(f([...]))`), o, tələbənin kodu yanında "
    "təhlükəsiz sandbox-da işləyəcək. Testlər hamısı keçibsə, kodun oxunaqlılığına və kənar hallara bax. "
    "Qısa, texniki yaz. Tələbəyə müraciət etmə - mentor edəcək."
)
MENTOR_PROMPT = (
    "Sən MasterAI kursunun mentorusan. Yoxlayıcının qeydlərinə əsasən tələbəyə Azərbaycan dilində, mehriban "
    "və qısa rəy yaz: 1) nə yaxşı alınıb, 2) nə səhvdir və hansı halda, 3) bir ipucu. TAM HƏLLİ YAZMA, "
    "düzəldilmiş funksiyanı vermə - tələbə özü düzəltməlidir. Ən çox 2 sətirlik kod nümunəsi olar. "
    "Rəyin sonunda ayrıca sətirdə YEKUN yaz."
)
_CODE_BLOCK = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.DOTALL)
GROQ_OPENAI_URL = "https://api.groq.com/openai/v1"


def strip_solution(text: str, max_lines: int = 3) -> str:
    """Mentor tam həll yazıbsa (uzun kod bloku), bloku silir: tələbə özü düzəltməlidir."""
    def replace(match: re.Match) -> str:
        lines = [line for line in match.group(1).splitlines() if line.strip()]
        return match.group(0) if len(lines) <= max_lines else "(kod nümunəsi silindi: həlli özün yaz)"

    return _CODE_BLOCK.sub(replace, text)


def model_client_from_env():
    """vLLM (`VLLM_BASE_URL`) varsa o, yoxsa Groq-un OpenAI-uyğun API-si."""
    from autogen_ext.models.openai import OpenAIChatCompletionClient

    from pipeline.providers import GROQ_MODEL

    info = {"vision": False, "function_calling": True, "json_output": False, "family": "unknown",
            "structured_output": False}
    if os.environ.get("VLLM_BASE_URL"):
        return OpenAIChatCompletionClient(model=os.environ.get("VLLM_MODEL", "masterai-mcq"),
                                          base_url=os.environ["VLLM_BASE_URL"].rstrip("/") + "/v1",
                                          api_key=os.environ.get("VLLM_API_KEY") or "none", model_info=info)
    return OpenAIChatCompletionClient(model=GROQ_MODEL, base_url=GROQ_OPENAI_URL,
                                      api_key=os.environ["GROQ_API_KEY"], model_info=info)


@dataclass
class Review:
    report: CheckReport
    feedback: str
    transcript: list[tuple[str, str]] = field(default_factory=list)


def task_text(exercise: Exercise, code: str, report: CheckReport) -> str:
    return (f"Tapşırıq: {exercise.title}\n{exercise.prompt}\n\nTələbənin kodu (solution.py):\n```python\n{code}\n```\n\n"
            f"Avtomatik testlər:\n{report.summary()}")


async def review_submission(exercise: Exercise, code: str, *, reviewer_client, mentor_client=None,
                            runner=run_python) -> Review:
    report = await asyncio.to_thread(run_tests, exercise, code, runner=runner)

    async def run_experiment(code_snippet: str) -> str:
        """Qısa Python kodunu tələbənin solution.py faylı yanında sandbox-da işlədir, çıxışı qaytarır."""
        result = await asyncio.to_thread(runner, {"solution.py": code},
                                         "import sys\nsys.path.insert(0, '/work')\n" + code_snippet, timeout=10)
        output = (result.stdout + ("\n" + result.stderr if result.stderr else "")).strip()
        return ("[vaxt həddi aşıldı]\n" if result.timed_out else "") + (output[-1500:] or "(çıxış yoxdur)")

    reviewer = AssistantAgent("yoxlayici", reviewer_client, tools=[run_experiment], system_message=REVIEWER_PROMPT,
                              reflect_on_tool_use=True, max_tool_iterations=3)
    mentor = AssistantAgent("mentor", mentor_client or reviewer_client, system_message=MENTOR_PROMPT)
    team = RoundRobinGroupChat(
        [reviewer, mentor],
        termination_condition=TextMentionTermination("YEKUN", sources=["mentor"]) | MaxMessageTermination(10),
    )
    result = await team.run(task=task_text(exercise, code, report))
    transcript = [(m.source, m.content if isinstance(m.content, str) else str(m.content))
                  for m in result.messages]
    mentor_texts = [m.content for m in result.messages if isinstance(m, TextMessage) and m.source == "mentor"]
    feedback = strip_solution(mentor_texts[-1].replace("YEKUN", "").strip()) if mentor_texts else ""
    return Review(report, feedback, transcript)


def review(exercise: Exercise, code: str, **kwargs) -> Review:
    return asyncio.run(review_submission(exercise, code, **kwargs))
