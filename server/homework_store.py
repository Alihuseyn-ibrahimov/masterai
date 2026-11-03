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

import json
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

                -- Açıq cavablar (Faza 1, PR 2). Sualın mətni, nümunə cavabı
                -- və meyarları cavab anında SURƏT kimi saxlanılır: müəllim
                -- sonra sualı redaktə və ya silsə, yoxlanmış cavabın balı
                -- hansı meyarla verildiyini itirməməlidir.
                CREATE TABLE IF NOT EXISTS homework_open_answers (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    attempt_id       INTEGER NOT NULL,
                    assignment_id    INTEGER NOT NULL,
                    student_id       INTEGER NOT NULL,
                    open_question_id INTEGER NOT NULL,
                    question         TEXT NOT NULL,
                    model_answer     TEXT NOT NULL,
                    rubric           TEXT NOT NULL,
                    answer           TEXT NOT NULL,
                    status           TEXT NOT NULL,
                    ai_result        TEXT,
                    ai_points        INTEGER,
                    error            TEXT,
                    final_points     INTEGER,
                    teacher_comment  TEXT,
                    created_at       TEXT NOT NULL,
                    graded_at        TEXT,
                    confirmed_at     TEXT,
                    UNIQUE(attempt_id, open_question_id)
                );
                """
            )
            self._conn.commit()

    # ---- açıq cavablar (Faza 1, PR 2) ---------------------------------
    # status: grading → graded | failed → confirmed (müəllim balı təsdiqlədi)

    @staticmethod
    def _open_answer_row(row: sqlite3.Row) -> dict:
        data = dict(row)
        data["rubric"] = json.loads(data["rubric"])
        data["ai_result"] = json.loads(data["ai_result"]) if data["ai_result"] else None
        return data

    def submit_open_answer(self, attempt: dict, question: dict, answer: str) -> dict | None:
        """Yeni cavab yazır (`grading`). Bu suala artıq cavab varsa `None` (tək cəhd)."""
        with self._lock:
            try:
                cur = self._conn.execute(
                    "INSERT INTO homework_open_answers (attempt_id, assignment_id, student_id, open_question_id, "
                    "question, model_answer, rubric, answer, status, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'grading', ?)",
                    (attempt["id"], attempt["assignment_id"], attempt["student_id"], question["id"],
                     question["question"], question["model_answer"],
                     json.dumps(question["rubric"], ensure_ascii=False), answer, _utc_now_iso()),
                )
            except sqlite3.IntegrityError:
                return None
            self._conn.commit()
            return self.get_open_answer(cur.lastrowid)

    def get_open_answer(self, answer_id: int) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM homework_open_answers WHERE id = ?", (answer_id,)).fetchone()
            return self._open_answer_row(row) if row else None

    def list_open_answers_for_attempt(self, attempt_id: int) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM homework_open_answers WHERE attempt_id = ? ORDER BY id", (attempt_id,)
            )
            return [self._open_answer_row(row) for row in cur.fetchall()]

    def list_open_answers_for_assignment(self, assignment_id: int) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM homework_open_answers WHERE assignment_id = ? ORDER BY student_id, id",
                (assignment_id,),
            )
            return [self._open_answer_row(row) for row in cur.fetchall()]

    def finish_open_grading(self, answer_id: int, ai_result: dict, ai_points: int) -> None:
        with self._lock:
            # Müəllim AI-dan əvvəl özü təsdiqləyibsə onun balına toxunulmur.
            self._conn.execute(
                "UPDATE homework_open_answers SET ai_result = ?, ai_points = ?, graded_at = ?, "
                "status = CASE WHEN status = 'confirmed' THEN status ELSE 'graded' END WHERE id = ?",
                (json.dumps(ai_result, ensure_ascii=False), ai_points, _utc_now_iso(), answer_id),
            )
            self._conn.commit()

    def fail_open_grading(self, answer_id: int, error: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE homework_open_answers SET error = ?, graded_at = ?, "
                "status = CASE WHEN status = 'confirmed' THEN status ELSE 'failed' END WHERE id = ?",
                (error[:500], _utc_now_iso(), answer_id),
            )
            self._conn.commit()

    def fail_interrupted_open_grading(self, error: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE homework_open_answers SET status = 'failed', error = ?, graded_at = ? "
                "WHERE status = 'grading'",
                (error, _utc_now_iso()),
            )
            self._conn.commit()
            return cur.rowcount

    def confirm_open_answer(self, answer_id: int, points: int, comment: str) -> dict | None:
        with self._lock:
            self._conn.execute(
                "UPDATE homework_open_answers SET status = 'confirmed', final_points = ?, teacher_comment = ?, "
                "confirmed_at = ? WHERE id = ?",
                (points, comment or None, _utc_now_iso(), answer_id),
            )
            self._conn.commit()
            return self.get_open_answer(answer_id)

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

    def answer_stats_for_assignment(self, assignment_id: int) -> dict[int, tuple[int, int]]:
        """`{question_index: (düzgün, cəmi)}` — tapşırığın bütün cəhdləri üzrə."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT a.question_index AS idx, SUM(a.is_correct) AS correct, COUNT(*) AS total "
                "FROM homework_answers a JOIN homework_attempts t ON t.id = a.attempt_id "
                "WHERE t.assignment_id = ? GROUP BY a.question_index",
                (assignment_id,),
            ).fetchall()
            return {row["idx"]: (row["correct"], row["total"]) for row in rows}

    def get_chat_leaderboard(self, chat_id: int) -> dict[int, int]:
        """Çatın hər üzvünün TAMAMLANMIŞ ev tapşırıqlarının cəm xalı —
        `student_id -> total_score`. Cəhdi olmayan üzvlər burada
        YOXDUR (çağıran `chats.list_member_ids`-lə birləşdirib 0-la
        doldurmalıdır, bax `app.py`, `get_chat_leaderboard` — canlı
        sessiyanın `compute_scores`-unun eyni naxışı)."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT ha.student_id as student_id, SUM(ha.score) as total_score "
                "FROM homework_attempts ha "
                "JOIN homework_assignments a ON a.id = ha.assignment_id "
                "WHERE a.chat_id = ? AND ha.status = 'completed' "
                "GROUP BY ha.student_id",
                (chat_id,),
            )
            return {row["student_id"]: row["total_score"] for row in cur.fetchall()}

    def list_attempts_by_student(self, student_id: int) -> list[dict]:
        """Tələbənin bütün TAMAMLANMIŞ cəhdləri (bütün tapşırıqlar üzrə) —
        Fərdi tələbə tarixçəsi üçün (bax `app.py`, `/history/*`).
        `in_progress`/`pending` cəhdlər hələ "tarixçə" sayılmır."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, assignment_id, student_id, status, current_question_index, "
                "score, started_at, completed_at FROM homework_attempts "
                "WHERE student_id = ? AND status = 'completed' ORDER BY completed_at DESC",
                (student_id,),
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

    # ---- Sahib paneli: aktivlik (spec 2026-09-29 §3) ----

    def count_answers_in_chats_since(self, chat_ids: list[int], since_iso: str) -> int:
        if not chat_ids:
            return 0
        marks = ",".join("?" for _ in chat_ids)
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM homework_answers ans "
                "JOIN homework_attempts att ON att.id = ans.attempt_id "
                "JOIN homework_assignments asg ON asg.id = att.assignment_id "
                f"WHERE asg.chat_id IN ({marks}) AND ans.answered_at >= ?",
                (*chat_ids, since_iso),
            ).fetchone()[0]

    def last_answer_in_chats(self, chat_ids: list[int]) -> str | None:
        if not chat_ids:
            return None
        marks = ",".join("?" for _ in chat_ids)
        with self._lock:
            return self._conn.execute(
                "SELECT MAX(ans.answered_at) FROM homework_answers ans "
                "JOIN homework_attempts att ON att.id = ans.attempt_id "
                "JOIN homework_assignments asg ON asg.id = att.assignment_id "
                f"WHERE asg.chat_id IN ({marks})",
                tuple(chat_ids),
            ).fetchone()[0]
