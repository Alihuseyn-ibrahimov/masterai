"""Lövhə şəkli → mətn (MasterAI Classroom, gün 7)."""

import io
import os
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from pipeline import board_ocr
from server.app import (
    app,
    get_board_reader,
    get_chat_store,
    get_lesson_store,
    get_token_secret,
    get_upload_dir,
    get_user_store,
)
from server.auth import create_token
from server.chat_store import ChatStore
from server.lesson_store import BOARD_SEQ_START, LessonStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


@pytest.fixture
def env(tmp_path):
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    lessons = LessonStore(":memory:")
    seen = []

    def fake_reader(path):
        seen.append(path)
        content = open(path, "rb").read()
        if content == b"bad":
            raise board_ocr.IngestionError("Şəkildə yazı tanınmadı")
        return f"Maddə {content.decode()}"

    for dep, value in {get_user_store: users, get_chat_store: chats, get_lesson_store: lessons,
                       get_token_secret: _SECRET, get_upload_dir: str(tmp_path),
                       get_board_reader: fake_reader}.items():
        app.dependency_overrides[dep] = (lambda v: lambda: v)(value)

    course = users.courses.create("Kurs", "exam_prep", trial_days=30, seat_limit=30)
    teacher = users.create("t@x.az", "h", "Müəllim", course_id=course["id"])
    users.set_teacher(teacher["id"], True)
    student = users.create("a@x.az", "h", "Əli", course_id=course["id"])
    chat = chats.create(kind="group", created_by=teacher["id"], name="Sinif", course_id=course["id"])
    for member in (teacher, student):
        chats.add_member(chat["id"], member["id"])
    lesson = lessons.create(chat["id"], course_id=course["id"], created_by=teacher["id"], title="Sinif",
                            description="", starts_at="2026-11-03T06:00:00+00:00", duration_min=90,
                            mode="offline")
    with TestClient(app) as client:
        yield {"client": client, "lessons": lessons, "lesson": lesson, "seen": seen,
               "auth": {"Authorization": f"Bearer {create_token(teacher['id'], secret=_SECRET)}"},
               "student_auth": {"Authorization": f"Bearer {create_token(student['id'], secret=_SECRET)}"}}
    app.dependency_overrides.clear()


def _send(env, content=b"7", name="board.jpg", auth=None):
    return env["client"].post(f"/live/lessons/{env['lesson']['id']}/board",
                              files={"image": (name, content, "image/jpeg")}, headers=auth or env["auth"])


def _transcript(env, timeout=5.0):
    deadline = time.time() + timeout
    while True:
        data = env["client"].get(f"/live/lessons/{env['lesson']['id']}/transcript", headers=env["auth"]).json()
        if all(s["status"] != "processing" for s in data["segments"]) or time.time() > deadline:
            return data
        time.sleep(0.05)


def test_board_photo_text_joins_lesson_text_after_audio(env):
    lesson_id = env["lesson"]["id"]
    assert _send(env).status_code == 409  # dərs başlamayıb
    env["lessons"].set_status(lesson_id, "live")
    # Səs hissəsi də var: lövhə mətni ondan SONRA gəlir və nömrələri toqquşmur.
    env["lessons"].start_segment(lesson_id, 0)
    env["lessons"].finish_segment(lesson_id, 0, text="Müəllim danışır")
    assert _send(env, b"7").status_code == 202
    assert _send(env, b"8").status_code == 202
    data = _transcript(env)
    boards = [s for s in data["segments"] if s["kind"] == "board"]
    assert [s["seq"] for s in boards] == [BOARD_SEQ_START, BOARD_SEQ_START + 1]
    assert [s["kind"] for s in data["segments"]] == ["audio", "board", "board"]
    assert data["text"] == "Müəllim danışır\n\nLövhədən:\nMaddə 7\n\nLövhədən:\nMaddə 8"
    # Şəkil serverdə qalmır.
    assert env["seen"] and not any(os.path.exists(p) for p in env["seen"])


def test_unreadable_board_is_failed_with_reason_and_file_removed(env):
    env["lessons"].set_status(env["lesson"]["id"], "live")
    _send(env, b"bad")
    segment = _transcript(env)["segments"][0]
    assert segment["status"] == "failed"
    assert "tanınmadı" in segment["error"]
    assert not os.path.exists(env["seen"][0])


def test_board_rejects_non_image_and_students(env):
    env["lessons"].set_status(env["lesson"]["id"], "live")
    assert _send(env, name="notes.pdf").status_code == 415
    assert _send(env, auth=env["student_auth"]).status_code == 403


# ---- OCR hazırlığı ----

def test_prepare_applies_exif_rotation_grayscale_and_downscale():
    image = Image.new("RGB", (4000, 1000), "white")
    exif = image.getexif()
    exif[0x0112] = 6  # telefon: «90° döndər»
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", exif=exif)
    buffer.seek(0)
    prepared = board_ocr.prepare(Image.open(buffer))
    assert prepared.mode == "L"
    assert prepared.size[1] > prepared.size[0]  # döndərilib: indi hündürdür
    assert max(prepared.size) == board_ocr.MAX_SIDE


def test_read_board_raises_on_blank_and_non_image(tmp_path):
    blank = tmp_path / "blank.png"
    Image.new("L", (200, 200), 255).save(blank)
    with pytest.raises(board_ocr.IngestionError):
        board_ocr.read_board(str(blank))
    junk = tmp_path / "junk.jpg"
    junk.write_bytes(b"not an image")
    with pytest.raises(board_ocr.IngestionError):
        board_ocr.read_board(str(junk))
