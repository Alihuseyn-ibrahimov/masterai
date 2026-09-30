"""Canlı sinif sessiyası üçün fənn-etiketli sual bankları — SQLite saxlanması.

Mövcud `materials`/`questions` cədvəllərinə TOXUNULMUR (bax
`docs/superpowers/specs/2026-09-07-masterai-live-classroom-design.md`) —
`question_sets` çatdan asılı deyil, öz `live_questions` cədvəlinə
malikdir. Eyni ədədin `materials`/`questions`-dakı fərqli bir sətrə
təsadüfən istinad etməsinin qarşısını almaq üçün bu, QƏSDƏN tamam ayrı
cədvəllərdir (autoincrement ID-lər cədvəllər arasında paylaşılmır).

`threading.RLock()` bütün metodları əhatə edir (reentrant, çünki
`create()` öz daxilində `get()`-i çağırır) — səbəb üçün bax
`user_store.py`-nin modul qeydi (real WebSocket testində tapılan sqlite
çoxlu-thread korlanması).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone

from pipeline.models import MCQQuestion
from server.course_store import DEFAULT_COURSE_ID

SUBJECTS = (
    "mentiq",
    "informatika",
    "dunyagorusu",
    "azerbaycan_dili",
    "qanunvericilik",
    "xarici_dil",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _question_row_to_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["options"] = json.loads(data["options"])
    return data


class QuestionSetStore:
    def __init__(self, path: str = "question_sets.db") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS question_sets (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject           TEXT NOT NULL,
                    title             TEXT NOT NULL,
                    status            TEXT NOT NULL,
                    material_kind     TEXT NOT NULL,
                    material_location TEXT NOT NULL,
                    error             TEXT,
                    created_by        INTEGER NOT NULL,
                    created_at        TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS live_questions (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_set_id INTEGER NOT NULL,
                    question        TEXT NOT NULL,
                    options         TEXT NOT NULL,
                    correct_index   INTEGER NOT NULL,
                    explanation     TEXT NOT NULL,
                    created_at      TEXT NOT NULL
                );
                """
            )
            # Kurs sərhədi (spec 2026-09-29 §4): köhnə banklar kurs #1-dədir.
            try:
                self._conn.execute("ALTER TABLE question_sets ADD COLUMN course_id INTEGER")
            except sqlite3.OperationalError:
                pass
            self._conn.execute(
                "UPDATE question_sets SET course_id = ? WHERE course_id IS NULL",
                (DEFAULT_COURSE_ID,),
            )
            # Kurs profili (spec 2026-09-29 §5). Profil bankda SAXLANILIR:
            # kursun profili sonra dəyişsə, köhnə bankın hansı promptla
            # yaradıldığı bilinməlidir. Köhnə banklar imtahan profilindədir.
            for ddl in (
                "ALTER TABLE question_sets ADD COLUMN profile TEXT NOT NULL DEFAULT 'exam_prep'",
                "ALTER TABLE question_sets ADD COLUMN bank_kind TEXT NOT NULL DEFAULT 'practice'",
                "ALTER TABLE question_sets ADD COLUMN passage TEXT",
            ):
                try:
                    self._conn.execute(ddl)
                except sqlite3.OperationalError:
                    pass
            self._conn.commit()

    def create(
        self,
        subject: str,
        title: str,
        material_kind: str,
        material_location: str,
        created_by: int,
        course_id: int = DEFAULT_COURSE_ID,
        profile: str = "exam_prep",
        bank_kind: str = "practice",
    ) -> dict:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO question_sets "
                "(subject, title, status, material_kind, material_location, error, created_by, "
                "created_at, course_id, profile, bank_kind) "
                "VALUES (?, ?, 'processing', ?, ?, NULL, ?, ?, ?, ?, ?)",
                (subject, title, material_kind, material_location, created_by, _utc_now_iso(),
                 course_id, profile, bank_kind),
            )
            self._conn.commit()
            return self.get(cur.lastrowid)

    def get(self, question_set_id: int) -> dict | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, subject, title, status, material_kind, material_location, "
                "error, created_by, created_at, course_id, profile, bank_kind FROM question_sets WHERE id = ?",
                (question_set_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def list_all(self) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, subject, title, status, material_kind, material_location, "
                "error, created_by, created_at, course_id, profile, bank_kind FROM question_sets ORDER BY created_at DESC"
            )
            return [dict(row) for row in cur.fetchall()]

    def mark_ready(self, question_set_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE question_sets SET status = 'ready' WHERE id = ?", (question_set_id,)
            )
            self._conn.commit()

    def mark_failed(self, question_set_id: int, error: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE question_sets SET status = 'failed', error = ? WHERE id = ?",
                (error, question_set_id),
            )
            self._conn.commit()

    def add_question(self, question_set_id: int, mcq: MCQQuestion) -> dict:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO live_questions "
                "(question_set_id, question, options, correct_index, explanation, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    question_set_id,
                    mcq.question,
                    json.dumps(mcq.options, ensure_ascii=False),
                    mcq.correct_index,
                    mcq.explanation,
                    _utc_now_iso(),
                ),
            )
            self._conn.commit()
            return self.get_question(cur.lastrowid)

    def get_question(self, question_id: int) -> dict | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, question_set_id, question, options, correct_index, explanation, created_at "
                "FROM live_questions WHERE id = ?",
                (question_id,),
            )
            row = cur.fetchone()
            return _question_row_to_dict(row) if row else None

    def update_question(
        self,
        question_id: int,
        question: str,
        options: list[str],
        correct_index: int,
        explanation: str,
    ) -> dict | None:
        """Müəllimin sual redaktəsi (bax Sual redaktə/təsdiq ekranı, Faza 5)
        — sual sayı/sırası dəyişmir, yalnız məzmun yenilənir."""
        with self._lock:
            self._conn.execute(
                "UPDATE live_questions SET question = ?, options = ?, correct_index = ?, "
                "explanation = ? WHERE id = ?",
                (question, json.dumps(options, ensure_ascii=False), correct_index, explanation, question_id),
            )
            self._conn.commit()
            return self.get_question(question_id)

    def delete_question(self, question_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM live_questions WHERE id = ?", (question_id,))
            self._conn.commit()

    def list_questions(self, question_set_id: int) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, question_set_id, question, options, correct_index, explanation, created_at "
                "FROM live_questions WHERE question_set_id = ? ORDER BY id",
                (question_set_id,),
            )
            return [_question_row_to_dict(row) for row in cur.fetchall()]

    def set_passage(self, question_set_id: int, passage: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE question_sets SET passage = ? WHERE id = ?", (passage, question_set_id)
            )
            self._conn.commit()

    def get_passage(self, question_set_id: int) -> str | None:
        """Reading mətni ayrıca oxunur — siyahı sorğularına (hər bank ~3000
        simvol) qatılmır."""
        with self._lock:
            row = self._conn.execute(
                "SELECT passage FROM question_sets WHERE id = ?", (question_set_id,)
            ).fetchone()
            return row[0] if row else None

    def count_by_creator_since(self, user_id: int, since_iso: str) -> int:
        """Gündəlik yükləmə limiti üçün (bax `MaterialStore.count_by_uploader_since`)."""
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM question_sets WHERE created_by = ? AND created_at >= ?",
                (user_id, since_iso),
            ).fetchone()[0]

    def count_by_course_since(self, course_id: int, since_iso: str) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM question_sets WHERE course_id = ? AND created_at >= ?",
                (course_id, since_iso),
            ).fetchone()[0]

    def last_created_in_course(self, course_id: int) -> str | None:
        with self._lock:
            return self._conn.execute(
                "SELECT MAX(created_at) FROM question_sets WHERE course_id = ?", (course_id,)
            ).fetchone()[0]

    def count_questions(self, question_set_id: int) -> int:
        with self._lock:
            cur = self._conn.execute(
                "SELECT COUNT(*) FROM live_questions WHERE question_set_id = ?",
                (question_set_id,),
            )
            return cur.fetchone()[0]
