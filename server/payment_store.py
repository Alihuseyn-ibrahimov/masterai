"""Ödəniş izləməsi (Faza 3 PR 3, 2026-11-03) — əl ilə qeyd, onlayn kartla
ödəniş bu fazada YOX (bax plan sənədi, "Qərar tələb edən suallar" §2).

Hər (çat, tələbə) cütü üçün aylıq məbləğ (`payment_fees`) və hər ay üçün
"ödədi" qeydi (`payment_records`) AYRI cədvəldədir — məbləğ sonra
dəyişsə, keçmiş aylarda nə qədər ödənildiyi təhrif olunmasın.

`threading.Lock()` bütün metodları əhatə edir — səbəb üçün bax
`user_store.py`-nin modul qeydi.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_month() -> str:
    """«2026-11» - server UTC-də."""
    return datetime.now(timezone.utc).strftime("%Y-%m")


class PaymentStore:
    def __init__(self, path: str = "payments.db") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS payment_fees (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id        INTEGER NOT NULL,
                    student_id     INTEGER NOT NULL,
                    monthly_amount INTEGER NOT NULL,
                    updated_at     TEXT NOT NULL,
                    UNIQUE(chat_id, student_id)
                );

                CREATE TABLE IF NOT EXISTS payment_records (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id    INTEGER NOT NULL,
                    student_id INTEGER NOT NULL,
                    month      TEXT NOT NULL,
                    amount     INTEGER NOT NULL,
                    marked_by  INTEGER NOT NULL,
                    paid_at    TEXT NOT NULL,
                    UNIQUE(chat_id, student_id, month)
                );
                """
            )
            self._conn.commit()

    # ---- aylıq məbləğ ----

    def set_fee(self, chat_id: int, student_id: int, monthly_amount: int) -> dict:
        with self._lock:
            now = _utc_now_iso()
            self._conn.execute(
                "INSERT INTO payment_fees (chat_id, student_id, monthly_amount, updated_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(chat_id, student_id) DO UPDATE SET monthly_amount = ?, updated_at = ?",
                (chat_id, student_id, monthly_amount, now, monthly_amount, now),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT chat_id, student_id, monthly_amount, updated_at FROM payment_fees "
                "WHERE chat_id = ? AND student_id = ?",
                (chat_id, student_id),
            ).fetchone()
            return dict(row)

    def list_fees_for_chat(self, chat_id: int) -> dict[int, int]:
        """`{student_id: monthly_amount}`."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT student_id, monthly_amount FROM payment_fees WHERE chat_id = ?",
                (chat_id,),
            )
            return {row["student_id"]: row["monthly_amount"] for row in cur.fetchall()}

    # ---- ödəniş qeydi ----

    def mark_paid(self, chat_id: int, student_id: int, month: str, amount: int, marked_by: int) -> dict:
        with self._lock:
            now = _utc_now_iso()
            self._conn.execute(
                "INSERT INTO payment_records (chat_id, student_id, month, amount, marked_by, paid_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(chat_id, student_id, month) DO UPDATE SET amount = ?, marked_by = ?, paid_at = ?",
                (chat_id, student_id, month, amount, marked_by, now, amount, marked_by, now),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT chat_id, student_id, month, amount, marked_by, paid_at FROM payment_records "
                "WHERE chat_id = ? AND student_id = ? AND month = ?",
                (chat_id, student_id, month),
            ).fetchone()
            return dict(row)

    def unmark_paid(self, chat_id: int, student_id: int, month: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM payment_records WHERE chat_id = ? AND student_id = ? AND month = ?",
                (chat_id, student_id, month),
            )
            self._conn.commit()

    def list_payments_for_chat(self, chat_id: int, month: str) -> dict[int, dict]:
        """`{student_id: record}` — verilən ay üçün."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT chat_id, student_id, month, amount, marked_by, paid_at FROM payment_records "
                "WHERE chat_id = ? AND month = ?",
                (chat_id, month),
            )
            return {row["student_id"]: dict(row) for row in cur.fetchall()}
