"""Sinifdə QR davamiyyət və əl ilə düzəliş (MasterAI Classroom, gün 6)."""

import pytest
from fastapi.testclient import TestClient

from server import attendance_qr
from server.app import app, get_chat_store, get_lesson_store, get_token_secret, get_user_store
from server.auth import create_token
from server.chat_store import ChatStore
from server.lesson_store import LessonStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


# ---- Kodun özü ----

def test_code_changes_every_window_and_previous_window_is_accepted():
    t = 1_800_000_000.0  # pəncərənin tam başlanğıcı (30-a bölünür)
    code = attendance_qr.make_code(_SECRET, 7, now=t)
    assert attendance_qr.make_code(_SECRET, 7, now=t + 29) == code
    assert attendance_qr.make_code(_SECRET, 7, now=t + 30) != code
    assert attendance_qr.verify_code(_SECRET, 7, code, now=t + 45)       # əvvəlki pəncərə
    assert not attendance_qr.verify_code(_SECRET, 7, code, now=t + 60)   # artıq köhnədir


def test_code_is_bound_to_lesson_and_secret():
    t = 1_800_000_000.0
    code = attendance_qr.make_code(_SECRET, 7, now=t)
    assert not attendance_qr.verify_code(_SECRET, 8, code, now=t)
    assert not attendance_qr.verify_code("başqa-açar", 7, code, now=t)
    assert not attendance_qr.verify_code(_SECRET, 7, "", now=t)


def test_join_url_uses_site_url(monkeypatch):
    monkeypatch.setenv("SITE_URL", "http://127.0.0.1:8123/")
    assert attendance_qr.join_url(5, "ABC") == "http://127.0.0.1:8123/dersim.html?id=5&qr=ABC"


def test_qr_svg_is_plain_svg():
    svg = attendance_qr.qr_svg("https://masterai.prdostu.com/dersim.html?id=1&qr=ABC")
    assert svg.startswith("<svg") and "<script" not in svg


# ---- Marşrutlar ----

@pytest.fixture
def env():
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    lessons = LessonStore(":memory:")
    for dep, value in {get_user_store: users, get_chat_store: chats, get_lesson_store: lessons,
                       get_token_secret: _SECRET}.items():
        app.dependency_overrides[dep] = (lambda v: lambda: v)(value)
    course = users.courses.create("Kurs", "exam_prep", trial_days=30, seat_limit=30)

    def person(email, name, *, teacher=False):
        row = users.create(email, "h", name, course_id=course["id"])
        if teacher:
            users.set_teacher(row["id"], True)
        return users.get_by_id(row["id"])

    teacher = person("t@x.az", "Müəllim", teacher=True)
    ali = person("a@x.az", "Əli")
    outsider = person("o@x.az", "Kənar")
    chat = chats.create(kind="group", created_by=teacher["id"], name="Sinif 1", course_id=course["id"])
    for member in (teacher, ali):
        chats.add_member(chat["id"], member["id"])
    lesson = lessons.create(chat["id"], course_id=course["id"], created_by=teacher["id"], title="Sinif dərsi",
                            description="", starts_at="2026-11-03T06:00:00+00:00", duration_min=90,
                            mode="offline")
    yield {"client": TestClient(app), "lessons": lessons, "teacher": teacher, "ali": ali,
           "outsider": outsider, "lesson": lesson}
    app.dependency_overrides.clear()


def _auth(user):
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


def test_qr_only_for_teacher_and_live_lesson(env):
    url = f"/live/lessons/{env['lesson']['id']}/qr"
    assert env["client"].get(url, headers=_auth(env["teacher"])).status_code == 409
    env["lessons"].set_status(env["lesson"]["id"], "live")
    assert env["client"].get(url, headers=_auth(env["ali"])).status_code == 403
    data = env["client"].get(url, headers=_auth(env["teacher"])).json()
    assert data["url"].endswith(f"dersim.html?id={env['lesson']['id']}&qr={data['code']}")
    assert data["svg"].startswith("<svg")
    assert 1 <= data["expires_in"] <= attendance_qr.WINDOW_SECONDS


def test_teacher_marks_and_unmarks_student_by_hand(env):
    lesson_id = env["lesson"]["id"]
    url = f"/live/lessons/{lesson_id}/attendance/{env['ali']['id']}"
    assert env["client"].post(url, headers=_auth(env["teacher"])).status_code == 409  # başlamayıb
    env["lessons"].set_status(lesson_id, "live")
    assert env["client"].post(url, headers=_auth(env["teacher"])).status_code == 204
    assert env["lessons"].list_attendance(lesson_id)[0]["method"] == "manual"
    assert env["client"].delete(url, headers=_auth(env["teacher"])).status_code == 204
    assert env["lessons"].list_attendance(lesson_id) == []
    assert env["client"].post(url, headers=_auth(env["ali"])).status_code == 403


def test_teacher_cannot_mark_non_member_or_teacher(env):
    env["lessons"].set_status(env["lesson"]["id"], "live")
    base = f"/live/lessons/{env['lesson']['id']}/attendance"
    for target in (env["outsider"], env["teacher"]):
        r = env["client"].post(f"{base}/{target['id']}", headers=_auth(env["teacher"]))
        assert r.status_code == 404
