"""Gün 17: vLLM provayderi (OpenAI-uyğun API), provayder sırası, sürət ölçməsi, Colab notebook-u."""

import ast
import json
from pathlib import Path

import httpx
import pytest

from ml import bench_llm
from pipeline import providers
from pipeline.providers import complete_with_fallback, openai_compatible_completer, parse_order

ROOT = Path(__file__).resolve().parents[1]


def test_parse_order():
    assert parse_order("vllm, groq,claude") == ["vllm", "groq", "claude"]
    assert parse_order("VLLM,gorq,groq,groq") == ["vllm", "groq"]   # yazı səhvi və təkrar atılır
    assert parse_order("") == ["groq", "claude", "ollama"]
    assert parse_order(None) == ["groq", "claude", "ollama"]
    assert parse_order("bilinməz") == ["groq", "claude", "ollama"]


def _chat_transport(seen, *, content="Cavab", finish="stop", status=200):
    def handler(request: httpx.Request):
        seen.append(request)
        if status != 200:
            return httpx.Response(status, json={"error": "x"})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}, "finish_reason": finish}]})

    return httpx.MockTransport(handler)


def test_openai_compatible_completer_request_shape():
    seen = []
    complete = openai_compatible_completer("http://gpu:8000/", "masterai-mcq", api_key="k", max_tokens=123,
                                           temperature=0.1, transport=_chat_transport(seen))
    assert complete("Sistem", "Sual") == "Cavab"
    request = seen[0]
    assert request.url.path == "/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer k"
    body = json.loads(request.content)
    assert body["model"] == "masterai-mcq" and body["max_tokens"] == 123 and body["temperature"] == 0.1
    assert body["messages"] == [{"role": "system", "content": "Sistem"}, {"role": "user", "content": "Sual"}]


def test_truncated_or_failed_answer_falls_back_to_next_provider():
    truncated = openai_compatible_completer("http://gpu", "m", transport=_chat_transport([], finish="length"))
    with pytest.raises(RuntimeError, match="kəsildi"):
        truncated("s", "u")
    down = openai_compatible_completer("http://gpu", "m", transport=_chat_transport([], status=502))
    groq = lambda s, u: "groq cavabı"  # noqa: E731
    assert complete_with_fallback("s", "u", ["vllm", "groq"], {"vllm": down, "groq": groq}) == "groq cavabı"


def test_build_completers_adds_vllm_only_when_configured(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(providers, "VLLM_BASE_URL", "")
    assert "vllm" not in providers.build_completers()
    monkeypatch.setattr(providers, "VLLM_BASE_URL", "http://gpu:8000")
    assert "vllm" in providers.build_completers()


# ---- sürət ölçməsi --------------------------------------------------------------

def _sse_transport(tokens=5, status=200):
    def handler(request: httpx.Request):
        body = json.loads(request.content)
        assert body["stream"] is True and body["stream_options"] == {"include_usage": True}
        if status != 200:
            return httpx.Response(status, text="GPU yoxdur")
        events = [{"choices": [{"delta": {"content": f"t{i} "}}]} for i in range(tokens)]
        events.append({"choices": [], "usage": {"completion_tokens": tokens}})
        lines = "".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"
        return httpx.Response(200, text=lines, headers={"content-type": "text/event-stream"})

    return httpx.MockTransport(handler)


def test_bench_measures_levels(tmp_path, capsys):
    out = tmp_path / "b.json"
    code = bench_llm.main(["--url", "http://gpu", "--concurrency", "1,3", "--requests", "3", "--out", str(out)],
                          transport=_sse_transport(tokens=7))
    assert code == 0
    levels = json.loads(out.read_text(encoding="utf-8"))["levels"]
    assert [lvl["concurrency"] for lvl in levels] == [1, 3]
    assert all(lvl["ok"] == 3 and lvl["errors"] == 0 and lvl["ttft_p50"] is not None for lvl in levels)
    assert levels[0]["throughput_tokens_per_s"] > 0
    assert "tok/s (cəmi)" in capsys.readouterr().out


def test_bench_reports_errors(capsys):
    assert bench_llm.main(["--url", "http://gpu", "--concurrency", "1", "--requests", "2"],
                          transport=_sse_transport(status=503)) == 1
    assert "HTTP 503" in capsys.readouterr().out


def test_percentile_and_default_prompt():
    assert bench_llm.percentile([], 0.5) is None
    assert bench_llm.percentile([3, 1, 2], 0.5) == 2
    system, user = bench_llm.sample_prompts(None, 1)[0]
    assert "Material:\n---\n" in user and "Konstitusiya" in user


# ---- notebook ---------------------------------------------------------------------

def _python_of(source: str) -> str:
    kept, shell = [], False
    for line in source.splitlines():
        if shell or line.lstrip().startswith(("!", "%")):
            shell = line.rstrip().endswith("\\")
            continue
        kept.append(line)
    return "\n".join(kept)


def test_vllm_notebook_valid():
    nb = json.loads((ROOT / "ml" / "vllm_serve.ipynb").read_text(encoding="utf-8"))
    code = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
    for source in code:
        ast.parse(_python_of(source))
    joined = "\n".join(code)
    assert '"vllm==' in joined and '"--dtype", "half"' in joined and '"--api-key", API_KEY' in joined
    assert "ml.bench_llm" in joined and "trycloudflare" in joined and "LLM_ORDER=vllm,groq,claude" in joined
