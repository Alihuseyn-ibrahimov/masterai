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


_TELEGRAM_VARS = (
    "ADMIN_TELEGRAM_BOT_TOKEN",
    "ADMIN_TELEGRAM_CHAT_ID",
    "BACKUP_TELEGRAM_BOT_TOKEN",
    "BACKUP_TELEGRAM_CHAT_ID",
)


@pytest.fixture(autouse=True)
def _no_telegram_keys(monkeypatch):
    for name in _TELEGRAM_VARS:
        monkeypatch.delenv(name, raising=False)


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


_FAILED = {"material_id": 7, "chat_id": 3, "kind": "url", "location": "https://a.az", "error": "403"}


@pytest.mark.asyncio
async def test_telegram_uses_backup_bot_when_no_admin_bot(monkeypatch):
    monkeypatch.delenv("ADMIN_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("BACKUP_TELEGRAM_BOT_TOKEN", "111:abc")
    monkeypatch.setenv("BACKUP_TELEGRAM_CHAT_ID", "42")
    _RecordingAsyncClient.calls.clear()
    monkeypatch.setattr("server.app.httpx.AsyncClient", _RecordingAsyncClient)

    await _notify_admin_webhook(_FAILED)

    assert len(_RecordingAsyncClient.calls) == 1
    url, body = _RecordingAsyncClient.calls[0]
    assert url == "https://api.telegram.org/bot111:abc/sendMessage"
    assert body["chat_id"] == "42"
    assert "Material #7" in body["text"] and "https://a.az" in body["text"] and "403" in body["text"]


@pytest.mark.asyncio
async def test_admin_bot_wins_over_backup_bot(monkeypatch):
    monkeypatch.delenv("ADMIN_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("BACKUP_TELEGRAM_BOT_TOKEN", "111:abc")
    monkeypatch.setenv("BACKUP_TELEGRAM_CHAT_ID", "42")
    monkeypatch.setenv("ADMIN_TELEGRAM_BOT_TOKEN", "222:xyz")
    monkeypatch.setenv("ADMIN_TELEGRAM_CHAT_ID", "99")
    _RecordingAsyncClient.calls.clear()
    monkeypatch.setattr("server.app.httpx.AsyncClient", _RecordingAsyncClient)

    await _notify_admin_webhook(_FAILED)

    url, body = _RecordingAsyncClient.calls[0]
    assert url == "https://api.telegram.org/bot222:xyz/sendMessage"
    assert body["chat_id"] == "99"


@pytest.mark.asyncio
async def test_webhook_and_telegram_both_sent(monkeypatch):
    monkeypatch.setenv("ADMIN_WEBHOOK_URL", "https://n8n.example/webhook/x")
    monkeypatch.setenv("BACKUP_TELEGRAM_BOT_TOKEN", "111:abc")
    monkeypatch.setenv("BACKUP_TELEGRAM_CHAT_ID", "42")
    _RecordingAsyncClient.calls.clear()
    monkeypatch.setattr("server.app.httpx.AsyncClient", _RecordingAsyncClient)

    await _notify_admin_webhook(_FAILED)

    assert [c[0] for c in _RecordingAsyncClient.calls] == [
        "https://n8n.example/webhook/x",
        "https://api.telegram.org/bot111:abc/sendMessage",
    ]


@pytest.mark.asyncio
async def test_telegram_needs_both_keys(monkeypatch):
    monkeypatch.delenv("ADMIN_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("BACKUP_TELEGRAM_BOT_TOKEN", "111:abc")
    monkeypatch.setattr("server.app.httpx.AsyncClient", _RaisingAsyncClient)

    await _notify_admin_webhook(_FAILED)


@pytest.mark.asyncio
async def test_telegram_network_error_is_swallowed(monkeypatch):
    monkeypatch.delenv("ADMIN_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("BACKUP_TELEGRAM_BOT_TOKEN", "111:abc")
    monkeypatch.setenv("BACKUP_TELEGRAM_CHAT_ID", "42")
    monkeypatch.setattr("server.app.httpx.AsyncClient", _FailingAsyncClient)

    await _notify_admin_webhook(_FAILED)  # istisna YUXARI ÖTÜRÜLMƏMƏLİDİR
