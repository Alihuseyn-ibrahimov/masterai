"""`license_gate_flow.mjs` üçün LOKAL test məlumatı (produksiyada İŞLƏTMƏ).

İşlətmək (backend başlamazdan ƏVVƏL, eyni DB yolları ilə):
    USERS_DB_PATH=... CHATS_DB_PATH=... python deploy/diagnostics/license_seed.py seed
    python deploy/diagnostics/license_seed.py status <course_id> <trial|suspended>
    python deploy/diagnostics/license_seed.py registration   # registration_flow.mjs üçün
    python deploy/diagnostics/license_seed.py owner          # owner_panel_flow.mjs üçün

`seed` JSON çap edir: kurs id-si, e-poçt/şifrələr, çat id-si.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from server.auth import hash_password  # noqa: E402
from server.chat_store import ChatStore  # noqa: E402
from server.user_store import UserStore  # noqa: E402

PASSWORD = "Parol1234"


def _users() -> UserStore:
    return UserStore(os.environ["USERS_DB_PATH"])


def seed() -> None:
    users = _users()
    chats = ChatStore(os.environ["CHATS_DB_PATH"])
    # 3 gün qalıb — müəllim banneri görünməlidir.
    course = users.courses.create("E2E English", "english", trial_days=3, seat_limit=30)
    teacher = users.create("muellim@e2e.az", hash_password(PASSWORD), "Müəllim",
                           course_id=course["id"])
    users.set_teacher(teacher["id"], True)
    student = users.create("telebe@e2e.az", hash_password(PASSWORD), "Tələbə",
                           course_id=course["id"])
    chat = chats.create(kind="group", created_by=teacher["id"], name="E2E sinif",
                        course_id=course["id"])
    chats.add_member(chat["id"], teacher["id"])
    chats.add_member(chat["id"], student["id"])
    print(json.dumps({
        "course_id": course["id"], "chat_id": chat["id"], "password": PASSWORD,
        "teacher": teacher["email"], "student": student["email"],
    }))


def registration() -> None:
    """1 yerlik kurs + müəllim dəvəti: qapalı qeydiyyatın brauzer yoxlaması."""
    users = _users()
    course = users.courses.create("E2E qeydiyyat", "english", trial_days=30, seat_limit=1)
    invite = users.courses.create_teacher_invite(course["id"], created_by=0)
    print(json.dumps({
        "course_id": course["id"], "join_code": course["join_code"],
        "invite": invite, "password": PASSWORD,
    }))


def owner() -> None:
    """Platforma sahibi (kurs #1) + sahib OLMAYAN admin-müəllim (404 yoxlaması)."""
    users = _users()
    boss = users.create("sahib@e2e.az", hash_password(PASSWORD), "Sahib")
    users.set_platform_owner(boss["id"], True)
    other = users.create("admin@e2e.az", hash_password(PASSWORD), "Admin müəllim")
    users.set_teacher(other["id"], True)
    users.set_admin(other["id"], True)
    print(json.dumps({"owner": boss["email"], "other": other["email"], "password": PASSWORD}))


def set_status(course_id: int, status: str) -> None:
    _users().courses.set_status(course_id, status)


if __name__ == "__main__":
    if sys.argv[1] == "seed":
        seed()
    elif sys.argv[1] == "owner":
        owner()
    elif sys.argv[1] == "registration":
        registration()
    elif sys.argv[1] == "status":
        set_status(int(sys.argv[2]), sys.argv[3])
