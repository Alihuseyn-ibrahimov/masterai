"""Kursun istifadəçilərinə baxmaq və hesabı bağlamaq - VPS-də (2026-10-01).

Səbəb: sahib dəvət linkini özü sınadı və İngilis kursunda sınaq müəllim
hesabı qaldı. Panelde hesab bağlamaq düyməsi yoxdur. Hesab SİLİNMİR
(is_active=0): giriş bağlanır, müəllim sayından çıxır, data qalır.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy" / "course_users.py"
sys.path.insert(0, str(ROOT / "deploy"))
import course_users  # noqa: E402

from server.user_store import UserStore  # noqa: E402


@pytest.fixture
def live(tmp_path):
    (tmp_path / "data").mkdir()
    users = UserStore(str(tmp_path / "data" / "users.db"))
    owner = users.create("sahib@x.az", "h", "Sahib")
    users.set_platform_owner(owner["id"], True)
    course = users.courses.create("English", "english", trial_days=30, seat_limit=10)
    test = users.create("sinaq@x.az", "h", "Sınaq müəllim", course_id=course["id"])
    users.set_teacher(test["id"], True)
    (tmp_path / ".env").write_text("JWT_SECRET=gizli\nUSERS_DB_PATH=data/users.db\n", encoding="utf-8")
    return tmp_path, course["id"]


def _users(live) -> UserStore:
    return UserStore(str(live[0] / "data" / "users.db"))


def test_list_shows_course_users(live, capsys):
    path, course_id = live
    assert course_users.main(["--from", str(path), "list", "--course", str(course_id)]) == 0
    out = capsys.readouterr().out
    assert "sinaq@x.az" in out and "müəllim" in out and "aktiv" in out
    assert "sahib@x.az" not in out  # başqa kurs
    assert "gizli" not in out


def test_deactivate_removes_from_teacher_count(live):
    path, course_id = live
    assert course_users.main(["--from", str(path), "deactivate", "--email", "sinaq@x.az"]) == 0
    users = _users(live)
    assert users.get_by_email("sinaq@x.az")["is_active"] == 0
    assert users.count_teachers(course_id) == 0


def test_activate_restores(live):
    path, _ = live
    course_users.main(["--from", str(path), "deactivate", "--email", "sinaq@x.az"])
    assert course_users.main(["--from", str(path), "activate", "--email", "sinaq@x.az"]) == 0
    assert _users(live).get_by_email("sinaq@x.az")["is_active"] == 1


def test_refuses_platform_owner(live):
    path, _ = live
    assert course_users.main(["--from", str(path), "deactivate", "--email", "sahib@x.az"]) == 1
    assert _users(live).get_by_email("sahib@x.az")["is_active"] == 1


def test_unknown_email(live):
    path, _ = live
    assert course_users.main(["--from", str(path), "deactivate", "--email", "yox@x.az"]) == 1


def test_cli_runs_as_script(live, tmp_path):
    path, course_id = live
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--from", str(path), "list", "--course", str(course_id)],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "sinaq@x.az" in result.stdout
