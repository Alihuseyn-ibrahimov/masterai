"""Sahib paneli API-si — spec 2026-09-29 §3.

Yalnız `is_platform_owner`. Başqa HƏR KƏS (admin, müəllim, tələbə) bütün
`/owner/*` marşrutlarında 404 alır — panelin varlığı belə açılmır.
Aktivlik rəqəmləri YENİ izləmə kodu olmadan mövcud cədvəllərdən sayılır.
Hər sahib əməliyyatı jurnala yazılır (ödəniş mübahisəsi üçün).
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion
from server.app import (
    app,
    get_chat_store,
    get_homework_store,
    get_live_session_store,
    get_message_store,
    get_question_set_store,
    get_token_secret,
    get_user_store,
)
from server.auth import create_token
from server.chat_store import ChatStore
from server.course_store import DEFAULT_COURSE_ID
from server.homework_store import HomeworkStore
from server.live_session_store import LiveSessionStore
from server.message_store import MessageStore
from server.question_set_store import QuestionSetStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


@pytest.fixture
def env():
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    messages = MessageStore(":memory:")
    question_sets = QuestionSetStore(":memory:")
    live = LiveSessionStore(":memory:")
    homework = HomeworkStore(":memory:")
    stores = {
        get_user_store: users, get_chat_store: chats, get_message_store: messages,
        get_question_set_store: question_sets, get_live_session_store: live,
        get_homework_store: homework, get_token_secret: _SECRET,
    }

    def _const(value):
        return lambda: value

    for dep, value in stores.items():
        app.dependency_overrides[dep] = _const(value)

    owner = users.create("sahib@x.az", "h", "Sahib")
    users.set_platform_owner(owner["id"], True)
    admin = users.create("admin@x.az", "h", "Admin")
    users.set_admin(admin["id"], True)
    users.set_teacher(admin["id"], True)
    course = users.courses.create("English Club", "english", trial_days=30, seat_limit=10)
    yield {
        "client": TestClient(app), "users": users, "chats": chats, "messages": messages,
        "question_sets": question_sets, "live": live, "homework": homework,
        "owner": users.get_by_id(owner["id"]), "admin": users.get_by_id(admin["id"]),
        "course": course,
    }
    app.dependency_overrides.clear()


def _auth(user):
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


def _owner_routes():
    return sorted(
        (sorted(r.methods)[0], r.path)
        for r in app.routes
        if isinstance(r, APIRoute) and r.path.startswith("/owner")
    )


def test_owner_routes_exist():
    paths = {p for _, p in _owner_routes()}
    assert "/owner/courses" in paths
    assert "/owner/audit-log" in paths


@pytest.mark.parametrize("method,path", _owner_routes())
def test_non_owner_gets_404_everywhere(env, method, path):
    """Admin belə — panelin varlığı açılmır."""
    url = path.replace("{course_id}", str(env["course"]["id"]))
    r = env["client"].request(method, url, headers=_auth(env["admin"]), json={})
    unknown = env["client"].get("/bele-marsrut-yoxdur", headers=_auth(env["admin"]))
    assert r.status_code == 404
    assert r.json() == unknown.json()  # naməlum marşrutdan fərqlənmir


def _courses(env):
    r = env["client"].get("/owner/courses", headers=_auth(env["owner"]))
    assert r.status_code == 200
    return {c["id"]: c for c in r.json()}


class TestCourseList:
    def test_lists_all_courses_with_status(self, env):
        courses = _courses(env)
        assert set(courses) == {DEFAULT_COURSE_ID, env["course"]["id"]}
        english = courses[env["course"]["id"]]
        assert english["status"] == "trial"
        assert english["is_open"] is True
        assert english["days_left"] == 30
        assert english["seat_limit"] == 10
        assert english["join_code"] == env["course"]["join_code"]
        assert courses[DEFAULT_COURSE_ID]["days_left"] is None

    def test_counts_students_and_teachers(self, env):
        cid = env["course"]["id"]
        users = env["users"]
        t = users.create("t@x.az", "h", "T", course_id=cid)
        users.set_teacher(t["id"], True)
        users.create_student("s1@x.az", "h", "S1", course_id=cid)
        gone = users.create_student("s2@x.az", "h", "S2", course_id=cid)
        users.set_active(gone["id"], False)
        c = _courses(env)[cid]
        assert c["students_active"] == 1
        assert c["teachers"] == 1

    def test_activity_last_7_days_from_existing_tables(self, env):
        cid = env["course"]["id"]
        users, chats = env["users"], env["chats"]
        t = users.create("t@x.az", "h", "T", course_id=cid)
        chat = chats.create(kind="group", created_by=t["id"], name="S", course_id=cid)
        env["messages"].create(chat["id"], t["id"], "text", "salam")
        qs = env["question_sets"].create("mentiq", "U1", "link", "https://x", created_by=t["id"], course_id=cid)
        env["question_sets"].add_question(qs["id"], MCQQuestion(
            question="Q?", options=["A", "B", "C", "D", "E"], correct_index=0, explanation="izah"))
        session = env["live"].create_session(qs["id"], chat_id=chat["id"], created_by=t["id"])
        p = env["live"].add_participant(session["id"], "S", user_id=t["id"])
        env["live"].record_answer(session["id"], p["id"], 0, 0, True)
        assignment = env["homework"].create_assignment(chat["id"], qs["id"], "2099-01-01", created_by=t["id"])
        attempt = env["homework"].get_or_create_attempt(assignment["id"], student_id=t["id"])
        env["homework"].answer(attempt["id"], 0, 0, True, total_questions=1)
        # Başqa kursun aktivliyi sayılmamalıdır
        other = chats.create(kind="group", created_by=t["id"], name="X", course_id=DEFAULT_COURSE_ID)
        env["messages"].create(other["id"], t["id"], "text", "kənar")

        c = _courses(env)[cid]
        assert c["activity_7d"] == {"sessions": 1, "question_sets": 1, "answers": 2, "messages": 1}
        assert c["last_activity"] is not None
        assert _courses(env)[DEFAULT_COURSE_ID]["activity_7d"]["messages"] == 1

    def test_old_activity_not_counted(self, env):
        cid = env["course"]["id"]
        t = env["users"].create("t@x.az", "h", "T", course_id=cid)
        chat = env["chats"].create(kind="group", created_by=t["id"], name="S", course_id=cid)
        env["messages"].create(chat["id"], t["id"], "text", "köhnə")
        env["messages"]._conn.execute("UPDATE messages SET created_at = '2020-01-01T00:00:00+00:00'")
        env["messages"]._conn.commit()
        c = _courses(env)[cid]
        assert c["activity_7d"]["messages"] == 0
        assert c["last_activity"] == "2020-01-01T00:00:00+00:00"


class TestActions:
    def test_create_course(self, env):
        r = env["client"].post("/owner/courses", headers=_auth(env["owner"]), json={
            "name": "Yeni kurs", "profile": "english", "trial_days": 14, "seat_limit": 25})
        assert r.status_code == 201
        body = r.json()
        assert body["status"] == "trial" and body["days_left"] == 14 and body["seat_limit"] == 25

    def test_create_rejects_unknown_profile(self, env):
        r = env["client"].post("/owner/courses", headers=_auth(env["owner"]), json={
            "name": "X", "profile": "riyaziyyat", "trial_days": 30, "seat_limit": 5})
        assert r.status_code == 422

    def test_payment_during_trial_starts_after_trial(self, env):
        """Sınaqda ödəyən müştəri qalan sınaq günlərini İTİRMƏMƏLİDİR."""
        cid = env["course"]["id"]
        r = env["client"].post(f"/owner/courses/{cid}/payments", headers=_auth(env["owner"]), json={"months": 1})
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "active"
        assert body["days_left"] == 60  # 30 sınaq + 30 ödəniş

    def test_payment_after_expiry_starts_today(self, env):
        cid = env["users"].courses.create("Bitmiş", "english", trial_days=-10, seat_limit=5)["id"]
        r = env["client"].post(f"/owner/courses/{cid}/payments", headers=_auth(env["owner"]), json={"months": 2})
        assert r.json()["days_left"] == 60
        assert r.json()["is_open"] is True

    def test_payment_months_bounded(self, env):
        cid = env["course"]["id"]
        for months in (0, 13):
            r = env["client"].post(f"/owner/courses/{cid}/payments", headers=_auth(env["owner"]), json={"months": months})
            assert r.status_code == 422

    def test_suspend_and_resume(self, env):
        cid = env["course"]["id"]
        r = env["client"].post(f"/owner/courses/{cid}/suspend", headers=_auth(env["owner"]))
        assert r.json()["status"] == "suspended" and r.json()["is_open"] is False
        r = env["client"].post(f"/owner/courses/{cid}/resume", headers=_auth(env["owner"]))
        assert r.json()["status"] == "trial" and r.json()["is_open"] is True

    def test_resume_paid_course_returns_to_active(self, env):
        cid = env["course"]["id"]
        env["client"].post(f"/owner/courses/{cid}/payments", headers=_auth(env["owner"]), json={"months": 1})
        env["client"].post(f"/owner/courses/{cid}/suspend", headers=_auth(env["owner"]))
        r = env["client"].post(f"/owner/courses/{cid}/resume", headers=_auth(env["owner"]))
        assert r.json()["status"] == "active"

    def test_owner_course_cannot_be_suspended_or_billed(self, env):
        """Kurs #1 (mövcud imtahan kursu) müddətsizdir — səhv kliklə bütün
        mövcud istifadəçiləri bağlamaq mümkün olmamalıdır."""
        for action, body in (("suspend", None), ("payments", {"months": 1})):
            r = env["client"].post(f"/owner/courses/{DEFAULT_COURSE_ID}/{action}",
                                   headers=_auth(env["owner"]), json=body)
            assert r.status_code == 400
        assert env["users"].courses.get(DEFAULT_COURSE_ID)["status"] == "owner"

    def test_update_limits(self, env):
        cid = env["course"]["id"]
        r = env["client"].patch(f"/owner/courses/{cid}", headers=_auth(env["owner"]), json={
            "seat_limit": 40, "upload_limit_student": 3, "upload_limit_teacher": 50})
        assert r.status_code == 200
        c = env["users"].courses.get(cid)
        assert (c["seat_limit"], c["upload_limit_student"], c["upload_limit_teacher"]) == (40, 3, 50)

    def test_update_rejects_negative(self, env):
        r = env["client"].patch(f"/owner/courses/{env['course']['id']}", headers=_auth(env["owner"]),
                                json={"seat_limit": -1})
        assert r.status_code == 422

    def test_regenerate_join_code_kills_old_code(self, env):
        cid = env["course"]["id"]
        old = env["course"]["join_code"]
        r = env["client"].post(f"/owner/courses/{cid}/join-code", headers=_auth(env["owner"]))
        new = r.json()["join_code"]
        assert new != old
        assert env["users"].courses.get_by_join_code(old) is None

    def test_teacher_invite_is_usable_once(self, env):
        cid = env["course"]["id"]
        r = env["client"].post(f"/owner/courses/{cid}/teacher-invites", headers=_auth(env["owner"]))
        assert r.status_code == 201
        token = r.json()["token"]
        reg = env["client"].post("/auth/register", json={
            "email": "yeni@x.az", "password": "Parol1234", "display_name": "Yeni", "invite_token": token})
        assert reg.status_code == 201 and reg.json()["user"]["is_teacher"] is True

    def test_unknown_course_404(self, env):
        r = env["client"].post("/owner/courses/999/suspend", headers=_auth(env["owner"]))
        assert r.status_code == 404


class TestAuditLog:
    def test_actions_are_logged_newest_first(self, env):
        cid = env["course"]["id"]
        env["client"].post(f"/owner/courses/{cid}/payments", headers=_auth(env["owner"]), json={"months": 1})
        env["client"].post(f"/owner/courses/{cid}/suspend", headers=_auth(env["owner"]))
        rows = env["client"].get("/owner/audit-log", headers=_auth(env["owner"])).json()
        assert [row["action"] for row in rows[:2]] == ["suspend", "payment"]
        assert rows[1]["course_id"] == cid
        assert "1" in rows[1]["details"]
        assert rows[0]["owner_name"] == "Sahib"

    def test_invite_token_never_logged(self, env):
        cid = env["course"]["id"]
        token = env["client"].post(f"/owner/courses/{cid}/teacher-invites",
                                   headers=_auth(env["owner"])).json()["token"]
        rows = env["client"].get("/owner/audit-log", headers=_auth(env["owner"])).json()
        assert rows[0]["action"] == "teacher_invite"
        assert token not in str(rows)


def test_user_info_exposes_owner_flag(env):
    """Frontend sahib linkini `is_platform_owner` ilə göstərir."""
    r = env["client"].get("/me/course", headers=_auth(env["owner"]))
    assert r.status_code == 200
    login_user = env["users"].get_by_id(env["owner"]["id"])
    from server.app import _user_info
    assert _user_info(login_user).is_platform_owner is True


def test_audit_details_are_human_readable(env):
    """Jurnal insana göstərilir — daxili dəyərlər (`english`, `active`,
    `seat_limit=`) görünməməlidir (brauzer ekran şəklində tapıldı)."""
    client, auth = env["client"], _auth(env["owner"])
    cid = client.post("/owner/courses", headers=auth, json={
        "name": "Kurs", "profile": "english", "trial_days": 30, "seat_limit": 5}).json()["id"]
    client.post(f"/owner/courses/{cid}/payments", headers=auth, json={"months": 1})
    client.post(f"/owner/courses/{cid}/suspend", headers=auth)
    client.post(f"/owner/courses/{cid}/resume", headers=auth)
    client.patch(f"/owner/courses/{cid}", headers=auth, json={"seat_limit": 9, "upload_limit_student": 2})
    details = " | ".join(row["details"] for row in client.get("/owner/audit-log", headers=auth).json())
    for internal in ("english", "exam_prep", "active", "trial", "seat_limit", "upload_limit"):
        assert internal not in details, f"{internal!r} jurnalda: {details}"
    assert "ingilis dili" in details and "tələbə limiti 9" in details
