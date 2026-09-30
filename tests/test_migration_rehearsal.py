"""Miqrasiya sınağı — produksiya bazalarının SURƏTİNDƏ (spec 2026-09-29, Faza 9).

Lokal bazalar boşdur, yəni kurs miqrasiyası real data ilə heç vaxt
sınanmayıb. Skript canlı bazaları yeni qovluğa köçürür, miqrasiyanı YALNIZ
surətdə işlədir və nəticəni bazadan oxuyur. Canlı fayllara toxunmamalıdır.

Skript birbaşa icra ilə də sınanır (subprocess): `repair_duplicate_participants.py`
yalnız import edilərək sınandığı üçün serverdə `No module named 'server'` ilə
sınmışdı (bax masterai/CLAUDE.md).
"""

from __future__ import annotations

import hashlib
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy" / "migration_rehearsal.py"

sys.path.insert(0, str(ROOT / "deploy"))
import migration_rehearsal  # noqa: E402


def _legacy_live_dir(base: Path) -> Path:
    """Kurslardan ƏVVƏLKİ sxemli «canlı» qovluq: bir baza data/-da, digərləri kökdə
    (canlı serverdəki qarışıq vəziyyət kimi, bax deploy/UPDATE.md)."""
    live = base / "live"
    (live / "data").mkdir(parents=True)
    users = sqlite3.connect(live / "data" / "users.db")
    users.executescript(
        """
        CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL, phone TEXT UNIQUE, display_name TEXT NOT NULL,
            created_at TEXT NOT NULL, is_teacher INTEGER NOT NULL DEFAULT 0,
            is_admin INTEGER NOT NULL DEFAULT 0);
        INSERT INTO users (email, password_hash, display_name, created_at, is_teacher, is_admin)
        VALUES ('amil@x.az','h','Amil','2026-09-01',1,1), ('s1@x.az','h','S1','2026-09-02',0,0),
               ('s2@x.az','h','S2','2026-09-03',0,0);
        """
    )
    users.commit()
    users.close()
    chats = sqlite3.connect(live / "chats.db")
    chats.executescript(
        """
        CREATE TABLE chats (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, name TEXT,
            created_by INTEGER NOT NULL, created_at TEXT NOT NULL, invite_code TEXT);
        CREATE TABLE chat_members (chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            joined_at TEXT NOT NULL, PRIMARY KEY (chat_id, user_id));
        INSERT INTO chats (kind, name, created_by, created_at, invite_code)
        VALUES ('group','11-A',1,'2026-09-01','ABC234'), ('group','11-B',1,'2026-09-02','DEF567');
        """
    )
    chats.commit()
    chats.close()
    banks = sqlite3.connect(live / "question_sets.db")
    banks.executescript(
        """
        CREATE TABLE question_sets (id INTEGER PRIMARY KEY AUTOINCREMENT, subject TEXT NOT NULL,
            title TEXT NOT NULL, status TEXT NOT NULL, material_kind TEXT NOT NULL,
            material_location TEXT NOT NULL, error TEXT, created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL);
        CREATE TABLE live_questions (id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_set_id INTEGER NOT NULL, question TEXT NOT NULL, options TEXT NOT NULL,
            correct_index INTEGER NOT NULL, explanation TEXT NOT NULL, created_at TEXT NOT NULL);
        INSERT INTO question_sets (subject, title, status, material_kind, material_location,
            created_by, created_at) VALUES ('mentiq','Bank','ready','link','https://x',1,'2026-09-01');
        """
    )
    banks.commit()
    banks.close()
    (live / ".env").write_text(
        "JWT_SECRET=gizli-deyer-kopyalanmamali\n"
        f"USERS_DB_PATH={live / 'data' / 'users.db'}\n",
        encoding="utf-8",
    )
    return live


def _digest(folder: Path) -> dict[str, str]:
    return {
        str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(folder.rglob("*.db"))
    }


def test_rehearsal_passes_and_live_files_untouched(tmp_path):
    live = _legacy_live_dir(tmp_path)
    before = _digest(live)
    target = tmp_path / "rehearsal"

    report = migration_rehearsal.rehearse(live, target)

    assert report.ok, report.lines
    assert _digest(live) == before  # canlı fayllar BAYT-BAYT eynidir
    text = "\n".join(report.lines)
    assert "users: 3 -> 3" in text
    assert "chats: 2 -> 2" in text
    assert "question_sets: 1 -> 1" in text


def test_env_secrets_are_not_copied(tmp_path):
    live = _legacy_live_dir(tmp_path)
    target = tmp_path / "rehearsal"
    migration_rehearsal.rehearse(live, target)
    for path in target.rglob("*"):
        if path.is_file():
            assert b"gizli-deyer" not in path.read_bytes(), path


def test_env_db_path_is_respected(tmp_path):
    """users.db `.env`-də data/-dadır — kökdəki köhnə boş fayl YOX, o sınanmalıdır."""
    live = _legacy_live_dir(tmp_path)
    decoy = sqlite3.connect(live / "users.db")
    decoy.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT)")
    decoy.commit()
    decoy.close()
    report = migration_rehearsal.rehearse(live, tmp_path / "rehearsal")
    assert report.ok, report.lines
    assert "users: 3 -> 3" in "\n".join(report.lines)


def test_refuses_existing_target(tmp_path):
    live = _legacy_live_dir(tmp_path)
    target = tmp_path / "rehearsal"
    target.mkdir()
    with pytest.raises(SystemExit):
        migration_rehearsal.rehearse(live, target)


def test_refuses_target_inside_live(tmp_path):
    live = _legacy_live_dir(tmp_path)
    with pytest.raises(SystemExit):
        migration_rehearsal.rehearse(live, live / "sinaq")


def test_detects_broken_migration(tmp_path, monkeypatch):
    """Yoxlama həqiqətən yoxlayır: istifadəçi kurs #1-ə düşməsə XƏTA."""
    live = _legacy_live_dir(tmp_path)
    monkeypatch.setattr(migration_rehearsal, "DEFAULT_COURSE_ID", 99)
    report = migration_rehearsal.rehearse(live, tmp_path / "rehearsal")
    assert not report.ok


def test_cli_runs_as_script(tmp_path):
    live = _legacy_live_dir(tmp_path)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--from", str(live), "--to", str(tmp_path / "r")],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "HAMISI TƏMİZ" in result.stdout
