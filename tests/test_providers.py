import logging

import pytest

from pipeline.providers import (
    DEFAULT_ORDER,
    AllProvidersFailed,
    complete_with_fallback,
    complete_with_fallback_detail,
)


def _ok(text: str):
    def completer(system: str, user: str) -> str:
        return text
    return completer


def _boom(message: str = "saxta xəta"):
    def completer(system: str, user: str) -> str:
        raise RuntimeError(message)
    return completer


class TestCompleteWithFallbackDetail:
    def test_first_provider_success_short_circuits_rest(self):
        called = {"claude": False}

        def claude(system, user):
            called["claude"] = True
            return "claude cavabı"

        completers = {"groq": _ok("groq cavabı"), "claude": claude}
        text, provider, errors = complete_with_fallback_detail(
            "sys", "user", ["groq", "claude"], completers
        )

        assert text == "groq cavabı"
        assert provider == "groq"
        assert errors == []
        assert called["claude"] is False

    def test_falls_through_to_second_provider_on_failure(self):
        completers = {"groq": _boom("groq 429"), "claude": _ok("claude cavabı")}
        text, provider, errors = complete_with_fallback_detail(
            "sys", "user", ["groq", "claude"], completers
        )

        assert text == "claude cavabı"
        assert provider == "claude"
        assert len(errors) == 1
        assert "groq" in errors[0]

    def test_falls_through_to_third_provider_ollama(self):
        completers = {
            "groq": _boom("groq xətası"),
            "claude": _boom("claude xətası"),
            "ollama": _ok("ollama cavabı"),
        }
        text, provider, errors = complete_with_fallback_detail(
            "sys", "user", DEFAULT_ORDER, completers
        )

        assert text == "ollama cavabı"
        assert provider == "ollama"
        assert len(errors) == 2

    def test_skips_provider_missing_from_completers_dict(self):
        # groq üçün API açarı yoxdursa, build_completers() onu dict-ə əlavə
        # etmir — fallback bunu susmadan keçib növbətiyə düşməlidir.
        completers = {"claude": _ok("claude cavabı")}
        text, provider, errors = complete_with_fallback_detail(
            "sys", "user", DEFAULT_ORDER, completers
        )

        assert text == "claude cavabı"
        assert provider == "claude"

    def test_raises_all_providers_failed_when_all_fail(self):
        completers = {"groq": _boom("a"), "claude": _boom("b"), "ollama": _boom("c")}
        with pytest.raises(AllProvidersFailed):
            complete_with_fallback_detail("sys", "user", DEFAULT_ORDER, completers)

    def test_raises_all_providers_failed_when_completers_empty(self):
        with pytest.raises(AllProvidersFailed):
            complete_with_fallback_detail("sys", "user", DEFAULT_ORDER, {})

    def test_logs_failure_and_success(self, caplog):
        completers = {"groq": _boom("groq xətası"), "claude": _ok("ok")}
        with caplog.at_level(logging.INFO, logger="masterai.pipeline.providers"):
            complete_with_fallback_detail("sys", "user", ["groq", "claude"], completers)

        messages = [r.message for r in caplog.records]
        assert any("llm_failed" in m and "groq" in m for m in messages)
        assert any("llm_ok" in m and "claude" in m for m in messages)


class TestCompleteWithFallback:
    def test_returns_only_text(self):
        completers = {"groq": _ok("cavab mətni")}
        assert complete_with_fallback("sys", "user", ["groq"], completers) == "cavab mətni"
