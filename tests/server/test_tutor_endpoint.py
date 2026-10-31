"""AI tutor marşrutu (gün 8): mənbələrin sərhədi və limit."""

import pytest
from fastapi.testclient import TestClient

from pipeline.rag import TutorAnswer
from server.app import (
    app,
    get_chat_store,
    get_lesson_store,
    get_question_set_store,
    get_summary_store,
    get_token_secret,
    get_tutor,
    get_tutor_rate_limiter,
    get_user_store,
)
from server.auth import create_token
from server.chat_store import ChatStore
from server.lesson_store import LessonStore
from server.question_set_store import QuestionSetStore
from server.rate_limit import RateLimiter
from server.summary_store import SummaryStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"
_SUMMARY = ('{"title": "Konstitusiya", "intro": "Əsas qanun.", "key_points": ["1995-ci ildə qəbul edilib."], '
            '"terms": [{"term": "Referendum", "definition": "Ümumxalq səsverməsi"}], "facts": [], "self_check": []}')


@pytest.fixture
def env():
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    lessons = LessonStore(":memory:")
    banks = QuestionSetStore(":memory:")
    summaries = SummaryStore(":memory:")
    calls = []

    def fake_tutor(question, docs):
        calls.append((question, docs))
        return TutorAnswer(answer="Cavab [1].", found=True, sources=docs[:1])

    limiter = RateLimiter(3, 600)
    for dep, value in {get_user_store: users, get_chat_store: chats, get_lesson_store: lessons,
                       get_question_set_store: banks, get_summary_store: summaries, get_token_secret: _SECRET,
                       get_tutor: fake_tutor, get_tutor_rate_limiter: limiter}.items():
        app.dependency_overrides[dep] = (lambda v: lambda: v)(value)
    course = users.courses.create("Kurs", "exam_prep", trial_days=30, seat_limit=30)
    teacher = users.create("t@x.az", "h", "Müəllim", course_id=course["id"])
    users.set_teacher(teacher["id"], True)
    ali = users.create("a@x.az", "h", "Əli", course_id=course["id"])
    chat = chats.create(kind="group", created_by=teacher["id"], name="Sinif 1", course_id=course["id"])
    other = chats.create(kind="group", created_by=teacher["id"], name="Sinif 2", course_id=course["id"])
    for member in (teacher, ali):
        chats.add_member(chat["id"], member["id"])
    chats.add_member(other["id"], teacher["id"])

    def lesson(chat_id, title, status="ended", text=None):
        row = lessons.create(chat_id, course_id=course["id"], created_by=teacher["id"], title=title,
                             description="", starts_at="2026-11-03T06:00:00+00:00", duration_min=90, mode="online")
        lessons.set_status(row["id"], status)
        if text:
            lessons.start_segment(row["id"], 0)
            lessons.finish_segment(row["id"], 0, text=text)
        return row

    yield {"client": TestClient(app), "calls": calls, "lesson": lesson, "chat": chat, "other": other,
           "summaries": summaries, "banks": banks, "lessons": lessons, "course": course, "teacher": teacher,
           "auth": {"Authorization": f"Bearer {create_token(ali['id'], secret=_SECRET)}"}}
    app.dependency_overrides.clear()


def _ask(env, **body):
    return env["client"].post("/me/tutor/ask", json={"question": "Konstitusiya nədir?", **body}, headers=env["auth"])


def test_uses_only_own_class_material_and_published_summaries(env):
    mine = env["lesson"](env["chat"]["id"], "Konstitusiya", text="Konstitusiya 1995-ci ildə qəbul edilib.")
    env["lesson"](env["other"]["id"], "Başqa sinif", text="Gizli mətn")
    env["lesson"](env["chat"]["id"], "Gələcək", status="scheduled", text="Hələ keçilməyib")
    bank = env["banks"].create("qanunvericilik", "Konstitusiya", "text", "/x", created_by=env["teacher"]["id"],
                               course_id=env["course"]["id"])
    published = env["summaries"].start(bank["id"], created_by=env["teacher"]["id"], course_id=env["course"]["id"])
    env["summaries"].mark_ready(published["id"], _SUMMARY)
    env["summaries"].publish(published["id"], env["chat"]["id"])
    bank2 = env["banks"].create("qanunvericilik", "Qaralama", "text", "/y", created_by=env["teacher"]["id"],
                                course_id=env["course"]["id"])
    draft = env["summaries"].start(bank2["id"], created_by=env["teacher"]["id"], course_id=env["course"]["id"])
    env["summaries"].mark_ready(draft["id"], _SUMMARY)  # dərc olunmayıb

    r = _ask(env)
    assert r.status_code == 200, r.text
    docs = env["calls"][0][1]
    assert sorted(d.key for d in docs) == sorted([f"lesson:{mine['id']}", f"summary:{published['id']}"])
    summary_doc = next(d for d in docs if d.key.startswith("summary"))
    assert "Referendum: Ümumxalq səsverməsi" in summary_doc.text
    assert r.json()["sources"] == [{"title": "Dərs: Konstitusiya", "lesson_id": mine["id"], "summary_id": None}]


def test_lesson_scope_and_no_material(env):
    empty = env["lesson"](env["chat"]["id"], "Səssiz dərs")
    r = _ask(env, lesson_id=empty["id"])
    assert r.json() == {"found": False, "answer": "", "sources": [], "no_material": True}
    assert env["calls"] == []
    foreign = env["lesson"](env["other"]["id"], "Başqa", text="x")
    assert _ask(env, lesson_id=foreign["id"]).status_code == 404


def test_rate_limited_per_user(env):
    env["lesson"](env["chat"]["id"], "Konstitusiya", text="Konstitusiya")
    codes = [_ask(env).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


def test_question_length_validated(env):
    assert _ask(env, question="x").status_code == 422
    assert _ask(env, question="a" * 501).status_code == 422
