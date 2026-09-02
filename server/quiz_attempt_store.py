"""İstifadəçi cavablarının SQLite saxlanması — minimal CRUD.

`is_correct` bura hazır (çağıran tərəfindən hesablanmış) ötürülür — bu
Store, digərləri kimi (`UserStore` şifrəni özü hash-ləmədiyi kimi),
qiymətləndirmə məntiqini özü etmir.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["is_correct"] = bool(data["is_correct"])
    return data


class QuizAttemptStore:
    def __init__(self, path: str = "quiz_attempts.db") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS quiz_attempts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id  INTEGER NOT NULL,
                user_id      INTEGER NOT NULL,
                chosen_index INTEGER NOT NULL,
                is_correct   INTEGER NOT NULL,
                answered_at  TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def create(self, question_id: int, user_id: int, chosen_index: int, is_correct: bool) -> dict:
        cur = self._conn.execute(
            "INSERT INTO quiz_attempts "
            "(question_id, user_id, chosen_index, is_correct, answered_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (question_id, user_id, chosen_index, int(is_correct), _utc_now_iso()),
        )
        self._conn.commit()
        return self.get(cur.lastrowid)

    def get(self, attempt_id: int) -> dict | None:
        cur = self._conn.execute(
            "SELECT id, question_id, user_id, chosen_index, is_correct, answered_at "
            "FROM quiz_attempts WHERE id = ?",
            (attempt_id,),
        )
        row = cur.fetchone()
        return _row_to_dict(row) if row else None

    def list_by_question(self, question_id: int) -> list[dict]:
        cur = self._conn.execute(
            "SELECT id, question_id, user_id, chosen_index, is_correct, answered_at "
            "FROM quiz_attempts WHERE question_id = ? ORDER BY answered_at",
            (question_id,),
        )
        return [_row_to_dict(row) for row in cur.fetchall()]

    def list_by_user(self, user_id: int) -> list[dict]:
        cur = self._conn.execute(
            "SELECT id, question_id, user_id, chosen_index, is_correct, answered_at "
            "FROM quiz_attempts WHERE user_id = ? ORDER BY answered_at",
            (user_id,),
        )
        return [_row_to_dict(row) for row in cur.fetchall()]
