"""LangSmith izləmə (gün 10): açar yoxdursa heç nə göndərilmir, varsa LLM çağırışı iz verir."""

from unittest.mock import MagicMock

import langsmith
from langsmith.run_helpers import tracing_context

from pipeline.providers import complete_with_fallback, complete_with_fallback_detail


def test_disabled_tracing_sends_nothing(monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    client = MagicMock(spec=langsmith.Client)
    with tracing_context(enabled=False, client=client):
        assert complete_with_fallback("s", "u", ["x"], {"x": lambda s, u: "cavab"}) == "cavab"
    assert not client.method_calls


def test_enabled_tracing_records_llm_run():
    client = MagicMock(spec=langsmith.Client)
    with tracing_context(enabled=True, client=client, project_name="test"):
        text, provider, _ = complete_with_fallback_detail("sistem", "sual", ["x"], {"x": lambda s, u: "cavab"})
    assert (text, provider) == ("cavab", "x")
    names = {call[0] for call in client.method_calls}
    assert names & {"create_run", "multipart_ingest", "batch_ingest_runs"}
