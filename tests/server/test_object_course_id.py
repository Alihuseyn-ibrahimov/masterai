"""Çat və sual bankı kursa bağlıdır (`course_id`).

Store-lar ayrı SQLite fayllarındadır — fayllar arası JOIN yoxdur. Kurs
sərhədi yoxlaması (spec §4) obyektin özündə `course_id` olmasına
söykənir. Köhnə sətirlər kurs #1-ə backfill olunur.

Canlı sessiyada ayrıca sütun YOXDUR: sessiya çata bağlıdır, kurs çatdan
alınır (köhnə PIN sessiyaları çatsızdır → kurs #1).
"""

import sqlite3

from server.chat_store import ChatStore
from server.course_store import DEFAULT_COURSE_ID
from server.question_set_store import QuestionSetStore


def test_legacy_chats_backfilled_to_default_course(tmp_path):
    path = str(tmp_path / "chats.db")
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, name TEXT,
            created_by INTEGER NOT NULL, created_at TEXT NOT NULL
        );
        INSERT INTO chats (kind, name, created_by, created_at)
        VALUES ('group', 'Köhnə sinif', 1, '2026-09-01T00:00:00+00:00');
        """
    )
    conn.commit()
    conn.close()

    chat = ChatStore(path).get(1)
    assert chat["course_id"] == DEFAULT_COURSE_ID


def test_chat_created_in_given_course(tmp_path):
    store = ChatStore(str(tmp_path / "chats.db"))
    chat = store.create(kind="group", created_by=1, name="Sinif", course_id=7)
    assert chat["course_id"] == 7
    assert store.get(chat["id"])["course_id"] == 7
    assert store.get_by_invite_code(chat["invite_code"])["course_id"] == 7


def test_chat_default_course_when_not_given(tmp_path):
    store = ChatStore(str(tmp_path / "chats.db"))
    chat = store.create(kind="direct", created_by=1)
    assert chat["course_id"] == DEFAULT_COURSE_ID


def test_legacy_question_sets_backfilled(tmp_path):
    path = str(tmp_path / "question_sets.db")
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE question_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT, subject TEXT NOT NULL, title TEXT NOT NULL,
            status TEXT NOT NULL, material_kind TEXT NOT NULL, material_location TEXT NOT NULL,
            error TEXT, created_by INTEGER NOT NULL, created_at TEXT NOT NULL
        );
        INSERT INTO question_sets
            (subject, title, status, material_kind, material_location, created_by, created_at)
        VALUES ('Hüquq', 'Konstitusiya', 'ready', 'link', 'https://x', 1, '2026-09-01T00:00:00+00:00');
        """
    )
    conn.commit()
    conn.close()

    store = QuestionSetStore(path)
    assert store.get(1)["course_id"] == DEFAULT_COURSE_ID
    assert store.list_all()[0]["course_id"] == DEFAULT_COURSE_ID


def test_question_set_created_in_given_course(tmp_path):
    store = QuestionSetStore(str(tmp_path / "question_sets.db"))
    qs = store.create("English", "Unit 1", "link", "https://x", created_by=1, course_id=4)
    assert qs["course_id"] == 4
