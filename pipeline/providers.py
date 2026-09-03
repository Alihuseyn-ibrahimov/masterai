"""LLM provayder qatı — Groq/Claude/Ollama completer-ləri və fallback məntiqi.

`complete_with_fallback[_detail]` təmiz məntiqdir (mock completer ilə test
olunur); faktiki şəbəkə completer-ləri `build_completers()`-dədir. Naxış
dildostu/server/dildostu_server/providers.py-dən götürülüb.
"""

from __future__ import annotations

import logging
import os
from typing import Callable

Completer = Callable[[str, str], str]  # (system, user) -> text

# `llama-3.3-70b-versatile` Groq tərəfindən dayandırılıb (real production-da
# 404 model_not_found ilə tapıldı, bax masterai/CLAUDE.md) — `client.models.
# list()` ilə hesabın canlı model siyahısi yoxlanıb, `openai/gpt-oss-120b`
# seçilib (mövcud olanlar arasında ən böyük ümumi-təyinatlı chat model).
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:32b")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

AI_TEMPERATURE = float(os.environ.get("AI_TEMPERATURE", "0.5"))

DEFAULT_ORDER = ["groq", "claude", "ollama"]

logger = logging.getLogger("masterai.pipeline.providers")


class AllProvidersFailed(Exception):
    """Sıradakı bütün provayderlər uğursuz oldu."""


def complete_with_fallback_detail(
    system: str,
    user: str,
    order: list[str],
    completers: dict[str, Completer],
) -> tuple[str, str, list[str]]:
    """`order` sırası ilə provayderləri sına; ilk uğurlu cavabı qaytar.

    Qaytarır: (cavab, uğurlu provayderin adı, uğursuz provayderlərin xətaları).
    Provayder `completers`-də yoxdursa (məs. API açarı verilməyib) susmadan
    keçilir. Hamısı uğursuzsa `AllProvidersFailed` atılır.
    """
    errors: list[str] = []
    for name in order:
        completer = completers.get(name)
        if completer is None:
            continue
        try:
            text = completer(system, user)
            logger.info("llm_ok provider=%s", name)
            return text, name, errors
        except Exception as exc:  # noqa: BLE001 — fallback üçün geniş tutuş
            logger.warning("llm_failed provider=%s error=%s", name, exc)
            errors.append(f"{name}: {exc}")

    logger.error("llm_all_failed order=%s errors=%s", order, errors)
    raise AllProvidersFailed("; ".join(errors) or "provayder yoxdur")


def complete_with_fallback(
    system: str,
    user: str,
    order: list[str],
    completers: dict[str, Completer],
) -> str:
    text, _provider, _errors = complete_with_fallback_detail(system, user, order, completers)
    return text


def build_completers() -> dict[str, Completer]:
    """Mövcud API açarlarına görə Groq/Claude completer-lərini qur, Ollama
    həmişə əlavə olunur (lokal, açar tələb etmir — server işləmirsə fallback
    zamanı özü xəta verəcək)."""
    from dotenv import load_dotenv

    load_dotenv()
    completers: dict[str, Completer] = {}
    if os.environ.get("GROQ_API_KEY"):
        completers["groq"] = _groq_completer(GROQ_MODEL)
    if os.environ.get("ANTHROPIC_API_KEY"):
        completers["claude"] = _claude_completer(CLAUDE_MODEL)
    completers["ollama"] = _ollama_completer(OLLAMA_MODEL, OLLAMA_HOST)
    return completers


def _groq_completer(model: str) -> Completer:
    import groq

    client = groq.Groq(api_key=os.environ["GROQ_API_KEY"])

    def complete(system: str, user: str) -> str:
        resp = client.chat.completions.create(
            model=model,
            temperature=AI_TEMPERATURE,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content

    return complete


def _claude_completer(model: str) -> Completer:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def complete(system: str, user: str) -> str:
        resp = client.messages.create(
            model=model,
            max_tokens=2048,
            temperature=AI_TEMPERATURE,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in resp.content if b.type == "text")

    return complete


def _ollama_completer(model: str, host: str) -> Completer:
    import ollama

    client = ollama.Client(host=host)

    def complete(system: str, user: str) -> str:
        resp = client.chat(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp["message"]["content"]

    return complete
