"""Gündəlik backup - `data/` qovluğunun tam surəti, serverdən kənara da (2026-10-30).

Niyə: 2026-10-30-da DigitalOcean hesabı dayandırıldı, droplet silindi və
bütün bazalar onunla getdi - serverdən kənarda heç bir surət yox idi.

Nə edir:
1. `data/`-dakı HƏR `*.db` faylının ardıcıl surətini çıxarır (sqlite
   `backup` API-si - servis işləyərkən faylı kopyalamaq yarımçıq yazını
   tuta bilər) və `uploads/`-u əlavə edir, hamısı bir `.tar.gz`-də.
2. Yerli qovluqda son `--keep` arxivi saxlayır, köhnələri silir.
3. `.env`-də `BACKUP_TELEGRAM_BOT_TOKEN` + `BACKUP_TELEGRAM_CHAT_ID` varsa,
   arxivi Telegram-a göndərir - serverdən kənar nüsxə budur. Telegram
   botunun fayl limiti 50 MB-dır; ondan böyük arxiv göndərilmir və skript
   xəta kodu ilə çıxır ki, jurnalda görünsün.

    .venv/bin/python deploy/backup_data.py --data /opt/masterai/data --out /var/backups/masterai
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

TELEGRAM_LIMIT_BYTES = 49 * 1024 * 1024
PREFIX = "masterai-"


def _snapshot(source: Path, target: Path) -> None:
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def make_archive(data: Path, out: Path, now: datetime | None = None) -> Path:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    archive = out / f"{PREFIX}{stamp}.tar.gz"
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp)
        for db in sorted(data.glob("*.db")):
            _snapshot(db, staging / db.name)
        with tarfile.open(archive, "w:gz") as tar:
            for db in sorted(staging.glob("*.db")):
                tar.add(db, arcname=f"data/{db.name}")
            uploads = data / "uploads"
            if uploads.is_dir():
                tar.add(uploads, arcname="data/uploads")
    os.chmod(archive, 0o600)  # e-poçtlar və parol hash-ləri var
    return archive


def prune(out: Path, keep: int) -> list[Path]:
    archives = sorted(out.glob(f"{PREFIX}*.tar.gz"))
    removed = archives[:-keep] if keep > 0 else archives
    for path in removed:
        path.unlink()
    return removed


def send_to_telegram(archive: Path, token: str, chat_id: str, post=None) -> None:
    if archive.stat().st_size > TELEGRAM_LIMIT_BYTES:
        raise RuntimeError(
            f"Arxiv {archive.stat().st_size // (1024 * 1024)} MB-dır, Telegram limiti 50 MB - göndərilmədi"
        )
    if post is None:
        import requests
        post = requests.post
    with archive.open("rb") as fh:
        response = post(
            f"https://api.telegram.org/bot{token}/sendDocument",
            data={"chat_id": chat_id, "caption": f"MasterAI backup: {archive.name}"},
            files={"document": (archive.name, fh)},
            timeout=120,
        )
    if getattr(response, "status_code", 200) != 200:
        raise RuntimeError(f"Telegram cavabı {response.status_code}: {response.text[:200]}")


def main(argv: list[str] | None = None, env=os.environ, post=None) -> int:
    parser = argparse.ArgumentParser(description="MasterAI data backup")
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--keep", type=int, default=14)
    args = parser.parse_args(argv)

    if not args.data.is_dir():
        print(f"data qovluğu yoxdur: {args.data}", file=sys.stderr)
        return 1
    archive = make_archive(args.data, args.out)
    print(f"arxiv: {archive} ({archive.stat().st_size} bayt)")
    for path in prune(args.out, args.keep):
        print(f"silindi: {path.name}")

    token = env.get("BACKUP_TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = env.get("BACKUP_TELEGRAM_CHAT_ID", "").strip()
    if not (token and chat_id):
        print("XƏBƏRDARLIQ: Telegram açarları yoxdur - surət YALNIZ bu serverdədir")
        return 0
    try:
        send_to_telegram(archive, token, chat_id, post=post)
    except Exception as exc:  # noqa: BLE001 - jurnala düşsün, servis uğursuz görünsün
        print(f"XƏTA: Telegram-a göndərilmədi: {exc}", file=sys.stderr)
        return 2
    print("Telegram-a göndərildi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
