"""Dərs xülasəsi endpointləri (Faza 3, 2026-10-30)."""

import time

import pytest
from fastapi.testclient import TestClient

from pipeline.summary import LessonSummary, SummaryError
from server.app import (
    app,
    get_chat_store,
    get_question_set_store,
    get_summarizer,
    get_summary_store,
    get_token_secret,
    get_user_store,
)
from server.auth import create_token
from server.chat_store import ChatStore
from server.question_set_store import QuestionSetStore
from server.summary_store import SummaryStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"
_CONTENT = {
    "title": "Konstitusiya", "intro": "Əsas qanun.",
    "key_points": ["Hakimiyyət üç qola bölünür.", "Xalq hakimiyyətin mənbəyidir."],
    "terms": [{"term": "Referendum", "definition": "Ümumxalq səsverməsi."}],
    "facts": ["1995-ci ildə qəbul edilib."],
    "self_check": [{"question": "Neçə qol?", "answer": "Üç."}],
}


def _fake_summarizer(source):
    return LessonSummary(**_CONTENT)


def _wait(summaries, summary_id, timeout=10.0):
    deadline = time.time() + timeout
    row = summaries.get(summary_id)
    while row["status"] == "processing" and time.time() < deadline:
        time.sleep(0.02)
        row = summaries.get(summary_id)
    return row


@pytest.fixture
def env():
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    question_sets = QuestionSetStore(":memory:")
    summaries = SummaryStore(":memory:")
    for dep, value in {
        get_user_store: users, get_chat_store: chats, get_question_set_store: question_sets,
        get_summary_store: summaries, get_token_secret: _SECRET,
    }.items():
        app.dependency_overrides[dep] = (lambda v: lambda: v)(value)
    app.dependency_overrides[get_summarizer] = lambda: _fake_summarizer

    course = users.courses.create("Kurs", "exam_prep", trial_days=30, seat_limit=30)
    teacher = users.create("t@x.az", "h", "Müəllim", course_id=course["id"])
    users.set_teacher(teacher["id"], True)
    teacher = users.get_by_id(teacher["id"])
    student = users.get_by_id(users.create("s@x.az", "h", "Tələbə", course_id=course["id"])["id"])
    outsider = users.get_by_id(users.create("o@x.az", "h", "Kənar", course_id=course["id"])["id"])

    chat = chats.create(kind="group", created_by=teacher["id"], name="Sinif 1", course_id=course["id"])
    chats.add_member(chat["id"], teacher["id"])
    chats.add_member(chat["id"], student["id"])
    qs = question_sets.create("mentiq", "Konstitusiya", "link", "https://x.az",
                              created_by=teacher["id"], course_id=course["id"])

    # `with`: bir event loop bütün test boyu yaşayır, fon task-ı (sual bankı
    # → xülasə) yarıda qalmır. Onsuz CI-da xülasə `processing`-də ilişirdi.
    with TestClient(app) as client:
        yield {"client": client, "summaries": summaries, "teacher": teacher, "student": student,
               "outsider": outsider, "chat": chat, "qs": qs}
    app.dependency_overrides.clear()


def _auth(user):
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


def _ready_summary(env):
    r = env["client"].post(f"/live/question-sets/{env['qs']['id']}/summary", headers=_auth(env["teacher"]))
    assert r.status_code == 202 and r.json()["status"] == "processing"
    _wait(env["summaries"], r.json()["id"])
    return r.json()["id"]


def test_teacher_generates_and_reads_summary(env):
    _ready_summary(env)
    r = env["client"].get(f"/live/question-sets/{env['qs']['id']}/summary", headers=_auth(env["teacher"]))
    body = r.json()
    assert body["status"] == "ready"
    assert body["title"] == "Konstitusiya"
    assert body["content"]["key_points"][0] == "Hakimiyyət üç qola bölünür."
    assert body["published_at"] is None


def test_students_cannot_use_teacher_routes(env):
    r = env["client"].post(f"/live/question-sets/{env['qs']['id']}/summary", headers=_auth(env["student"]))
    assert r.status_code == 403


def test_failure_is_stored(env):
    def boom(source):
        raise SummaryError("alınmadı")

    app.dependency_overrides[get_summarizer] = lambda: boom
    r = env["client"].post(f"/live/question-sets/{env['qs']['id']}/summary", headers=_auth(env["teacher"]))
    row = _wait(env["summaries"], r.json()["id"])
    assert row["status"] == "failed" and "alınmadı" in row["error"]


def test_unpublished_summary_is_invisible_to_student(env):
    summary_id = _ready_summary(env)
    assert env["client"].get("/me/summaries", headers=_auth(env["student"])).json() == []
    assert env["client"].get(f"/me/summaries/{summary_id}", headers=_auth(env["student"])).status_code == 404


