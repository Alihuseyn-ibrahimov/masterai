"""Rədd edilən WebSocket qoşulması SƏBƏBİ çatdırmalıdır.

REAL PRODUKSİYADA TAPILDI. Jurnalda hər 30 saniyədən bir təkrarlanan
sətir:

    "WebSocket /ws/live/347489/host?token=..." 403
    connection rejected (403 Forbidden)

Yəni müəllimin canlı sessiya konsolu qoşula bilmir və brauzer sonsuz
yenidən cəhd edir.

KÖK SƏBƏB. Server `accept()`-dən ƏVVƏL `close(code=4404)` çağırırdı.
Starlette bunu handshake rəddinə çevirir, brauzer isə HTTP 403 görür və
`onclose`-a **1006** (anormal) kodu gəlir. Bizim təyin etdiyimiz
4401/4403/4404/4409 kodları brauzerə HEÇ VAXT ÇATMIR.

Bu, real brauzerdə ölçüldü (minimal reproduksiya, Chromium):
    accept()-siz close(4404)      -> brauzer 1006 görür
    accept() + mesaj + close(4404) -> brauzer 4404 görür

Nəticə: `socket.js`-dəki `FATAL_CLOSE_CODES` siyahısı işə DÜŞMÜRDÜ,
çünki 1006 orada yoxdur. Client dayanmadan yenidən qoşulurdu və
istifadəçi səbəbi heç vaxt görmürdü.

Həll: əvvəl `accept()`, sonra səbəbi izah edən mesaj, sonra konkret
kodla `close()`. Qoşulma qısa müddət qəbul edilir, amma heç bir
məxfi məlumat göndərilmir.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server.app import (
    app,
    get_chat_store,
    get_live_session_store,
    get_message_store,
    get_question_set_store,
    get_token_secret,
    get_user_store,
)
from server.auth import create_token
from server.chat_store import ChatStore
from server.live_session_store import LiveSessionStore
from server.message_store import MessageStore
from server.question_set_store import QuestionSetStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


@pytest.fixture
def env():
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    messages = MessageStore(":memory:")
    question_sets = QuestionSetStore(":memory:")
    live_sessions = LiveSessionStore(":memory:")

    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_chat_store] = lambda: chats
    app.dependency_overrides[get_message_store] = lambda: messages
    app.dependency_overrides[get_question_set_store] = lambda: question_sets
    app.dependency_overrides[get_live_session_store] = lambda: live_sessions
    app.dependency_overrides[get_token_secret] = lambda: _SECRET

    client = TestClient(app)
    ali = users.create("ali@n.az", "hash", "Əli")
    kenar = users.create("kenar@n.az", "hash", "Kənar")
    chat = chats.create("group", ali["id"], name="11-A")
    chats.add_member(chat["id"], ali["id"])

    yield {
        "client": client, "users": users, "chats": chats,
        "live_sessions": live_sessions, "question_sets": question_sets,
        "ali": ali, "kenar": kenar, "chat_id": chat["id"],
    }
    app.dependency_overrides.clear()


def _token(user_id: int) -> str:
    return create_token(user_id, secret=_SECRET)


def _reason_and_code(client, url: str) -> tuple[dict, int]:
    """Qoşulur, səbəb mesajını və bağlanma kodunu qaytarır.

    Əgər server accept-dən əvvəl bağlasa, bu funksiya istisna atacaq —
    yəni testin özü naxışı qoruyur.
    """
    with client.websocket_connect(url) as ws:
        payload = ws.receive_json()
        closing = ws.receive()
    return payload, closing.get("code")


class TestChatWebsocket:
    def _url(self, chat_id: int, token: str) -> str:
        return f"/ws/chat/{chat_id}?token={token}"

    def test_invalid_token_is_explained_not_silently_dropped(self, env):
        payload, code = _reason_and_code(env["client"], self._url(env["chat_id"], "bu-token-deyil"))
        assert code == 4401
        assert payload["type"] == "error"
        assert payload["detail"], "səbəb boş olmamalıdır"

    def test_non_member_is_explained(self, env):
        payload, code = _reason_and_code(
            env["client"], self._url(env["chat_id"], _token(env["kenar"]["id"]))
        )
        assert code == 4403
        assert payload["type"] == "error"

    def test_unknown_chat_is_explained(self, env):
        payload, code = _reason_and_code(env["client"], self._url(999, _token(env["ali"]["id"])))
        assert code == 4404
        assert payload["type"] == "error"


class TestLiveHostWebsocket:
    def test_unknown_session_is_explained(self, env):
        """Ən çox rast gəlinən hal: sessiya artıq BİTİB və müəllimin
        səhifəsi köhnəlib. Səbəb göndərilməsə brauzerə 1006 çatır və
        səhifə sonsuz yenidən qoşulur (real produksiyada baş verib).

        Ünvan Faza 4-də PIN-dən sessiya ID-sinə keçdi."""
        payload, code = _reason_and_code(
            env["client"], f"/ws/live/sessions/9999/host?token={_token(env['ali']['id'])}"
        )
        assert code == 4404
        assert payload["type"] == "error"

    def test_invalid_token_is_explained(self, env):
        payload, code = _reason_and_code(
            env["client"], "/ws/live/sessions/9999/host?token=yanlis"
        )
        assert code == 4401
        assert payload["type"] == "error"
