"""Kursun istifadəçiləri: siyahı və hesabı bağlamaq/açmaq - VPS-də.

Hesab SİLİNMİR: `is_active=0` girişi bağlayır, tələbə yerini boşaldır,
müəllim sayından çıxarır; çatlar, cavablar, banklar qalır. Geri açmaq olur.

    .venv/bin/python deploy/course_users.py --from $PWD list --course 2
    .venv/bin/python deploy/course_users.py --from $PWD deactivate --email X
    .venv/bin/python deploy/course_users.py --from $PWD activate --email X
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from migration_rehearsal import resolve_db_paths  # noqa: E402
from server.user_store import UserStore  # noqa: E402


def _list(users: UserStore, course_id: int) -> int:
    course = users.courses.get(course_id)
    if course is None:
        print(f"Kurs #{course_id} yoxdur")
        return 1
    print(f"Kurs #{course_id}: {course['name']}")
    with users._lock:  # noqa: SLF001 - yalnız oxuma, eyni bağlantı
        rows = users._conn.execute(
            "SELECT id, email, display_name, is_teacher, is_active, created_at FROM users "
            "WHERE course_id = ? ORDER BY is_teacher DESC, id", (course_id,)
        ).fetchall()
    for row in rows:
        user_id, email, name, is_teacher, is_active, created_at = tuple(row)
        print(f"  #{user_id} {email} | {name} | {'müəllim' if is_teacher else 'tələbə'} | "
              f"{'aktiv' if is_active else 'BAĞLI'} | {created_at[:16]}")
    print(f"cəmi: {len(rows)}")
    return 0


def _set_active(users: UserStore, email: str, active: bool) -> int:
    user = users.get_by_email(email)
    if user is None:
        print(f"Bu e-poçtla istifadəçi yoxdur: {email} - heç nə dəyişmədi")
        return 1
    if not active and user["is_platform_owner"]:
        print("Platforma sahibinin hesabı bu skriptlə bağlanmır - heç nə dəyişmədi")
        return 1
    users.set_active(user["id"], active)
    after = users.get_by_id(user["id"])
    print(f"#{after['id']} {after['email']} (kurs #{after['course_id']}): "
          f"{'aktiv' if after['is_active'] else 'BAĞLI'}")
    return 0 if bool(after["is_active"]) == active else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Kursun istifadəçiləri")
    parser.add_argument("--from", dest="live", required=True, help="servisin iş qovluğu")
    sub = parser.add_subparsers(dest="action", required=True)
    lst = sub.add_parser("list")
    lst.add_argument("--course", type=int, required=True)
    for name in ("deactivate", "activate"):
        sub.add_parser(name).add_argument("--email", required=True)
    args = parser.parse_args(argv)

    path = resolve_db_paths(Path(args.live).resolve())["users.db"]
    if not path.exists():
        print(f"users.db tapılmadı: {path}")
        return 1
    users = UserStore(str(path))
    if args.action == "list":
        return _list(users, args.course)
    return _set_active(users, args.email, args.action == "activate")


if __name__ == "__main__":
    raise SystemExit(main())