def test_publish_then_student_reads_then_unpublish(env):
    summary_id = _ready_summary(env)
    r = env["client"].post(f"/live/summaries/{summary_id}/publish", json={"chat_id": env["chat"]["id"]},
                           headers=_auth(env["teacher"]))
    assert r.status_code == 200 and r.json()["chat_name"] == "Sinif 1"

    listed = env["client"].get("/me/summaries", headers=_auth(env["student"])).json()
    assert [s["id"] for s in listed] == [summary_id]
    one = env["client"].get(f"/me/summaries/{summary_id}", headers=_auth(env["student"]))
    assert one.status_code == 200 and one.json()["content"]["facts"] == ["1995-ci ildə qəbul edilib."]

    # Çatın üzvü olmayan eyni kursun tələbəsi görmür.
    assert env["client"].get(f"/me/summaries/{summary_id}", headers=_auth(env["outsider"])).status_code == 404

    env["client"].post(f"/live/summaries/{summary_id}/unpublish", headers=_auth(env["teacher"]))
    assert env["client"].get(f"/me/summaries/{summary_id}", headers=_auth(env["student"])).status_code == 404


def test_teacher_edits_summary(env):
    summary_id = _ready_summary(env)
    edited = {**_CONTENT, "intro": "Düzəldilmiş giriş."}
    r = env["client"].put(f"/live/summaries/{summary_id}", json=edited, headers=_auth(env["teacher"]))
    assert r.status_code == 200 and r.json()["content"]["intro"] == "Düzəldilmiş giriş."


def test_published_summary_cannot_be_regenerated(env):
    summary_id = _ready_summary(env)
    env["client"].post(f"/live/summaries/{summary_id}/publish", json={"chat_id": env["chat"]["id"]},
                       headers=_auth(env["teacher"]))
    r = env["client"].post(f"/live/question-sets/{env['qs']['id']}/summary", headers=_auth(env["teacher"]))
    assert r.status_code == 409


def test_failed_summary_can_be_regenerated_in_place(env):
    def boom(source):
        raise SummaryError("x")

    app.dependency_overrides[get_summarizer] = lambda: boom
    first = env["client"].post(f"/live/question-sets/{env['qs']['id']}/summary", headers=_auth(env["teacher"]))
    _wait(env["summaries"], first.json()["id"])
    app.dependency_overrides[get_summarizer] = lambda: _fake_summarizer
    second_id = _ready_summary(env)
    assert second_id == first.json()["id"]
    assert env["summaries"].get(second_id)["status"] == "ready"


def test_cannot_publish_to_chat_teacher_is_not_in(env):
    summary_id = _ready_summary(env)
    chats = app.dependency_overrides[get_chat_store]()
    other = chats.create(kind="group", created_by=env["student"]["id"], name="Başqa",
                         course_id=env["teacher"]["course_id"])
    r = env["client"].post(f"/live/summaries/{summary_id}/publish", json={"chat_id": other["id"]},
                           headers=_auth(env["teacher"]))
    assert r.status_code == 403


def test_missing_summary_returns_404(env):
    r = env["client"].get(f"/live/question-sets/{env['qs']['id']}/summary", headers=_auth(env["teacher"]))
    assert r.status_code == 404


def test_upload_with_make_summary_creates_summary_after_questions(env):
    from pipeline.models import MCQQuestion, PipelineResult
    from server.app import get_material_generator, get_upload_dir

    order = []

    def generator(source, question_count=10, **_options):
        order.append("questions")
        return PipelineResult(
            questions=[MCQQuestion(question=f"Sual {i}?", options=list("ABCDE"), correct_index=0,
                                   explanation="i") for i in range(3)],
            source=source, chunks_processed=1, chunks_failed=0, requested_question_count=question_count,
        )

    def summarizer(source):
        order.append("summary")
        return _fake_summarizer(source)

    app.dependency_overrides[get_material_generator] = lambda: generator
    app.dependency_overrides[get_summarizer] = lambda: summarizer
    app.dependency_overrides[get_upload_dir] = lambda: "/tmp"
    r = env["client"].post(
        "/live/question-sets",
        data={"subject": "mentiq", "title": "B", "kind": "link", "location": "https://x.az", "make_summary": "true"},
        headers=_auth(env["teacher"]),
    )
    assert r.status_code == 202
    summary = env["summaries"].get_for_question_set(r.json()["id"])
    summary = _wait(env["summaries"], summary["id"])
    assert summary["status"] == "ready"
    assert order == ["questions", "summary"]


def test_upload_without_make_summary_creates_none(env):
    from server.app import get_material_generator

    app.dependency_overrides[get_material_generator] = lambda: (
        lambda source, question_count=10, **_o: (_ for _ in ()).throw(RuntimeError("x"))
    )
    r = env["client"].post(
        "/live/question-sets",
        data={"subject": "mentiq", "title": "B", "kind": "link", "location": "https://x.az"},
        headers=_auth(env["teacher"]),
    )
    assert env["summaries"].get_for_question_set(r.json()["id"]) is None
