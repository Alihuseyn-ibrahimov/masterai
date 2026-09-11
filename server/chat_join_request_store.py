"""Çata qoşulma istəklərinin SQLite saxlanması.

NİYƏ AYRICA STORE: qoşulma artıq bir addım deyil. Əvvəl
`POST /chats/{id}/join` heç nə soruşmadan üzv əlavə edirdi və çat
ID-ləri `AUTOINCREMENT` (ARDICIL) olduğu üçün 1-dən saymaqla bütün
qrup çatlarına girmək olurdu. İndi tələbə dəvət kodu ilə İSTƏK
göndərir, çatı yaradan təsdiqləyir.

`PRIMARY KEY (chat_id, user_id)` QƏSDƏNDİR: rədd edilən tələbə yenidən
istək göndərəndə köhnə sətir yenilənir. Yəni rədd BLOKLAMA deyil —
müəllim səhvən rədd etsə, tələbə həmişəlik kənarda qalmır.

Üzvlüyü bu store ƏLAVƏ ETMİR — o, `ChatStore.add_member`-in işidir.
İkisini birləşdirmək store-u çat sxeminə bağlayardı; çağıran
(`server/app.py`) təsdiq qayıdan kimi üzvü əlavə edir.

`threading.Lock()` bütün metodları əhatə edir — səbəb üçün bax
`user_store.py` modul qeydi (real WebSocket testində tapılan sqlite
çoxlu-thread korlanması). Nested public metod çağırışı yoxdur, ona görə
`RLock` deyil, sadə `Lock` kifayətdir.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone

# Statuslar Azərbaycancadır və BİRBAŞA istifadəçiyə göstərilir — tərcümə
# qatı yoxdur (`HomeworkReportRow`-dakı eyni naxış).
STATUS_PENDING = "gözləyir"
STATUS_APPROVED = "təsdiqləndi"
STATUS_DECLINED = "rədd edildi"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatJoinRequestStore:
    def __init__(self, path: str = "chats.db") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS chat_join_requests (
                    chat_id    INTEGER NOT NULL,
                    user_id    INTEGER NOT NULL,
                    status     TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    decided_at TEXT,
                    decided_by INTEGER,
                    PRIMARY KEY (chat_id, user_id)
                );
                """
            )
            self._conn.commit()

    def request(self, chat_id: int, user_id: int) -> dict:
        """İstək göndərir və NƏTİCƏ SƏTRİNİ qaytarır.

        Təkrar çağırış təhlükəsizdir — tələbə düyməyə iki dəfə basa
        bilər, köhnə tabdan geri qayıda bilər:

        - sətir yoxdursa yaranır (`gözləyir`);
        - `rədd edildi` isə YENİDƏN AÇILIR və qərar sahələri təmizlənir;
        - `gözləyir` və ya `təsdiqləndi` isə TOXUNULMUR — təsdiqlənmiş
          üzvün statusunu geri qaytarmaq onu müəllimin gözləyənlər
          siyahısına qaytarardı.
        """
        with self._lock:
            existing = self._get_locked(chat_id, user_id)
            if existing is None:
                self._conn.execute(
                    "INSERT INTO chat_join_requests "
                    "(chat_id, user_id, status, created_at) VALUES (?, ?, ?, ?)",
                    (chat_id, user_id, STATUS_PENDING, _utc_now_iso()),
                )
                self._conn.commit()
            elif existing["status"] == STATUS_DECLINED:
                self._conn.execute(
                    "UPDATE chat_join_requests SET status = ?, created_at = ?, "
                    "decided_at = NULL, decided_by = NULL "
                    "WHERE chat_id = ? AND user_id = ?",
                    (STATUS_PENDING, _utc_now_iso(), chat_id, user_id),
                )
                self._conn.commit()
            return self._get_locked(chat_id, user_id)

    def get(self, chat_id: int, user_id: int) -> dict | None:
        with self._lock:
            return self._get_locked(chat_id, user_id)

    def _get_locked(self, chat_id: int, user_id: int) -> dict | None:
        cur = self._conn.execute(
            "SELECT chat_id, user_id, status, created_at, decided_at, decided_by "
            "FROM chat_join_requests WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def list_pending(self, chat_id: int) -> list[dict]:
        """Yalnız gözləyənlər, ən köhnə əvvəl.

        `user_id` sıralamaya ikinci açar kimi girir: eyni saniyədə gələn
        iki istəyin sırası əks halda təsadüfi olardı.
        """
        with self._lock:
            cur = self._conn.execute(
                "SELECT chat_id, user_id, status, created_at, decided_at, decided_by "
                "FROM chat_join_requests WHERE chat_id = ? AND status = ? "
                "ORDER BY created_at, user_id",
                (chat_id, STATUS_PENDING),
            )
            return [dict(row) for row in cur.fetchall()]

    def approve(self, chat_id: int, user_ids: list[int], decided_by: int) -> list[int]:
        """Toplu təsdiq. REAL dəyişilən `user_id`-ləri qaytarır.

        Çağıran qaytarılan siyahıya görə çata üzv əlavə edir, ona görə
        cavab «kim indi təsdiqləndi» olmalıdır, «kim soruşuldu» yox.

        YALNIZ `gözləyir` statuslu sətirlərə toxunur: uydurma və ya
        köhnə siyahıdan gələn `user_id` heç nə dəyişməməlidir, rədd
        edilmiş adam isə «Hamısını təsdiqlə» ilə geri qayıtmamalıdır.
        """
        approved: list[int] = []
        with self._lock:
            for user_id in user_ids:
                cur = self._conn.execute(
                    "UPDATE chat_join_requests SET status = ?, decided_at = ?, "
                    "decided_by = ? WHERE chat_id = ? AND user_id = ? AND status = ?",
                    (
                        STATUS_APPROVED,
                        _utc_now_iso(),
                        decided_by,
                        chat_id,
                        user_id,
                        STATUS_PENDING,
                    ),
                )
                if cur.rowcount:
                    approved.append(user_id)
            self._conn.commit()
        return approved

    def decline(self, chat_id: int, user_id: int, decided_by: int) -> bool:
        """Rədd. Dəyişiklik olubsa `True`.

        Təsdiqlənmiş sətrə toxunmur — çatdan ÇIXARMA ayrıca
        əməliyyatdır, rədd onun yerinə keçməməlidir.
        """
        with self._lock:
            cur = self._conn.execute(
                "UPDATE chat_join_requests SET status = ?, decided_at = ?, "
                "decided_by = ? WHERE chat_id = ? AND user_id = ? AND status = ?",
                (
                    STATUS_DECLINED,
                    _utc_now_iso(),
                    decided_by,
                    chat_id,
                    user_id,
                    STATUS_PENDING,
                ),
            )
            self._conn.commit()
            return cur.rowcount > 0
