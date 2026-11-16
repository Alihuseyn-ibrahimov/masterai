"""`deploy/kassa_demo.py`: pilot görüşü üçün sintetik Kassa kursu (addım 8)."""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy"))

import kassa_demo  # noqa: E402
from server import kassa as kassa_calc  # noqa: E402
from server.app import _kassa_enrollments  # noqa: E402
from server.chat_store import ChatStore  # noqa: E402
from server.course_store import DEFAULT_COURSE_ID  # noqa: E402
from server.payment_store import PaymentStore  # noqa: E402
from server.user_store import UserStore  # noqa: E402

NOW = datetime(2026, 11, 16, 9, 0, tzinfo=timezone.utc)
MONTH = "2026-11"


def _fast_hash(password: str) -> str:
    return "demo$" + password


def _summary(data_dir: Path) -> dict:
    paths = kassa_demo.db_paths(data_dir)
    chats = ChatStore(str(paths["CHATS_DB_PATH"]))
    users = UserStore(str(paths["USERS_DB_PATH"]))
    payments = PaymentStore(str(paths["PAYMENTS_DB_PATH"]))
    enrollments = _kassa_enrollments(DEFAULT_COURSE_ID, chats, users, payments)
    chat_ids = sorted({e.chat_id for e in enrollments})
    records = payments.list_records_for_chats(chat_ids, kassa_calc.months_back(MONTH, 12)[0], MONTH)
    expenses = payments.list_expenses(DEFAULT_COURSE_ID, kassa_calc.months_back(MONTH, 6)[0], MONTH)
    return kassa_calc.summarize(MONTH, NOW, enrollments, records, expenses)


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("demo")
    result = kassa_demo.build(data_dir, MONTH, now=NOW, hasher=_fast_hash)
    return result, _summary(data_dir)


def test_story_is_visible_in_kassa(demo):
    result, summary = demo
    assert result.students == sum(size for _, _, size in kassa_demo.GROUPS)
    assert len(summary["by_chat"]) == len(kassa_demo.GROUPS)
    assert summary["students_without_fee"] == 0
    # Cari ay yarımçıqdır: hamı ödəməyib, amma çoxu ödəyib.
    assert 0.6 <= summary["collection_rate"] < 0.95
    left = sorted(d["display_name"] for d in summary["debtors"] if d["likely_left"])
    assert left == sorted(result.stopped)
    assert len(summary["trend"]) == 6 and all(t["collected"] > 0 for t in summary["trend"])
    assert all(t["expenses"] > 0 for t in summary["trend"])


def test_no_payment_in_the_future(demo):
    result, _ = demo
    payments = PaymentStore(str(kassa_demo.db_paths(result.data_dir)["PAYMENTS_DB_PATH"]))
    with payments._lock:
        latest = payments._conn.execute("SELECT MAX(paid_at) FROM payment_records").fetchone()[0]
    assert datetime.fromisoformat(latest) <= NOW


def test_owner_can_log_in_as_course_admin(demo):
    result, _ = demo
    users = UserStore(str(kassa_demo.db_paths(result.data_dir)["USERS_DB_PATH"]))
    owner = users.get_by_email(result.email)
    assert owner["is_admin"] and owner["is_teacher"]
    assert owner["password_hash"] == _fast_hash(result.password)


def test_same_seed_same_course(tmp_path):
    a = kassa_demo.build(tmp_path / "a", MONTH, now=NOW, hasher=_fast_hash, password="x")
    b = kassa_demo.build(tmp_path / "b", MONTH, now=NOW, hasher=_fast_hash, password="x")
    assert a.stopped == b.stopped
    assert _summary(a.data_dir)["trend"] == _summary(b.data_dir)["trend"]


def test_refuses_directory_with_databases(tmp_path):
    (tmp_path / "users.db").write_bytes(b"")
    with pytest.raises(FileExistsError):
        kassa_demo.build(tmp_path, MONTH, now=NOW, hasher=_fast_hash)


def test_env_points_every_server_database_into_demo_dir(demo):
    result, _ = demo
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    needed = set(re.findall(r"^([A-Z_]+_DB_PATH)=", example, flags=re.M))
    env = dict(line.split("=", 1) for line in (result.data_dir / "demo.env").read_text().splitlines())
    assert needed <= set(env)
    assert all(Path(v).parent == result.data_dir for v in env.values())
