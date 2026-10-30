"""Gündəlik backup skripti (2026-10-30: droplet silindi, data getdi)."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy"))
import backup_data  # noqa: E402


@pytest.fixture
def data(tmp_path):
    folder = tmp_path / "data"
    (folder / "uploads").mkdir(parents=True)
    (folder / "uploads" / "a.pdf").write_bytes(b"%PDF")
    for name in ("users.db", "summaries.db"):
        conn = sqlite3.connect(folder / name)
        conn.execute("CREATE TABLE t (v TEXT)")
        conn.execute("INSERT INTO t VALUES ('salam')")
        conn.commit()
        conn.close()
    return folder


def test_archive_holds_every_db_and_uploads(data, tmp_path):
    archive = backup_data.make_archive(data, tmp_path / "out")
    with tarfile.open(archive) as tar:
        names = set(tar.getnames())
        tar.extractall(tmp_path / "restore", filter="data")
    assert {"data/users.db", "data/summaries.db", "data/uploads/a.pdf"} <= names
    restored = sqlite3.connect(tmp_path / "restore" / "data" / "users.db")
    assert restored.execute("SELECT v FROM t").fetchone() == ("salam",)


def test_archive_is_private(data, tmp_path):
    archive = backup_data.make_archive(data, tmp_path / "out")
    assert archive.stat().st_mode & 0o077 == 0


def test_prune_keeps_newest(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    for day in range(1, 6):
        (out / f"masterai-2026110{day}-000000.tar.gz").write_bytes(b"x")
    removed = backup_data.prune(out, keep=2)
    assert len(removed) == 3
    assert sorted(p.name for p in out.iterdir()) == [
        "masterai-20261104-000000.tar.gz", "masterai-20261105-000000.tar.gz"]


class _Resp:
    def __init__(self, code=200):
        self.status_code = code
        self.text = "ok"


def test_sends_to_telegram_when_configured(data, tmp_path):
    calls = []

    def post(url, data=None, files=None, timeout=None):
        calls.append((url, data["chat_id"], files["document"][0]))
        return _Resp()

    env = {"BACKUP_TELEGRAM_BOT_TOKEN": "TOK", "BACKUP_TELEGRAM_CHAT_ID": "42"}
    code = backup_data.main(["--data", str(data), "--out", str(tmp_path / "out")], env=env, post=post)
    assert code == 0
    assert calls[0][0] == "https://api.telegram.org/botTOK/sendDocument"
    assert calls[0][1] == "42"
    assert calls[0][2].startswith("masterai-")


def test_telegram_failure_is_nonzero(data, tmp_path):
    env = {"BACKUP_TELEGRAM_BOT_TOKEN": "TOK", "BACKUP_TELEGRAM_CHAT_ID": "42"}
    code = backup_data.main(["--data", str(data), "--out", str(tmp_path / "out")],
                            env=env, post=lambda *a, **k: _Resp(401))
    assert code == 2


def test_too_big_archive_is_not_sent(data, tmp_path, monkeypatch):
    monkeypatch.setattr(backup_data, "TELEGRAM_LIMIT_BYTES", 1)
    sent = []
    env = {"BACKUP_TELEGRAM_BOT_TOKEN": "TOK", "BACKUP_TELEGRAM_CHAT_ID": "42"}
    code = backup_data.main(["--data", str(data), "--out", str(tmp_path / "out")],
                            env=env, post=lambda *a, **k: sent.append(1))
    assert code == 2 and not sent


def test_without_telegram_only_local_copy(data, tmp_path, capsys):
    code = backup_data.main(["--data", str(data), "--out", str(tmp_path / "out")], env={})
    assert code == 0
    assert "YALNIZ bu serverdədir" in capsys.readouterr().out


def test_missing_data_dir(tmp_path):
    assert backup_data.main(["--data", str(tmp_path / "yox"), "--out", str(tmp_path / "o")], env={}) == 1


def test_runs_as_script(data, tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "deploy" / "backup_data.py"),
         "--data", str(data), "--out", str(tmp_path / "out")],
        capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, result.stderr
    assert list((tmp_path / "out").glob("masterai-*.tar.gz"))
