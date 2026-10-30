"""İlk admin skripti — təmiz serverdə tətbiq daxilindən admin yaradıla bilmir."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy" / "bootstrap_admin.py"

sys.path.insert(0, str(ROOT / "deploy"))
import bootstrap_admin  # noqa: E402

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


def _flags(live: Path, email: str) -> tuple[int, int, int]:
    u = UserStore(str(live / "data" / "users.db")).get_by_email(email)
    return u["is_teacher"], u["is_admin"], u["is_platform_owner"]


def test_sets_all_three_flags(live):
    assert bootstrap_admin.main(["--from", str(live), "--email", "amil@x.az"]) == 0
    assert _flags(live, "amil@x.az") == (1, 1, 1)


def test_idempotent(live):
    bootstrap_admin.main(["--from", str(live), "--email", "amil@x.az"])
    assert bootstrap_admin.main(["--from", str(live), "--email", "amil@x.az"]) == 0


def test_unknown_email_changes_nothing(live):
    assert bootstrap_admin.main(["--from", str(live), "--email", "yoxdur@x.az"]) == 1
    assert _flags(live, "amil@x.az") == (0, 0, 0)


def test_refuses_user_outside_default_course(live):
    assert bootstrap_admin.main(["--from", str(live), "--email", "kenar@x.az"]) == 1
    assert _flags(live, "kenar@x.az") == (0, 0, 0)


def test_missing_database(tmp_path):
    assert bootstrap_admin.main(["--from", str(tmp_path), "--email", "a@x.az"]) == 1


def test_runs_as_script(live):
    """Birbaşa icrada `sys.path[0]` `deploy/` olur - import yolu sınanır."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--from", str(live), "--email", "amil@x.az"],
        capture_output=True, text=True, cwd=live,
    )
    assert result.returncode == 0, result.stderr
    assert _flags(live, "amil@x.az") == (1, 1, 1)
