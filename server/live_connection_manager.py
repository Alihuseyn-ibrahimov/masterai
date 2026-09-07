"""Canlı sinif sessiyası üçün WebSocket bağlantılarının proses-daxili
reyestri — mövcud `ConnectionManager`-dən (çat/istifadəçi üçün) qəsdən
ayrıdır: host (tək, JWT-li müəllim) və play (çoxlu, anonim,
`participant_id`-li tələbə) qoşulmaları fərqli formadadır.

Kilid dizaynı `connection_manager.py`-nin eynisidir: `await
ws.send_json(...)` zamanı HEÇ VAXT kilid tutulmur — broadcast yalnız
hədəf siyahısını kilid altında "şəkilini çəkir", sonra kilidsiz göndərir.
"""

from __future__ import annotations

import threading
from typing import Protocol


class _SendsJSON(Protocol):
    async def send_json(self, message: dict) -> None: ...


class LiveConnectionManager:
    def __init__(self) -> None:
        self._hosts: dict[int, set] = {}
        self._players: dict[int, dict[int, set]] = {}
        self._lock = threading.Lock()

    def connect_host(self, session_id: int, websocket: _SendsJSON) -> None:
        with self._lock:
            self._hosts.setdefault(session_id, set()).add(websocket)

    def disconnect_host(self, session_id: int, websocket: _SendsJSON) -> None:
        with self._lock:
            sockets = self._hosts.get(session_id)
            if sockets is None:
                return
            sockets.discard(websocket)
            if not sockets:
                del self._hosts[session_id]

    def connect_player(self, session_id: int, participant_id: int, websocket: _SendsJSON) -> None:
        with self._lock:
            session = self._players.setdefault(session_id, {})
            session.setdefault(participant_id, set()).add(websocket)

    def disconnect_player(self, session_id: int, participant_id: int, websocket: _SendsJSON) -> None:
        with self._lock:
            session = self._players.get(session_id)
            if session is None:
                return
            sockets = session.get(participant_id)
            if sockets is None:
                return
            sockets.discard(websocket)
            if not sockets:
                del session[participant_id]
            if not session:
                del self._players[session_id]

    async def broadcast_host(self, session_id: int, message: dict) -> None:
        with self._lock:
            targets = list(self._hosts.get(session_id, set()))
        for ws in targets:
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect_host(session_id, ws)

    async def broadcast_players(self, session_id: int, message: dict) -> None:
        with self._lock:
            session = self._players.get(session_id, {})
            targets = [(pid, ws) for pid, sockets in session.items() for ws in sockets]
        for pid, ws in targets:
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect_player(session_id, pid, ws)

    async def send_to_player(self, session_id: int, participant_id: int, message: dict) -> None:
        with self._lock:
            sockets = list(self._players.get(session_id, {}).get(participant_id, set()))
        for ws in sockets:
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect_player(session_id, participant_id, ws)

    def player_count(self, session_id: int) -> int:
        with self._lock:
            return len(self._players.get(session_id, {}))
