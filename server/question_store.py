"""AI-nin yaratdığı sualların SQLite saxlanması.

`pipeline.models.MCQQuestion`-u DB-yə yazır/oxuyur (`options` JSON mətn
kimi saxlanır). Bu, `pipeline/` (Faza 1 spec) ilə `server/` (bu spec)
arasındakı körpüdür.

`threading.RLock()` bütün metodları əhatə edir (reentrant, çünki
`create_from_mcq()` öz daxilində `get()`-i çağırır) — səbəb üçün bax
`user_store.py`-nin modul qeydi (real WebSocket testində tapılan sqlite
çoxlu-thread korlanması).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone

from pipeline.models import MCQQuestion


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["options"] = json.loads(data["options"])
    return data


class QuestionStore:
    def __init__(self, path: str = "questions.db") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS questions (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    material_id   INTEGER NOT NULL,
                    question      TEXT NOT NULL,
                    options       TEXT NOT NULL,
                    correct_index INTEGER NOT NULL,
                    explanation   TEXT NOT NULL,
                    created_at    TEXT NOT NULL
                );
                """
            )
            self._conn.commit()

    def create_from_mcq(self, material_id: int, mcq: MCQQuestion) -> dict:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO questions "
                "(material_id, question, options, correct_index, explanation, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    material_id,
                    mcq.question,
                    json.dumps(mcq.options, ensure_ascii=False),
                    mcq.correct_index,
                    mcq.explanation,
                    _utc_now_iso(),
                ),
            )
            self._conn.commit()
            return self.get(cur.lastrowid)

    def get(self, question_id: int) -> dict | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, material_id, question, options, correct_index, explanation, created_at "
                "FROM questions WHERE id = ?",
                (question_id,),
            )
            row = cur.fetchone()
            return _row_to_dict(row) if row else None

    def list_by_material(self, material_id: int) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, material_id, question, options, correct_index, explanation, created_at "
                "FROM questions WHERE material_id = ? ORDER BY created_at",
                (material_id,),
            )
            return [_row_to_dict(row) for row in cur.fetchall()]

    def count_all(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
