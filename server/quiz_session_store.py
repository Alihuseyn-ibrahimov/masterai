"""Çat quiz sessiyalarının SQLite saxlanması.

`chat_id` PRIMARY KEY — bir çatda eyni anda yalnız bir aktiv sessiya ola
bilər. `finished` sessiya üzərinə yeni tur `UPDATE` ilə əvəz olunur (bax
spec, bölmə 3 — ardıcıl turlara icazə, paralel aktivə yox).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone


class QuizAlreadyActive(Exception):
    """Bu çatda artıq aktiv quiz sessiyası var."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["question_ids"] = json.loads(data["question_ids"])
    return data


class QuizSessionStore:
    def __init__(self, path: str = "quiz_sessions.db") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chat_quiz_sessions (
                chat_id                     INTEGER PRIMARY KEY,
                material_id                  INTEGER NOT NULL,
                question_ids                  TEXT NOT NULL,
                current_index                   INTEGER NOT NULL,
                current_question_started_at       TEXT NOT NULL,
                status                              TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def create(self, chat_id: int, material_id: int, question_ids: list[int]) -> dict:
        existing = self.get(chat_id)
        if existing is not None and existing["status"] == "active":
            raise QuizAlreadyActive(chat_id)

        now = _utc_now_iso()
        if existing is None:
            self._conn.execute(
                "INSERT INTO chat_quiz_sessions "
                "(chat_id, material_id, question_ids, current_index, "
                "current_question_started_at, status) VALUES (?, ?, ?, 0, ?, 'active')",
                (chat_id, material_id, json.dumps(question_ids), now),
            )
        else:
            self._conn.execute(
                "UPDATE chat_quiz_sessions SET material_id=?, question_ids=?, "
                "current_index=0, current_question_started_at=?, status='active' "
                "WHERE chat_id=?",
                (material_id, json.dumps(question_ids), now, chat_id),
            )
        self._conn.commit()
        return self.get(chat_id)

    def get(self, chat_id: int) -> dict | None:
        cur = self._conn.execute(
            "SELECT chat_id, material_id, question_ids, current_index, "
            "current_question_started_at, status FROM chat_quiz_sessions WHERE chat_id = ?",
            (chat_id,),
        )
        row = cur.fetchone()
        return _row_to_dict(row) if row else None

    def advance(self, chat_id: int) -> dict:
        session = self.get(chat_id)
        if session is None:
            raise ValueError(f"chat_id={chat_id} üçün sessiya yoxdur")

        new_index = session["current_index"] + 1
        if new_index < len(session["question_ids"]):
            self._conn.execute(
                "UPDATE chat_quiz_sessions SET current_index=?, "
                "current_question_started_at=? WHERE chat_id=?",
                (new_index, _utc_now_iso(), chat_id),
            )
        else:
            self._conn.execute(
                "UPDATE chat_quiz_sessions SET status='finished' WHERE chat_id=?",
                (chat_id,),
            )
        self._conn.commit()
        return self.get(chat_id)
