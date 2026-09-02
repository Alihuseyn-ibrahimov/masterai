"""WebSocket bağlantılarının proses-daxili reyestri.

Yaddaş-daxili — Redis/xarici state yoxdur, tək server prosesi fərz
edilir (bax spec, bölmə 2 — "Proses-daxili məhdudiyyət"). `WebSocket`
tipini ötürən obyekt yalnız `async send_json(dict)` metoduna malik
olmalıdır — testlərdə real Starlette `WebSocket` əvəzinə yüngül fake
işlədilir.

`threading.Lock()` `_connections` dict-inin oxu/yazısını qoruyur (real
WebSocket testində Starlette `TestClient`-in hər bağlantını ayrı OS
thread-ində işlətdiyi aşkarlandı — sinxronlaşdırılmamış dict mutasiyası
qeydiyyat itkisinə səbəb olurdu). **Kilid `await ws.send_json(...)`
zamanı HEÇ VAXT tutulmur** — broadcast yalnız hədəf siyahısını kilid
altında "şəkilini çəkir", sonra kilidsiz göndərir (əks halda fərqli
thread-in event loop-undan asılı await zamanı kilidi saxlamaq deadlock
yaradır, bax `quiz_runner.py`-nin modul qeydi).
"""

from __future__ import annotations

import threading
from typing import Protocol


class _SendsJSON(Protocol):
    async def send_json(self, message: dict) -> None: ...


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[int, dict[int, set]] = {}
        self._lock = threading.Lock()

    def connect(self, chat_id: int, user_id: int, websocket: _SendsJSON) -> None:
        with self._lock:
            chat = self._connections.setdefault(chat_id, {})
            chat.setdefault(user_id, set()).add(websocket)

    def disconnect(self, chat_id: int, user_id: int, websocket: _SendsJSON) -> None:
        with self._lock:
            chat = self._connections.get(chat_id)
            if chat is None:
                return
            sockets = chat.get(user_id)
            if sockets is None:
                return
            sockets.discard(websocket)
            if not sockets:
                del chat[user_id]
            if not chat:
                del self._connections[chat_id]

    async def broadcast(self, chat_id: int, message: dict) -> None:
        with self._lock:
            chat = self._connections.get(chat_id, {})
            targets = [(user_id, ws) for user_id, sockets in chat.items() for ws in sockets]
        # Kilid burada buraxılır — `send_json` await-ləri kilidsiz aparılır.
        for user_id, ws in targets:
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(chat_id, user_id, ws)

    def connection_count(self, chat_id: int) -> int:
        with self._lock:
            chat = self._connections.get(chat_id, {})
            return sum(len(sockets) for sockets in chat.values())
