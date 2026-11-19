"""Səhv Detektivi adapterini OpenAI-uyğun API ilə vermək - vLLM qalxmayanda ehtiyat yol.

    python -m ml.sehv_serve --adapter /content/drive/MyDrive/sehv-detektivi/sehv-lora-v3 --api-key KEY

masterai-nin `VllmBackend`-i yalnız `POST /v1/chat/completions` çağırır, ona görə bu kiçik server
vLLM-in yerinə keçə bilir: eyni ünvan, eyni `"model": "sehv"`, eyni `.env` sətirləri. Generasiya
transformers + peft ilə (fp16, greedy, `max_tokens`), sorğular növbə ilədir (bir GPU, bir model).
Niyə lazımdır: Colab Python-u dəyişəndə sabit vLLM versiyası quraşdırılmır (2026-11-19-da belə oldu),
T4-də yeni vLLM-in işləyəcəyi də zəmanətli deyil. Bir tələbənin sorğusu üçün bu sürət bəs edir.

Yalnız stdlib server: Colab-da əlavə paket lazım deyil (torch/transformers/peft onsuz da var).
"""

from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_BASE = "Qwen/Qwen2.5-1.5B-Instruct"


def load_generator(adapter: str, base: str = DEFAULT_BASE):
    """(messages, max_tokens) -> (mətn, finish_reason). Model bir dəfə yüklənir."""
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(base)
    model = AutoModelForCausalLM.from_pretrained(base, dtype=torch.float16, device_map="auto")
    model = PeftModel.from_pretrained(model, adapter).eval()

    def generate(messages, max_tokens):
        prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tok(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=max_tokens, do_sample=False,
                                 pad_token_id=tok.eos_token_id)
        new = out[0, inputs["input_ids"].shape[1]:]
        finished = len(new) < max_tokens or int(new[-1]) == tok.eos_token_id
        return tok.decode(new, skip_special_tokens=True), "stop" if finished else "length"

    return generate


def make_handler(generate, model_name: str, api_key: str = ""):
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body):
            data = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):  # həll mətni jurnala düşməsin
            pass

        def do_GET(self):
            if self.path == "/health":
                return self._send(200, {"status": "ok"})
            if self.path == "/v1/models":
                return self._send(200, {"data": [{"id": model_name, "object": "model"}]})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/v1/chat/completions":
                return self._send(404, {"error": "not found"})
            if api_key and self.headers.get("Authorization") != f"Bearer {api_key}":
                return self._send(401, {"error": "unauthorized"})
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                messages = body["messages"]
            except (ValueError, KeyError):
                return self._send(400, {"error": "messages tələb olunur"})
            if body.get("model") != model_name:
                return self._send(404, {"error": f"model yalnız {model_name}"})
            max_tokens = min(int(body.get("max_tokens") or 200), 1024)
            with lock:
                text, finish = generate(messages, max_tokens)
            self._send(200, {"object": "chat.completion", "model": model_name, "choices": [
                {"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": finish}]})

    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--model-name", default="sehv")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    generate = load_generator(args.adapter, args.base)
    server = ThreadingHTTPServer(("0.0.0.0", args.port), make_handler(generate, args.model_name, args.api_key))
    print(f"hazırdır: http://localhost:{args.port} (model={args.model_name})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
