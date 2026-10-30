"""İlk admini təyin etmək — təmiz serverdə, qeydiyyatdan DƏRHAL sonra.

Təzə bazada heç kim müəllim/admin deyil və tətbiq daxilindən ilk admin
yaradıla bilmir (bax `UserStore.set_admin`). Bu skript bir hesaba
müəllim + admin + platforma sahibi bayraqlarının üçünü birdən verir.

    .venv/bin/python deploy/bootstrap_admin.py --from /opt/masterai --email SƏNİN@EPOÇTUN

Bayraqlar növbəti GİRİŞDƏN sonra görünür: çıxıb yenidən daxil ol.
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
    parser = argparse.ArgumentParser(description="İlk admin (müəllim + admin + sahib)")
    parser.add_argument("--from", dest="live", required=True, help="servisin iş qovluğu")
    parser.add_argument("--email", required=True)
    args = parser.parse_args(argv)

    path = resolve_db_paths(Path(args.live).resolve())["users.db"]
    if not path.exists():
        print(f"users.db tapılmadı: {path} - əvvəlcə saytda qeydiyyatdan keç")
        return 1
    users = UserStore(str(path))
    user = users.get_by_email(args.email)
    if user is None:
        print(f"Bu e-poçtla istifadəçi yoxdur: {args.email} - əvvəlcə saytda qeydiyyatdan keç")
        return 1
    if user["course_id"] != DEFAULT_COURSE_ID:
        print(f"{user['email']} kurs #{user['course_id']}-dədir, ilk admin kurs "
              f"#{DEFAULT_COURSE_ID}-də olmalıdır - heç nə dəyişmədi")
        return 1
    users.set_teacher(user["id"], True)
    users.set_admin(user["id"], True)
    users.set_platform_owner(user["id"], True)
    after = users.get_by_id(user["id"])
    print(f"baza: {path}")
    print(f"#{user['id']} {user['email']}: müəllim={after['is_teacher']} "
          f"admin={after['is_admin']} sahib={after['is_platform_owner']}")
    return 0 if (after["is_teacher"], after["is_admin"], after["is_platform_owner"]) == (1, 1, 1) else 1


if __name__ == "__main__":
    raise SystemExit(main())
