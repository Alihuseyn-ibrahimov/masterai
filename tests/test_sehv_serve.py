"""ml/sehv_serve: vLLM qalxmayanda eyni API. masterai-nin VllmBackend-i real HTTP ilə ona qoşulur."""

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from ml.sehv_serve import make_handler
from pipeline.sehv_detektivi import VllmBackend, diagnose


@pytest.fixture
def server():
    calls = []

    def generate(messages, max_tokens):
        calls.append((messages, max_tokens))
        return json.dumps({"wrong_step": 2, "error_type": "ters_netice", "explanation": "Tərs."},
                          ensure_ascii=False), "stop"

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(generate, "sehv", "KEY"))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", calls
    httpd.shutdown()


def test_backend_talks_to_fallback_server(server):
    url, calls = server
    backend = VllmBackend(url, "sehv", api_key="KEY")
    out = diagnose("mentiq", "?", ["Yağış yağırsa yol yaşdır", "Yol yaşdır, deməli yağıb"], backend)
    assert out["status"] == "error_found" and out["error_type"] == "ters_netice" and out["source"] == "model"
    messages, max_tokens = calls[0]
    assert messages[0]["role"] == "system" and messages[-1]["role"] == "user" and max_tokens == 200


def _post(url, body, key="KEY"):
    req = urllib.request.Request(f"{url}/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        return urllib.request.urlopen(req).status
    except urllib.error.HTTPError as exc:
        return exc.code


def test_auth_model_and_health(server):
    url, _ = server
    msgs = [{"role": "user", "content": "x"}]
    assert _post(url, {"model": "sehv", "messages": msgs}, key="wrong") == 401
    assert _post(url, {"model": "receipts", "messages": msgs}) == 404
    assert _post(url, {"model": "sehv"}) == 400
    assert urllib.request.urlopen(f"{url}/health").status == 200
