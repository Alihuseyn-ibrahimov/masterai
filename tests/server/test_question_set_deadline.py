"""Bankın emalı ümumi vaxt tavanını keçəndə «hazırlanır»da qalmamalıdır
(2026-11-02: produksiyada bank 7 dəqiqə «hazırlanır» göstərdi)."""
import asyncio
import threading

from pipeline.models import MaterialSource, MCQQuestion, PipelineResult
from server import app as app_module
from server.question_set_store import QuestionSetStore


def _bank(store: QuestionSetStore) -> int:
    return store.create(created_by=1, subject="qanunvericilik", title="T", material_kind="link",
                        material_location="https://example.az")["id"]


def test_deadline_marks_bank_failed_and_ignores_late_result(monkeypatch):
    monkeypatch.setattr(app_module, "QUESTION_SET_DEADLINE_SECONDS", 0.05)
    store = QuestionSetStore(":memory:")
    bank_id = _bank(store)
    release = threading.Event()

    def slow_generator(source, question_count, **_):
        release.wait(2)
        return PipelineResult(
            questions=[MCQQuestion(question="S?", options=list("ABCDE"), correct_index=0, explanation="i")],
            source=source, chunks_processed=1, chunks_failed=0, requested_question_count=1,
        )

    source = MaterialSource(kind="link", location="https://example.az")
    asyncio.run(app_module._process_question_set(
        bank_id, source, generator=slow_generator, question_set_store=store,
    ))
    release.set()

    bank = store.get(bank_id)
    assert bank["status"] == "failed"
    assert bank["error"] == app_module.QUESTION_SET_DEADLINE_ERROR
    assert store.list_questions(bank_id) == []


def test_llm_clients_have_explicit_timeouts(monkeypatch):
    """SDK defoltları (Anthropic 600 san, 2 təkrar) fallback-ı gecikdirirdi."""
    from pipeline import providers

    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    import anthropic
    import groq

    seen = {}
    monkeypatch.setattr(groq, "Groq", lambda **kw: seen.setdefault("groq", kw))
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: seen.setdefault("claude", kw))
    providers._groq_completer("m")
    providers._claude_completer("m")
    assert seen["groq"]["timeout"] == providers.GROQ_TIMEOUT
    assert seen["claude"]["timeout"] == providers.CLAUDE_TIMEOUT
    assert seen["groq"]["max_retries"] == seen["claude"]["max_retries"] == 1
