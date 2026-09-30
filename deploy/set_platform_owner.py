"""Platforma sahibini təyin etmək / geri almaq — VPS-də, bir dəfə (Faza 9).

Sahib bayrağı API ilə DƏYİŞDİRİLMİR (bax `server/app.py: get_platform_owner`).
Baza yolu servisin `.env`-indən oxunur (`migration_rehearsal.resolve_db_paths`
ilə eyni qayda); `.env`-dəki digər dəyərlər oxunmur və çap olunmur.

    .venv/bin/python deploy/set_platform_owner.py --from /opt/pr-agent/repo/masterai --email SƏNİN@EPOÇTUN
    .venv/bin/python deploy/set_platform_owner.py --from ... --email ... --remove

Dəyişiklik növbəti GİRİŞDƏN sonra görünür: sahib bir dəfə çıxıb yenidən
daxil olmalıdır (profil səhifəsindəki panel linki `/auth/login` cavabından gəlir).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from migration_rehearsal import resolve_db_paths  # noqa: E402
from server.course_store import DEFAULT_COURSE_ID  # noqa: E402
from server.user_store import UserStore  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Platforma sahibi bayrağı")
    parser.add_argument("--from", dest="live", required=True, help="servisin iş qovluğu")
    parser.add_argument("--email", required=True)
    parser.add_argument("--remove", action="store_true", help="bayrağı geri al")
    args = parser.parse_args(argv)

    path = resolve_db_paths(Path(args.live).resolve())["users.db"]
    if not path.exists():
        print(f"users.db tapılmadı: {path}")
        return 1
    users = UserStore(str(path))
    user = users.get_by_email(args.email)
    if user is None:
        print(f"Bu e-poçtla istifadəçi yoxdur: {args.email} - heç nə dəyişmədi")
        return 1
    if not args.remove and user["course_id"] != DEFAULT_COURSE_ID:
        print(f"{user['email']} kurs #{user['course_id']}-dədir, sahib isə kurs "
              f"#{DEFAULT_COURSE_ID}-də olmalıdır - heç nə dəyişmədi")
        return 1
    users.set_platform_owner(user["id"], not args.remove)
    after = users.get_by_id(user["id"])["is_platform_owner"]
    print(f"baza: {path}")
    print(f"#{user['id']} {user['email']}: is_platform_owner = {after}")
    return 0 if after == (0 if args.remove else 1) else 1


if __name__ == "__main__":
    raise SystemExit(main())
