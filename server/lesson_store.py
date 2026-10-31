"""Dərslər və davamiyyət (MasterAI Classroom, gün 1, 2026-10-31).

Dərs bir qrup çatına (sinfə) bağlıdır: müəllim mövzu, vaxt və növ
(onlayn / sinifdə) təyin edir, dərs `scheduled` → `live` → `ended`
yolunu keçir. Davamiyyət (dərs, istifadəçi) cütü üçün BİR sətirdir —
təkrar qoşulma yeni sətir yazmır (bax CLAUDE.md «Dərs: təkrarlanan
iştirakçı», eyni tələ).

`threading.Lock()` kifayətdir (nested public-metod çağırışı yoxdur) —
bax `user_store.py`-nin modul qeydi.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone

LESSON_MODES = ("online", "offline")
LESSON_STATUSES = ("scheduled", "live", "ended")

_COLUMNS = (
    "id, chat_id, course_id, created_by, title, description, starts_at, "
    "duration_min, mode, status, notes, started_at, ended_at, created_at, updated_at, question_set_id"
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LessonStore:
    def __init__(self, path: str = "lessons.db") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS lessons (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id      INTEGER NOT NULL,
                    course_id    INTEGER,
                    created_by   INTEGER NOT NULL,
                    title        TEXT NOT NULL,
                    description  TEXT NOT NULL DEFAULT '',
                    starts_at    TEXT NOT NULL,
                    duration_min INTEGER NOT NULL,
                    mode         TEXT NOT NULL,
                    status       TEXT NOT NULL DEFAULT 'scheduled',
                    notes        TEXT NOT NULL DEFAULT '',
                    started_at   TEXT,
                    ended_at     TEXT,
                    created_at   TEXT NOT NULL,
                    updated_at   TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_lessons_chat ON lessons(chat_id, starts_at);
                CREATE TABLE IF NOT EXISTS lesson_transcripts (
                    lesson_id  INTEGER NOT NULL,
                    seq        INTEGER NOT NULL,
                    status     TEXT NOT NULL,
                    text       TEXT NOT NULL DEFAULT '',
                    error      TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (lesson_id, seq)
                );
                CREATE TABLE IF NOT EXISTS lesson_attendance (
                    lesson_id INTEGER NOT NULL,
                    user_id   INTEGER NOT NULL,
                    method    TEXT NOT NULL,
                    joined_at TEXT NOT NULL,
                    PRIMARY KEY (lesson_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS lesson_notes (
                    lesson_id  INTEGER NOT NULL,
                    user_id    INTEGER NOT NULL,
                    text       TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (lesson_id, user_id)
                );
                """
            )
            # Gün 4: dərs mətnindən yaradılan sual bankı (+ xülasə). Gün 1-3
            # bazalarında sütun yoxdur - eyni `ALTER TABLE` naxışı.
            try:
                self._conn.execute("ALTER TABLE lessons ADD COLUMN question_set_id INTEGER")
            except sqlite3.OperationalError:
                pass
            self._conn.commit()

    def _get(self, lesson_id: int) -> dict | None:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM lessons WHERE id = ?", (lesson_id,)
        ).fetchone()
        return dict(row) if row else None

    def create(
        self,
        chat_id: int,
        *,
        course_id: int | None,
        created_by: int,
        title: str,
        description: str,
        starts_at: str,
        duration_min: int,
        mode: str,
    ) -> dict:
        if mode not in LESSON_MODES:
            raise ValueError(mode)
        now = _utc_now_iso()
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO lessons (chat_id, course_id, created_by, title, description, "
                "starts_at, duration_min, mode, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (chat_id, course_id, created_by, title, description, starts_at,
                 duration_min, mode, now, now),
            )
            self._conn.commit()
            return self._get(cur.lastrowid)

    def get(self, lesson_id: int) -> dict | None:
        with self._lock:
            return self._get(lesson_id)

    def list_for_chats(self, chat_ids: list[int]) -> list[dict]:
        """Ən yaxın dərs əvvəldə: başlama vaxtına görə artan sıra."""
        if not chat_ids:
            return []
        marks = ",".join("?" * len(chat_ids))
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {_COLUMNS} FROM lessons WHERE chat_id IN ({marks}) "
                "ORDER BY starts_at, id",
                tuple(chat_ids),
            ).fetchall()
        return [dict(r) for r in rows]

    def update(self, lesson_id: int, **fields) -> dict | None:
        """Yalnız verilən sahələr dəyişir (None = toxunma)."""
        allowed = {"title", "description", "starts_at", "duration_min", "mode", "notes"}
        changes = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if "mode" in changes and changes["mode"] not in LESSON_MODES:
            raise ValueError(changes["mode"])
        with self._lock:
            if changes:
                assignments = ", ".join(f"{column} = ?" for column in changes)
                self._conn.execute(
                    f"UPDATE lessons SET {assignments}, updated_at = ? WHERE id = ?",
                    (*changes.values(), _utc_now_iso(), lesson_id),
                )
                self._conn.commit()
            return self._get(lesson_id)

    def set_status(self, lesson_id: int, status: str) -> dict | None:
        """`live` ilk başlama, `ended` bitmə anını yazır. Yenidən başladılan
        dərsin `started_at`-i dəyişmir: davamiyyət onun ilk anına baxır."""
        if status not in LESSON_STATUSES:
            raise ValueError(status)
        now = _utc_now_iso()
        with self._lock:
            self._conn.execute(
                "UPDATE lessons SET status = ?, "
                "started_at = CASE WHEN ? = 'live' THEN COALESCE(started_at, ?) ELSE started_at END, "
                "ended_at = CASE WHEN ? = 'ended' THEN ? ELSE NULL END, "
                "updated_at = ? WHERE id = ?",
                (status, status, now, status, now, now, lesson_id),
            )
            self._conn.commit()
            return self._get(lesson_id)

    def set_question_set(self, lesson_id: int, question_set_id: int) -> dict | None:
        with self._lock:
            self._conn.execute(
                "UPDATE lessons SET question_set_id = ?, updated_at = ? WHERE id = ?",
                (question_set_id, _utc_now_iso(), lesson_id),
            )
            self._conn.commit()
            return self._get(lesson_id)

    def delete(self, lesson_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM lesson_attendance WHERE lesson_id = ?", (lesson_id,))
            self._conn.execute("DELETE FROM lesson_transcripts WHERE lesson_id = ?", (lesson_id,))
            self._conn.execute("DELETE FROM lesson_notes WHERE lesson_id = ?", (lesson_id,))
            self._conn.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
            self._conn.commit()

    def mark_attendance(self, lesson_id: int, user_id: int, method: str) -> dict:
        """Tap-və-ya-yarat: ilk qoşulma vaxtı və üsulu saxlanır."""
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO lesson_attendance (lesson_id, user_id, method, joined_at) "
                "VALUES (?, ?, ?, ?)",
                (lesson_id, user_id, method, _utc_now_iso()),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT lesson_id, user_id, method, joined_at FROM lesson_attendance "
                "WHERE lesson_id = ? AND user_id = ?",
                (lesson_id, user_id),
            ).fetchone()
        return dict(row)

    def unmark_attendance(self, lesson_id: int, user_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM lesson_attendance WHERE lesson_id = ? AND user_id = ?", (lesson_id, user_id),
            )
            self._conn.commit()

    def list_attendance(self, lesson_id: int) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT lesson_id, user_id, method, joined_at FROM lesson_attendance "
                "WHERE lesson_id = ? ORDER BY joined_at",
                (lesson_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ---- Şəxsi qeydlər (gün 5) ----
    # Hər tələbənin hər dərs üçün BİR qeydi var, yalnız özü görür.
    # Boş mətn sətri silir: «qeyd yoxdur» ilə «boş qeyd» eyni şeydir.

    def get_note(self, lesson_id: int, user_id: int) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT text, updated_at FROM lesson_notes WHERE lesson_id = ? AND user_id = ?",
                (lesson_id, user_id),
            ).fetchone()
        return dict(row) if row else None

    def set_note(self, lesson_id: int, user_id: int, text: str) -> dict | None:
        now = _utc_now_iso()
        with self._lock:
            if text.strip():
                self._conn.execute(
                    "INSERT INTO lesson_notes (lesson_id, user_id, text, updated_at) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(lesson_id, user_id) DO UPDATE SET text = excluded.text, "
                    "updated_at = excluded.updated_at",
                    (lesson_id, user_id, text, now),
                )
            else:
                self._conn.execute(
                    "DELETE FROM lesson_notes WHERE lesson_id = ? AND user_id = ?", (lesson_id, user_id),
                )
            self._conn.commit()
        return {"text": text, "updated_at": now} if text.strip() else None

    # ---- Transkript (gün 3) ----
    # Hər səs hissəsi `seq` nömrəsi ilə bir sətirdir. Eyni hissənin
    # təkrar göndərilməsi (şəbəkə kəsilib brauzer yenidən yollayır)
    # yeni sətir yaratmır, köhnəsinin yerinə yazılır.

    def start_segment(self, lesson_id: int, seq: int) -> None:
        now = _utc_now_iso()
        with self._lock:
            self._conn.execute(
                "INSERT INTO lesson_transcripts (lesson_id, seq, status, text, error, created_at, updated_at) "
                "VALUES (?, ?, 'processing', '', NULL, ?, ?) "
                "ON CONFLICT(lesson_id, seq) DO UPDATE SET status = 'processing', text = '', "
                "error = NULL, updated_at = excluded.updated_at",
                (lesson_id, seq, now, now),
            )
            self._conn.commit()

    def finish_segment(self, lesson_id: int, seq: int, *, text: str | None = None,
                       error: str | None = None) -> None:
        status = "failed" if error else "ready"
        with self._lock:
            self._conn.execute(
                "UPDATE lesson_transcripts SET status = ?, text = ?, error = ?, updated_at = ? "
                "WHERE lesson_id = ? AND seq = ?",
                (status, text or "", error, _utc_now_iso(), lesson_id, seq),
            )
            self._conn.commit()

    def list_segments(self, lesson_id: int) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq, status, text, error FROM lesson_transcripts "
                "WHERE lesson_id = ? ORDER BY seq",
                (lesson_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def transcript_text(self, lesson_id: int) -> str:
        """Hazır hissələr sıra ilə, boş sətirlə ayrılmış."""
        return "\n\n".join(
            s["text"] for s in self.list_segments(lesson_id) if s["status"] == "ready" and s["text"]
        )

    def fail_interrupted_segments(self) -> int:
        """Servis restart olanda yarımçıq qalan emallar (eyni dərs:
        fon task-ı prosesdə ölür, status əbədi `processing` qalırdı)."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE lesson_transcripts SET status = 'failed', "
                "error = 'Server yenidən başladı, hissəni yenidən göndərin' "
                "WHERE status = 'processing'"
            )
            self._conn.commit()
            return cur.rowcount
