"""LLM serving sürətinin ölçülməsi (gün 17): vLLM, Groq və ya istənilən OpenAI-uyğun API.

    python -m ml.bench_llm --url https://<tunel>.trycloudflare.com --model masterai-mcq \
        --api-key $VLLM_API_KEY --concurrency 1,4,8 --requests 16
    python -m ml.bench_llm --groq --concurrency 1,4      # müqayisə üçün

Hər sorğu axınla (`stream: true`) göndərilir, ona görə üç rəqəm ölçülür:
- **TTFT** - ilk tokenə qədər vaxt (istifadəçinin «gözləmə» hissi);
- **gecikmə** - tam cavab müddəti (p50 / p95);
- **ötürmə qabiliyyəti** - bütün paralel sorğular üzrə saniyədə token.

vLLM-in üstünlüyü paralel yükdə görünür: continuous batching yeni sorğunu gedən
batch-a qoşur, PagedAttention KV-keşi səhifələrlə saxlayır - eyni GPU-da 8
paralel sorğunun cəmi ötürmə qabiliyyəti 1 sorğununkundan qat-qat yüksək olur.

Prompt: `--val` verilsə QLoRA val dəstinin produksiya promptları, yoxsa eval
materialından qurulmuş tipik sual generasiyası promptu.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

GROQ_URL = "https://api.groq.com/openai"


@dataclass
class Result:
    ok: bool
    latency: float = 0.0
    ttft: float | None = None
    tokens: int = 0
    error: str = ""


def sample_prompts(val_path: str | None, limit: int) -> list[tuple[str, str]]:
    if val_path:
        with open(val_path, encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh if line.strip()]
        return [(r["messages"][0]["content"], r["messages"][1]["content"]) for r in rows[:limit]]
    from evals.run import load_documents
    from pipeline.generation import SYSTEM_PROMPT, user_prompt

    text = "\n\n".join(d.text for d in load_documents())
    return [(SYSTEM_PROMPT, user_prompt(text, 3))]


def stream_once(client, model: str, system: str, user: str, max_tokens: int) -> Result:
    started = time.perf_counter()
    ttft, pieces, tokens = None, 0, None
    try:
        with client.stream("POST", "/v1/chat/completions", json={
            "model": model, "stream": True, "stream_options": {"include_usage": True},
            "max_tokens": max_tokens, "temperature": 0.3,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }) as resp:
            if resp.status_code != 200:
                resp.read()
                return Result(False, error=f"HTTP {resp.status_code}: {resp.text[:120]}")
            for line in resp.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                event = json.loads(data)
                if event.get("usage"):
                    tokens = event["usage"].get("completion_tokens", tokens)
                for choice in event.get("choices") or []:
                    if (choice.get("delta") or {}).get("content"):
                        if ttft is None:
                            ttft = time.perf_counter() - started
                        pieces += 1
    except Exception as exc:  # noqa: BLE001 - şəbəkə xətası da ölçmənin nəticəsidir
        return Result(False, error=str(exc)[:120])
    # Server usage verməsə, axın hissələrinin sayı token sayına yaxındır (vLLM hər tokeni ayrıca göndərir).
    return Result(True, time.perf_counter() - started, ttft, tokens if tokens is not None else pieces)


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


def run_level(client, model: str, prompts, concurrency: int, requests: int, max_tokens: int) -> dict:
    jobs = [prompts[i % len(prompts)] for i in range(requests)]
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(lambda p: stream_once(client, model, p[0], p[1], max_tokens), jobs))
    wall = time.perf_counter() - started
    good = [r for r in results if r.ok]
    latencies = [r.latency for r in good]
    ttfts = [r.ttft for r in good if r.ttft is not None]
    total_tokens = sum(r.tokens for r in good)
    per_request = [r.tokens / r.latency for r in good if r.latency > 0]
    rnd = lambda v, n=2: round(v, n) if v is not None else None  # noqa: E731
    return {
        "concurrency": concurrency, "requests": requests, "ok": len(good), "errors": len(results) - len(good),
        "latency_p50": rnd(percentile(latencies, 0.5)), "latency_p95": rnd(percentile(latencies, 0.95)),
        "ttft_p50": rnd(percentile(ttfts, 0.5), 3),
        "tokens_per_s_per_request": rnd(statistics.mean(per_request), 1) if per_request else None,
        "throughput_tokens_per_s": rnd(total_tokens / wall, 1) if wall > 0 else None,
        "first_error": next((r.error for r in results if not r.ok), ""),
    }


def format_table(rows: list[dict]) -> str:
    head = ["paralel", "uğurlu", "p50 san", "p95 san", "TTFT san", "tok/s (1 sorğu)", "tok/s (cəmi)"]
    keys = ["concurrency", "ok", "latency_p50", "latency_p95", "ttft_p50", "tokens_per_s_per_request",
            "throughput_tokens_per_s"]
    lines = ["  ".join(h.ljust(15) for h in head)]
    for row in rows:
        cells = [f"{row['ok']}/{row['requests']}" if k == "ok" else str(row[k] if row[k] is not None else "—")
                 for k in keys]
        lines.append("  ".join(c.ljust(15) for c in cells))
        if row["errors"]:
            lines.append(f"    xəta ({row['errors']}): {row['first_error']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None, transport=None) -> int:
    import httpx

    parser = argparse.ArgumentParser(description="OpenAI-uyğun LLM API-nin sürət ölçməsi")
    parser.add_argument("--url", default=os.environ.get("VLLM_BASE_URL", ""))
    parser.add_argument("--model", default=os.environ.get("VLLM_MODEL", "masterai-mcq"))
    parser.add_argument("--api-key", default=os.environ.get("VLLM_API_KEY", ""))
    parser.add_argument("--groq", action="store_true", help="Groq-un OpenAI-uyğun API-si (GROQ_API_KEY)")
    parser.add_argument("--val", help="QLoRA val.jsonl - produksiya promptları")
    parser.add_argument("--concurrency", default="1,4,8")
    parser.add_argument("--requests", type=int, default=8, help="hər səviyyədə sorğu sayı")
    parser.add_argument("--max-tokens", type=int, default=800)
    parser.add_argument("--out", help="nəticəni JSON-a yaz")
    args = parser.parse_args(argv)

    if args.groq:
        from pipeline.providers import GROQ_MODEL

        args.url, args.api_key = GROQ_URL, os.environ.get("GROQ_API_KEY", "")
        args.model = args.model if args.model != "masterai-mcq" else GROQ_MODEL
    if not args.url:
        parser.error("--url (və ya VLLM_BASE_URL) lazımdır")
    headers = {"Authorization": f"Bearer {args.api_key}"} if args.api_key else {}
    levels = [int(n) for n in args.concurrency.split(",") if n.strip()]
    prompts = sample_prompts(args.val, limit=max(levels) * 2)
    with httpx.Client(base_url=args.url.rstrip("/"), headers=headers, timeout=180, transport=transport) as client:
        rows = [run_level(client, args.model, prompts, c, max(args.requests, c), args.max_tokens) for c in levels]
    print(f"{args.url} · {args.model} · {len(prompts)} prompt")
    print(format_table(rows))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump({"url": args.url, "model": args.model, "levels": rows}, fh, ensure_ascii=False, indent=2)
    return 0 if all(r["ok"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
