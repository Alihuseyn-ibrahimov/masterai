import pytest

from server.app import _notify_admin_webhook


class _RaisingAsyncClient:
    """httpx.AsyncClient əvəzi — çağırılarsa testi sındırır (URL yoxdursa
    heç çağırılmamalıdır)."""

    def __init__(self, *args, **kwargs):
        raise AssertionError("ADMIN_WEBHOOK_URL təyin olunmayıbsa httpx.AsyncClient YARADILMAMALIDIR")


class _RecordingAsyncClient:
    calls: list = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json):
        _RecordingAsyncClient.calls.append((url, json))


class _FailingAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json):
        raise ConnectionError("əlçatmaz")


@pytest.mark.asyncio
async def test_noop_when_url_not_set(monkeypatch):
    monkeypatch.delenv("ADMIN_WEBHOOK_URL", raising=False)
    monkeypatch.setattr("server.app.httpx.AsyncClient", _RaisingAsyncClient)

    await _notify_admin_webhook({"material_id": 1})  # istisna atmamalıdır


@pytest.mark.asyncio
async def test_posts_payload_when_url_set(monkeypatch):
    monkeypatch.setenv("ADMIN_WEBHOOK_URL", "https://n8n.example/webhook/masterai-material-failed")
    _RecordingAsyncClient.calls.clear()
    monkeypatch.setattr("server.app.httpx.AsyncClient", _RecordingAsyncClient)

    payload = {"material_id": 5, "chat_id": 2, "kind": "pdf", "location": "/a.pdf", "error": "xəta"}
    await _notify_admin_webhook(payload)

    assert len(_RecordingAsyncClient.calls) == 1
    url, sent_json = _RecordingAsyncClient.calls[0]
    assert url == "https://n8n.example/webhook/masterai-material-failed"
    assert sent_json == payload


@pytest.mark.asyncio
async def test_swallows_network_errors(monkeypatch):
    monkeypatch.setenv("ADMIN_WEBHOOK_URL", "https://n8n.example/webhook/masterai-material-failed")
    monkeypatch.setattr("server.app.httpx.AsyncClient", _FailingAsyncClient)

    await _notify_admin_webhook({"material_id": 1})  # istisna YUXARI ÖTÜRÜLMƏMƏLİDİR
