"""Ev təkrarı rejimi (Faza 2) — SQLite saxlanması.

`live_session_store.py`-nin qohumu, amma daha sadədir: WebSocket/timer
yoxdur (asinxron, tək-oyunçulu), ona görə "runner" ayrıca modula
çıxarılmayıb — sual axını qaydaları (`NotCurrentQuestion`/
`AlreadyAnswered`) birbaşa bu Store-un `answer()` metodunda yoxlanılır.

`threading.RLock()` bütün metodları əhatə edir (reentrant, çünki
`answer()` öz daxilində `get_attempt()`/`has_answered()`-i çağırır) —
səbəb üçün bax `user_store.py`-nin modul qeydi.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class HomeworkError(Exception):
    """Ümumi ev tapşırığı xətası."""


class NotCurrentQuestion(HomeworkError):
    """Cavab hazırkı aktiv sualdan fərqli (köhnə) sual üçündür."""


class AttemptAlreadyCompleted(HomeworkError):
    """Cəhd artıq tamamlanıb — tək-cəhd qaydasına görə yeni cavab qəbul edilmir."""


class HomeworkStore:
    def __init__(self, path: str = "homework.db") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS homework_assignments (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id          INTEGER NOT NULL,
                    question_set_id  INTEGER NOT NULL,
                    due_date         TEXT NOT NULL,
                    created_by       INTEGER NOT NULL,
                    created_at       TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS homework_attempts (
                    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                    assignment_id           INTEGER NOT NULL,
                    student_id              INTEGER NOT NULL,
                    status                  TEXT NOT NULL,
                    current_question_index  INTEGER NOT NULL,
                    score                   INTEGER NOT NULL,
                    started_at              TEXT NOT NULL,
                    completed_at            TEXT,
                    UNIQUE(assignment_id, student_id)
                );

                CREATE TABLE IF NOT EXISTS homework_answers (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    attempt_id     INTEGER NOT NULL,
                    question_index INTEGER NOT NULL,
                    chosen_index   INTEGER NOT NULL,
                    is_correct     INTEGER NOT NULL,
                    answered_at    TEXT NOT NULL,
                    UNIQUE(attempt_id, question_index)
                );
                """
            )
            self._conn.commit()

    # ---- tapşırıqlar ------------------------------------------------

    def create_assignment(
        self, chat_id: int, question_set_id: int, due_date: str, created_by: int
    ) -> dict:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO homework_assignments "
                "(chat_id, question_set_id, due_date, created_by, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (chat_id, question_set_id, due_date, created_by, _utc_now_iso()),
            )
            self._conn.commit()
            return self.get_assignment(cur.lastrowid)

    def get_assignment(self, assignment_id: int) -> dict | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, chat_id, question_set_id, due_date, created_by, created_at "
                "FROM homework_assignments WHERE id = ?",
                (assignment_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def list_assignments_for_chat(self, chat_id: int) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, chat_id, question_set_id, due_date, created_by, created_at "
                "FROM homework_assignments WHERE chat_id = ? ORDER BY created_at DESC",
                (chat_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    def list_assignments_by_teacher(self, teacher_id: int) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, chat_id, question_set_id, due_date, created_by, created_at "
                "FROM homework_assignments WHERE created_by = ? ORDER BY created_at DESC",
                (teacher_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    # ---- cəhdlər ------------------------------------------------

    def get_attempt(self, attempt_id: int) -> dict | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, assignment_id, student_id, status, current_question_index, "
                "score, started_at, completed_at FROM homework_attempts WHERE id = ?",
                (attempt_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def get_attempt_for_student(self, assignment_id: int, student_id: int) -> dict | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, assignment_id, student_id, status, current_question_index, "
                "score, started_at, completed_at FROM homework_attempts "
                "WHERE assignment_id = ? AND student_id = ?",
                (assignment_id, student_id),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def get_or_create_attempt(self, assignment_id: int, student_id: int) -> dict:
        """Fasilə/davam + tək-cəhd qaydasını dəstəkləyir: mövcud cəhd
        (`in_progress` VƏ ya `completed`) varsa ONU qaytarır, çağıran
        `status == "completed"`-ə görə qərar verir (yenidən başlamır)."""
        with self._lock:
            existing = self.get_attempt_for_student(assignment_id, student_id)
            if existing is not None:
                return existing
            cur = self._conn.execute(
                "INSERT INTO homework_attempts "
                "(assignment_id, student_id, status, current_question_index, score, "
                "started_at, completed_at) VALUES (?, ?, 'in_progress', 0, 0, ?, NULL)",
                (assignment_id, student_id, _utc_now_iso()),
            )
            self._conn.commit()
            return self.get_attempt(cur.lastrowid)

    def list_attempts_for_assignment(self, assignment_id: int) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, assignment_id, student_id, status, current_question_index, "
                "score, started_at, completed_at FROM homework_attempts "
                "WHERE assignment_id = ?",
                (assignment_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    # ---- cavablar ------------------------------------------------

    def answer(
        self, attempt_id: int, question_index: int, chosen_index: int,
        is_correct: bool, total_questions: int,
    ) -> dict:
        """Cavabı qeydə alır VƏ cəhdi növbəti suala keçirir (və ya
        sonuncudursa tamamlayır) — bir atomik əməliyyatda, `live_session_
        runner.record_answer`+`advance_question`-un birləşmiş, sadələşdirilmiş
        versiyası (timer/broadcast yoxdur).

        `live_session_runner`-dən fərqli olaraq ayrıca `AlreadyAnswered`
        yoxlaması YOXDUR: bu, TƏK-oyunçulu rejimdir (canlı sessiyada olduğu
        kimi bir sualı bir neçə fərqli iştirakçı ayrı-ayrı cavablamır) və
        `current_question_index` HƏR cavabla ATOMİK irəli sürüşdüyü üçün
        (eyni `_lock` altında) "eyni sualı iki dəfə cavablama" halı
        strukturca mümkün deyil — `question_index != current_question_index`
        yoxlaması (aşağıda) onu artıq əhatə edir."""
        with self._lock:
            attempt = self.get_attempt(attempt_id)
            if attempt is None:
                raise ValueError(f"attempt_id={attempt_id} üçün cəhd yoxdur")
            if attempt["status"] == "completed":
                raise AttemptAlreadyCompleted(attempt_id)
            if question_index != attempt["current_question_index"]:
                raise NotCurrentQuestion(question_index)

            self._conn.execute(
                "INSERT INTO homework_answers "
                "(attempt_id, question_index, chosen_index, is_correct, answered_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (attempt_id, question_index, chosen_index, int(is_correct), _utc_now_iso()),
            )

            new_score = attempt["score"] + (1 if is_correct else 0)
            new_index = attempt["current_question_index"] + 1
            finished = new_index >= total_questions
            self._conn.execute(
                "UPDATE homework_attempts SET score = ?, current_question_index = ?, "
                "status = ?, completed_at = ? WHERE id = ?",
                (
                    new_score,
                    new_index,
                    "completed" if finished else "in_progress",
                    _utc_now_iso() if finished else None,
                    attempt_id,
                ),
            )
            self._conn.commit()
            return self.get_attempt(attempt_id)
