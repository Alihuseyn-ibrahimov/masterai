"""Dərs səsi → mətn (MasterAI Classroom, gün 3, 2026-10-31)."""

import os

import pytest
from fastapi.testclient import TestClient

from server.app import (
    app,
    get_chat_store,
    get_lesson_store,
    get_token_secret,
    get_transcriber,
    get_upload_dir,
    get_user_store,
)
from server.auth import create_token
from server.chat_store import ChatStore
from server.lesson_store import LessonStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"
_LESSON = {"title": "Konstitusiya", "starts_at": "2026-11-03T10:00:00+04:00", "mode": "online"}


@pytest.fixture
def env(tmp_path):
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    lessons = LessonStore(":memory:")
    seen = []

    def fake_transcriber(path):
        seen.append(path)
        content = open(path, "rb").read()
        if content == b"bad":
            raise RuntimeError("Whisper 500")
        return f"hissə: {content.decode()}"

    for dep, value in {get_user_store: users, get_chat_store: chats, get_lesson_store: lessons,
                       get_token_secret: _SECRET, get_upload_dir: str(tmp_path),
                       get_transcriber: fake_transcriber}.items():
        app.dependency_overrides[dep] = (lambda v: lambda: v)(value)

    course = users.courses.create("Kurs", "exam_prep", trial_days=30, seat_limit=30)
    teacher = users.create("t@x.az", "h", "Müəllim", course_id=course["id"])
    users.set_teacher(teacher["id"], True)
    teacher = users.get_by_id(teacher["id"])
    student = users.create("a@x.az", "h", "Əli", course_id=course["id"])
    chat = chats.create(kind="group", created_by=teacher["id"], name="Sinif", course_id=course["id"])
    for member in (teacher, student):
        chats.add_member(chat["id"], member["id"])

    client = TestClient(app)
    auth = {"Authorization": f"Bearer {create_token(teacher['id'], secret=_SECRET)}"}
    lesson = client.post(f"/chats/{chat['id']}/lessons", json=_LESSON, headers=auth).json()
    yield {"client": client, "auth": auth, "lesson": lesson, "lessons": lessons, "seen": seen,
           "student_auth": {"Authorization": f"Bearer {create_token(student['id'], secret=_SECRET)}"}}
    app.dependency_overrides.clear()


def _send(env, seq, content=b"salam", name="part.webm", auth=None):
    return env["client"].post(
        f"/live/lessons/{env['lesson']['id']}/audio", data={"seq": str(seq)},
        files={"audio": (name, content, "audio/webm")}, headers=auth or env["auth"],
    )


def _start(env):
    env["client"].post(f"/live/lessons/{env['lesson']['id']}/start", headers=env["auth"])


def _transcript(env):
    return env["client"].get(f"/live/lessons/{env['lesson']['id']}/transcript", headers=env["auth"]).json()


def test_segments_are_joined_in_order_and_audio_is_deleted(env):
    _start(env)
    # İkinci hissə birincidən əvvəl çatsa da mətn sıra ilə birləşir.
    assert _send(env, 1, b"iki").status_code == 202
    assert _send(env, 0, b"bir").status_code == 202
    body = _transcript(env)
    assert [s["status"] for s in body["segments"]] == ["ready", "ready"]
    assert body["text"] == "hissə: bir\n\nhissə: iki"
    assert all(not os.path.exists(p) for p in env["seen"])


def test_failed_segment_does_not_lose_the_rest_and_can_be_resent(env):
    _start(env)
    _send(env, 0, b"bir")
    _send(env, 1, b"bad")
    body = _transcript(env)
    assert body["segments"][1]["status"] == "failed" and "Whisper" in body["segments"][1]["error"]
    assert body["text"] == "hissə: bir"
    _send(env, 1, b"iki")  # təkrar göndəriş eyni sətrin yerinə yazılır
    body = _transcript(env)
    assert len(body["segments"]) == 2 and body["text"].endswith("hissə: iki")


def test_audio_before_lesson_start_is_rejected(env):
    assert _send(env, 0).status_code == 409


def test_last_segment_accepted_after_lesson_ended(env):
    _start(env)
    env["client"].post(f"/live/lessons/{env['lesson']['id']}/end", headers=env["auth"])
    assert _send(env, 0).status_code == 202


def test_only_audio_files_and_only_teacher(env):
    _start(env)
    assert _send(env, 0, name="x.exe").status_code == 415
    assert _send(env, 0, auth=env["student_auth"]).status_code == 403
    r = env["client"].get(f"/live/lessons/{env['lesson']['id']}/transcript", headers=env["student_auth"])
    assert r.status_code == 403


def test_restart_marks_unfinished_segments_failed():
    store = LessonStore(":memory:")
    store.start_segment(1, 0)
    assert store.fail_interrupted_segments() == 1
    assert store.list_segments(1)[0]["status"] == "failed"
