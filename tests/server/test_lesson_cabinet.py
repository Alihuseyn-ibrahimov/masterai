"""Tələbə kabineti: dərs səhifəsi + şəxsi qeyd (MasterAI Classroom, gün 5)."""

import pytest
from fastapi.testclient import TestClient

from server.app import (
    app,
    get_chat_store,
    get_homework_store,
    get_lesson_store,
    get_question_set_store,
    get_summary_store,
    get_token_secret,
    get_user_store,
)
from server.auth import create_token
from server.chat_store import ChatStore
from server.homework_store import HomeworkStore
from server.lesson_store import LessonStore
from server.question_set_store import QuestionSetStore
from server.summary_store import SummaryStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


@pytest.fixture
def env():
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    lessons = LessonStore(":memory:")
    banks = QuestionSetStore(":memory:")
    summaries = SummaryStore(":memory:")
    homework = HomeworkStore(":memory:")
    for dep, value in {get_user_store: users, get_chat_store: chats, get_lesson_store: lessons,
                       get_question_set_store: banks, get_summary_store: summaries,
                       get_homework_store: homework, get_token_secret: _SECRET}.items():
        app.dependency_overrides[dep] = (lambda v: lambda: v)(value)

    course = users.courses.create("Kurs", "exam_prep", trial_days=30, seat_limit=30)

    def person(email, name, *, teacher=False):
        row = users.create(email, "h", name, course_id=course["id"])
        if teacher:
            users.set_teacher(row["id"], True)
        return users.get_by_id(row["id"])

    teacher = person("t@x.az", "Müəllim", teacher=True)
    ali = person("a@x.az", "Əli")
    vali = person("v@x.az", "Vəli")
    outsider = person("o@x.az", "Kənar")
    chat = chats.create(kind="group", created_by=teacher["id"], name="Sinif 1", course_id=course["id"])
    other = chats.create(kind="group", created_by=teacher["id"], name="Sinif 2", course_id=course["id"])
    for member in (teacher, ali, vali):
        chats.add_member(chat["id"], member["id"])
    chats.add_member(other["id"], teacher["id"])

    lesson = lessons.create(chat["id"], course_id=course["id"], created_by=teacher["id"],
                            title="Konstitusiya", description="", starts_at="2026-11-03T06:00:00+00:00",
                            duration_min=90, mode="online")
    bank = banks.create("qanunvericilik", "Konstitusiya", "text", "/x.txt",
                        created_by=teacher["id"], course_id=course["id"])
    banks.mark_ready(bank["id"])
    lessons.set_question_set(lesson["id"], bank["id"])

    yield {"client": TestClient(app), "lessons": lessons, "summaries": summaries, "homework": homework,
           "banks": banks, "teacher": teacher, "ali": ali, "vali": vali, "outsider": outsider,
           "chat": chat, "other": other, "lesson": lesson, "bank": bank, "course": course}
    app.dependency_overrides.clear()


def _auth(user):
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


def _cabinet(env, user="ali"):
    r = env["client"].get(f"/me/lessons/{env['lesson']['id']}/cabinet", headers=_auth(env[user]))
    assert r.status_code == 200, r.text
    return r.json()


def test_cabinet_hides_bank_until_teacher_hands_it_out(env):
    # Bank hazırdır, konspekt də hazırdır, amma heç biri tələbəyə verilməyib.
    summary = env["summaries"].start(env["bank"]["id"], created_by=env["teacher"]["id"],
                                     course_id=env["course"]["id"])
    env["summaries"].mark_ready(summary["id"], "{}")
    data = _cabinet(env)
    assert data["lesson"]["title"] == "Konstitusiya"
    assert data["summary"] is None
    assert data["assignments"] == []
    assert data["note"] == {"text": "", "updated_at": None}


def test_cabinet_shows_published_summary_and_assignment_with_own_status(env):
    summary = env["summaries"].start(env["bank"]["id"], created_by=env["teacher"]["id"],
                                     course_id=env["course"]["id"])
    env["summaries"].mark_ready(summary["id"], "{}")
    env["summaries"].publish(summary["id"], env["chat"]["id"])
    assignment = env["homework"].create_assignment(env["chat"]["id"], env["bank"]["id"], "2026-11-10",
                                                   created_by=env["teacher"]["id"])
    # Başqa bankın tapşırığı bu dərsin səhifəsinə düşməməlidir.
    another = env["banks"].create("qanunvericilik", "Başqa", "text", "/y.txt",
                                  created_by=env["teacher"]["id"], course_id=env["course"]["id"])
    env["homework"].create_assignment(env["chat"]["id"], another["id"], "2026-11-10",
                                      created_by=env["teacher"]["id"])
    data = _cabinet(env)
    assert data["summary"] == {"id": summary["id"], "title": "Konstitusiya"}
    assert [a["assignment_id"] for a in data["assignments"]] == [assignment["id"]]
    assert data["assignments"][0]["status"] == "gözləyir"


def test_summary_published_to_another_class_is_not_shown(env):
    summary = env["summaries"].start(env["bank"]["id"], created_by=env["teacher"]["id"],
                                     course_id=env["course"]["id"])
    env["summaries"].mark_ready(summary["id"], "{}")
    env["summaries"].publish(summary["id"], env["other"]["id"])
    assert _cabinet(env)["summary"] is None


def test_note_is_private_and_empty_text_deletes_it(env):
    url = f"/me/lessons/{env['lesson']['id']}/note"
    r = env["client"].put(url, json={"text": "Maddə 7 - vacib"}, headers=_auth(env["ali"]))
    assert r.status_code == 200
    assert r.json()["text"] == "Maddə 7 - vacib"
    assert r.json()["updated_at"]
    assert _cabinet(env)["note"]["text"] == "Maddə 7 - vacib"
    # Vəli Əlinin qeydini görmür.
    assert _cabinet(env, "vali")["note"]["text"] == ""
    r = env["client"].put(url, json={"text": "  "}, headers=_auth(env["ali"]))
    assert r.json() == {"text": "", "updated_at": None}
    assert env["lessons"].get_note(env["lesson"]["id"], env["ali"]["id"]) is None


def test_non_member_gets_404_for_cabinet_and_note(env):
    lesson_id = env["lesson"]["id"]
    headers = _auth(env["outsider"])
    assert env["client"].get(f"/me/lessons/{lesson_id}/cabinet", headers=headers).status_code == 404
    r = env["client"].put(f"/me/lessons/{lesson_id}/note", json={"text": "x"}, headers=headers)
    assert r.status_code == 404


def test_note_length_is_limited(env):
    r = env["client"].put(f"/me/lessons/{env['lesson']['id']}/note", json={"text": "a" * 20_001},
                          headers=_auth(env["ali"]))
    assert r.status_code == 422


def test_deleting_lesson_removes_notes(env):
    env["lessons"].set_note(env["lesson"]["id"], env["ali"]["id"], "qeyd")
    env["lessons"].delete(env["lesson"]["id"])
    assert env["lessons"].get_note(env["lesson"]["id"], env["ali"]["id"]) is None
