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

    # `with`: bir event loop bütün test boyu yaşayır. Onsuz hər sorğu öz
    # loop-unu açıb bağlayır və fon task-ı (Whisper, sual bankı) yarıda
    # qala bilir - CI-da məhz belə oldu.
    with TestClient(app) as client:
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


def _transcript(env, timeout=5.0):
    """Mətnə çevirmə fon task-ıdır: cavab 202 qayıdanda hələ bitməmiş ola
    bilər (CI-da yavaş maşında məhz belə oldu). Bitənə qədər gözləyirik."""
    import time

    deadline = time.time() + timeout
    while True:
        body = env["client"].get(f"/live/lessons/{env['lesson']['id']}/transcript", headers=env["auth"]).json()
        if all(s["status"] != "processing" for s in body["segments"]) or time.time() > deadline:
            return body
        time.sleep(0.02)


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


# ---- Gün 4: dərs mətnindən sual bankı + xülasə ----------------------------

def _lesson_quiz_env(env, tmp_path):
    from pipeline.models import MCQQuestion, PipelineResult
    from pipeline.summary import LessonSummary
    from server.app import (
        get_material_generator, get_material_store, get_question_set_store, get_summarizer,
        get_summary_store,
    )
    from server.material_store import MaterialStore
    from server.question_set_store import QuestionSetStore
    from server.summary_store import SummaryStore

    seen = {}

    def generator(source, question_count=10, **options):
        seen["kind"] = source.kind
        seen["subject"] = options.get("subject")
        seen["text"] = open(source.location, encoding="utf-8").read()
        return PipelineResult(
            questions=[MCQQuestion(question=f"Sual {i}?", options=list("ABCDE"), correct_index=0,
                                   explanation="i") for i in range(3)],
            source=source, chunks_processed=1, chunks_failed=0, requested_question_count=question_count,
        )

    def summarizer(source):
        seen["summary_kind"] = source.kind
        return LessonSummary(title="Konspekt", intro="Giriş.", key_points=["Bir.", "İki."])

    question_sets, summaries = QuestionSetStore(":memory:"), SummaryStore(":memory:")
    for dep, value in {get_material_generator: generator, get_summarizer: summarizer,
                       get_question_set_store: question_sets, get_summary_store: summaries,
                       get_material_store: MaterialStore(":memory:")}.items():
        app.dependency_overrides[dep] = (lambda v: lambda: v)(value)
    return seen, question_sets, summaries


def _make_quiz(env, **body):
    return env["client"].post(f"/live/lessons/{env['lesson']['id']}/question-set",
                              json={"subject": "qanunvericilik", **body}, headers=env["auth"])


def test_lesson_transcript_becomes_question_bank_and_summary(env, tmp_path):
    import time

    seen, question_sets, summaries = _lesson_quiz_env(env, tmp_path)
    _start(env)
    _send(env, 0, ("Konstitusiya dövlətin əsas qanunudur. " * 20).encode())
    _transcript(env)
    r = _make_quiz(env, question_count=5)
    assert r.status_code == 202, r.text
    qs_id = r.json()["question_set_id"]
    deadline = time.time() + 5
    while question_sets.get(qs_id)["status"] == "processing" and time.time() < deadline:
        time.sleep(0.02)
    bank = question_sets.get(qs_id)
    assert bank["status"] == "ready" and bank["title"] == _LESSON["title"]
    assert bank["material_kind"] == "text" and seen["kind"] == "text"
    assert "Konstitusiya" in seen["text"]
    assert seen["subject"] == "qanunvericilik"
    summary = summaries.get_for_question_set(qs_id)
    deadline = time.time() + 5
    while summary["status"] == "processing" and time.time() < deadline:
        time.sleep(0.02)
        summary = summaries.get(summary["id"])
    assert summary["status"] == "ready" and seen["summary_kind"] == "text"
    lesson = env["client"].get(f"/me/lessons/{env['lesson']['id']}", headers=env["auth"]).json()
    assert lesson["question_set_id"] == qs_id
    # Təzədən hazırlamaq olar (fənn səhv seçilibsə): dərs yeni banka keçir,
    # köhnəsi silinmir.
    again = _make_quiz(env, subject="mentiq")
    assert again.status_code == 202 and again.json()["question_set_id"] != qs_id
    assert question_sets.get(qs_id) is not None
    # Hazırlanan bankın üstünə ikinci emal açılmır.
    new_id = again.json()["question_set_id"]
    with question_sets._lock:
        question_sets._conn.execute("UPDATE question_sets SET status='processing' WHERE id=?", (new_id,))
    assert _make_quiz(env).status_code == 409


def test_lesson_quiz_needs_enough_transcript(env, tmp_path):
    _lesson_quiz_env(env, tmp_path)
    _start(env)
    assert _make_quiz(env).status_code == 409  # mətn yoxdur
    _send(env, 0, b"qisa")
    _transcript(env)
    assert _make_quiz(env).status_code == 409
    assert _make_quiz(env, subject="yox").status_code in (400, 409)
    r = env["client"].post(f"/live/lessons/{env['lesson']['id']}/question-set",
                           json={"subject": "mentiq"}, headers=env["student_auth"])
    assert r.status_code == 403
