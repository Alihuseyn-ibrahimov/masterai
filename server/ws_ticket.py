"""Qısaömürlü, birdəfəlik WebSocket «ticket»-i.

Brauzer WebSocket API-si başlıq göndərə bilmir, ona görə giriş URL-də
gedirdi: `?token=<JWT>`. JWT günlərlə keçərlidir, URL isə proksi
jurnalında, brauzer tarixçəsində və ekran görüntüsündə qala bilir
(`log_redaction` yalnız BİZİM jurnalımızı təmizləyir).

İndi brauzer əvvəl `POST /auth/ws-ticket` ilə (Bearer başlığı ilə) bir
ticket alır və URL-ə onu yazır. Ticket:
- 60 saniyə keçərlidir;
- BİR dəfə işlənir (qoşulan kimi silinir) - URL-dən oğurlanmış ticket
  artıq işə yaramır;
- yalnız bu prosesin yaddaşındadır. Server `-w 1` ilə işləyir
  (`deploy/masterai.service`): WebSocket reyestri də proses-daxilidir.
  Restartdan sonra köhnə ticket-lər itir - client yenidən alır.
"""
from __future__ import annotations

import secrets
import threading
import time
from typing import Callable

TICKET_TTL_SECONDS = 60
# Bir istifadəçi saniyədə yüzlərlə ticket istəsə yaddaş böyüməsin.
MAX_TICKETS = 10_000


class WsTicketStore:
    def __init__(
        self,
        ttl_seconds: int = TICKET_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._tickets: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def issue(self, user_id: int) -> str:
        ticket = secrets.token_urlsafe(32)
        with self._lock:
            self._prune()
            if len(self._tickets) >= MAX_TICKETS:
                # Ən köhnəsi gedir (dict daxil etmə sırasını saxlayır).
                self._tickets.pop(next(iter(self._tickets)))
            self._tickets[ticket] = (user_id, self._clock() + self._ttl)
        return ticket

    def consume(self, ticket: str) -> int | None:
        """Ticket keçərlidirsə `user_id` qaytarır və onu SİLİR."""
        if not ticket:
            return None
        with self._lock:
            entry = self._tickets.pop(ticket, None)
        if entry is None:
            return None
        user_id, expires_at = entry
        if self._clock() > expires_at:
            return None
        return user_id

    def __len__(self) -> int:
        with self._lock:
            return len(self._tickets)

    def _prune(self) -> None:
        now = self._clock()
        expired = [t for t, (_, exp) in self._tickets.items() if exp < now]
        for t in expired:
            del self._tickets[t]
