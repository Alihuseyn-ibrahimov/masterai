"""Platforma sahibini təyin etmək — VPS-də əl ilə, bir dəfə (Faza 9).

Bayraq API ilə DƏYİŞDİRİLMİR (bax `get_platform_owner`), yalnız serverdə bu
skriptlə. Heredoc Python əvəzinə testli skript: produksiya bazasında səhv
istifadəçiyə sahib hüququ vermək bərpası çətin səhvdir.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy" / "set_platform_owner.py"

sys.path.insert(0, str(ROOT / "deploy"))
import set_platform_owner  # noqa: E402

from server.user_store import UserStore  # noqa: E402


@pytest.fixture
def live(tmp_path):
    (tmp_path / "data").mkdir()
    users = UserStore(str(tmp_path / "data" / "users.db"))
    users.create("Amil@X.az", "h", "Amil")
    other = users.courses.create("Kurs", "english", trial_days=30, seat_limit=5)
    users.create("kenar@x.az", "h", "Kənar", course_id=other["id"])
    (tmp_path / ".env").write_text("JWT_SECRET=gizli\nUSERS_DB_PATH=data/users.db\n", encoding="utf-8")
    return tmp_path


def _flag(live: Path, email: str) -> int:
    return UserStore(str(live / "data" / "users.db")).get_by_email(email)["is_platform_owner"]


def test_sets_flag_by_email_case_insensitive(live):
    assert set_platform_owner.main(["--from", str(live), "--email", "amil@x.az"]) == 0
    assert _flag(live, "amil@x.az") == 1


def test_idempotent(live):
    set_platform_owner.main(["--from", str(live), "--email", "amil@x.az"])
    assert set_platform_owner.main(["--from", str(live), "--email", "amil@x.az"]) == 0
    assert _flag(live, "amil@x.az") == 1


def test_unknown_email_changes_nothing(live):
    assert set_platform_owner.main(["--from", str(live), "--email", "yoxdur@x.az"]) == 1
    assert _flag(live, "amil@x.az") == 0


def test_refuses_user_outside_owner_course(live):
    """Sahib kurs #1-dədir: ödənişli kursun hesabı sahib olsa, o kursun
    müəllim/tələbə siyahısında görünər və lisenziya qapısından azad olar."""
    assert set_platform_owner.main(["--from", str(live), "--email", "kenar@x.az"]) == 1
    assert _flag(live, "kenar@x.az") == 0


def test_remove(live):
    set_platform_owner.main(["--from", str(live), "--email", "amil@x.az"])
    assert set_platform_owner.main(["--from", str(live), "--email", "amil@x.az", "--remove"]) == 0
    assert _flag(live, "amil@x.az") == 0


def test_cli_runs_as_script(live, tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--from", str(live), "--email", "amil@x.az"],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert _flag(live, "amil@x.az") == 1
    assert "gizli" not in result.stdout + result.stderr
