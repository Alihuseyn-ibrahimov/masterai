"""Kurs miqrasiyasının SINAĞI — produksiya bazalarının SURƏTİNDƏ (Faza 9).

NİYƏ: kurs lisenziyası miqrasiyası (users.course_id, courses cədvəli, kurs #1,
chats/question_sets.course_id, bank profili) lokal BOŞ bazalarda sınanıb.
Real data ilə ilk qarşılaşma canlı serverdə olmamalıdır.

NƏ EDİR:
  1. `.env`-dəki yollara görə (yoxdursa iş qovluğundan) üç bazanı tapır.
  2. Onları sqlite `backup` API-si ilə YALNIZ-OXUMA rejimində yeni qovluğa
     köçürür (servis işləyərkən də ardıcıl surət alınır; canlı fayla yazılmır).
  3. Miqrasiyanı surətdə İKİ dəfə işlədir (idempotentlik).
  4. Nəticəni BAZADAN oxuyur: sətir sayı dəyişmədimi, hamı kurs #1-dəmi, ...

`.env` KÖÇÜRÜLMÜR (içində açarlar var) — yalnız yollar oxunur.

İşlətmək (VPS-də, servisin iş qovluğundan):
    .venv/bin/python deploy/migration_rehearsal.py \\
        --from /opt/pr-agent/repo/masterai --to /root/migration-rehearsal-$(date +%Y%m%d-%H%M)

Çıxış kodu: 0 — hamısı təmiz, 1 — problem var (deploy ETMƏ).
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Birbaşa icrada `sys.path[0]` = deploy/ olur və `server` tapılmır — bu,
# repair_duplicate_participants.py-də serverdə real sındı.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.chat_store import ChatStore  # noqa: E402
from server.course_store import DEFAULT_COURSE_ID  # noqa: E402
from server.question_set_store import QuestionSetStore  # noqa: E402
from server.user_store import UserStore  # noqa: E402

# Kurs miqrasiyası YALNIZ bu üç bazaya toxunur.
DATABASES = {
    "USERS_DB_PATH": "users.db",
    "CHATS_DB_PATH": "chats.db",
    "QUESTION_SETS_DB_PATH": "question_sets.db",
}


@dataclass
class Report:
    lines: list[str] = field(default_factory=list)
    ok: bool = True

    def check(self, passed: bool, text: str) -> None:
        self.lines.append(f"{'OK  ' if passed else 'XƏTA'} {text}")
        if not passed:
            self.ok = False

    def note(self, text: str) -> None:
        self.lines.append(f"     {text}")


def _read_env_paths(live: Path) -> dict[str, str]:
    """Yalnız `*_DB_PATH` dəyərləri — digər sətirlər (açarlar) oxunmur."""
    env = live / ".env"
    paths: dict[str, str] = {}
    if not env.exists():
        return paths
    for line in env.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() in DATABASES:
            paths[key.strip()] = value.strip().strip('"').strip("'")
    return paths


def resolve_db_paths(live: Path) -> dict[str, Path]:
    env_paths = _read_env_paths(live)
    sources: dict[str, Path] = {}
    for key, filename in DATABASES.items():
        raw = env_paths.get(key)
        path = Path(raw) if raw else live / filename
        if not path.is_absolute():
            path = live / path  # servis WorkingDirectory-dən nisbi yol kimi açır
        sources[filename] = path
    return sources


def _snapshot(source: Path, target: Path) -> None:
    """Canlı baza `mode=ro` ilə açılır — bu bağlantı ilə ona YAZMAQ mümkün deyil."""
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def _count(path: Path, table: str) -> int:
    conn = sqlite3.connect(path)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.OperationalError:
        return 0  # cədvəl hələ yaranmayıb (məs. heç bank yoxdur)
    finally:
        conn.close()


def _scalar(path: Path, sql: str, params: tuple = ()) -> object:
    conn = sqlite3.connect(path)
    try:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row else None  # sətir yoxdur = yoxlama XƏTA verməlidir, sınmamalı
    finally:
        conn.close()


def _migrate(copies: dict[str, Path]) -> None:
    UserStore(str(copies["users.db"]))
    ChatStore(str(copies["chats.db"]))
    QuestionSetStore(str(copies["question_sets.db"]))


def rehearse(live: Path, target: Path) -> Report:
    live = live.resolve()
    target = target.resolve()
    if target.exists():
        raise SystemExit(f"Hədəf qovluq artıq var: {target} - köhnə sınağın üstünə yazılmır")
    if live == target or live in target.parents:
        raise SystemExit("Hədəf canlı qovluğun İÇİNDƏ ola bilməz")

    report = Report()
    sources = resolve_db_paths(live)
    if not sources["users.db"].exists():
        raise SystemExit(f"users.db tapılmadı: {sources['users.db']}")

    target.mkdir(parents=True)
    copies: dict[str, Path] = {}
    for filename, source in sources.items():
        copy = target / filename
        if source.exists():
            _snapshot(source, copy)
            report.note(f"surət: {source} -> {copy}")
        else:
            report.note(f"{filename} canlıda yoxdur ({source}) - boş yaradılacaq")
        copies[filename] = copy

    before = {
        "users": _count(copies["users.db"], "users"),
        "chats": _count(copies["chats.db"], "chats"),
        "question_sets": _count(copies["question_sets.db"], "question_sets"),
    }

    _migrate(copies)
    _migrate(copies)  # ikinci dəfə: idempotent olmalıdır

    users, chats, banks = copies["users.db"], copies["chats.db"], copies["question_sets.db"]
    after = {
        "users": _count(users, "users"),
        "chats": _count(chats, "chats"),
        "question_sets": _count(banks, "question_sets"),
    }
    for table in before:
        report.check(before[table] == after[table], f"{table}: {before[table]} -> {after[table]}")

    report.check(
        _scalar(users, "SELECT COUNT(*) FROM users WHERE course_id IS NULL OR course_id != ?",
                (DEFAULT_COURSE_ID,)) == 0,
        f"bütün istifadəçilər kurs #{DEFAULT_COURSE_ID}-dədir",
    )
    report.check(_scalar(users, "SELECT COUNT(*) FROM users WHERE is_active != 1") == 0,
                 "bütün istifadəçilər aktivdir (heç kim bağlanmayıb)")
    report.check(_scalar(users, "SELECT COUNT(*) FROM courses") == 1,
                 "iki dəfə işlədikdən sonra da tək kurs var")
    report.check(
        _scalar(users, "SELECT status FROM courses WHERE id = ?", (DEFAULT_COURSE_ID,)) == "owner",
        f"kurs #{DEFAULT_COURSE_ID} müddətsizdir (owner) - mövcud istifadəçilər bağlanmır",
    )
    report.check(
        bool(_scalar(users, "SELECT join_code FROM courses WHERE id = ?", (DEFAULT_COURSE_ID,))),
        f"kurs #{DEFAULT_COURSE_ID}-in qeydiyyat kodu var",
    )
    for table in ("teacher_invites", "owner_audit_log"):
        report.check(
            _scalar(users, "SELECT COUNT(*) FROM sqlite_master WHERE name = ?", (table,)) == 1,
            f"{table} cədvəli yaradılıb",
        )
    report.check(
        _scalar(chats, "SELECT COUNT(*) FROM chats WHERE course_id IS NULL OR course_id != ?",
                (DEFAULT_COURSE_ID,)) == 0,
        f"bütün çatlar kurs #{DEFAULT_COURSE_ID}-dədir",
    )
    report.check(
        _scalar(banks, "SELECT COUNT(*) FROM question_sets WHERE course_id IS NULL OR course_id != ? "
                "OR profile != 'exam_prep' OR bank_kind != 'practice'", (DEFAULT_COURSE_ID,)) == 0,
        "bütün banklar kurs #1-də, imtahan profilində, adi növdə",
    )
    owners = _scalar(users, "SELECT COUNT(*) FROM users WHERE is_platform_owner = 1")
    report.note(f"platforma sahibi sayı: {owners} (deploy-dan sonra VPS-də əl ilə təyin olunur)")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Kurs miqrasiyasının surətdə sınağı")
    parser.add_argument("--from", dest="live", required=True, help="servisin iş qovluğu")
    parser.add_argument("--to", dest="target", required=True, help="YENİ qovluq (mövcud olmamalıdır)")
    args = parser.parse_args(argv)
    report = rehearse(Path(args.live), Path(args.target))
    print("\n".join(report.lines))
    print("\nHAMISI TƏMİZ - deploy edilə bilər" if report.ok else "\nPROBLEM VAR - deploy ETMƏ")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
