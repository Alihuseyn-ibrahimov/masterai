"""Müəllim MCP serveri (gün 11): alətlər real FastAPI tətbiqinə qarşı."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from server.app import (
    app, get_chat_store, get_lesson_store, get_question_set_store, get_token_secret, get_user_store,
)
from server.auth import hash_password
from server.chat_store import ChatStore
from server.lesson_store import LessonStore
from server.question_set_store import QuestionSetStore
from server.user_store import UserStore
from pipeline.models import MCQQuestion
from teacher_mcp.server import MasterAIClient, MasterAIError, build_server

_SECRET = "test-secret-key-32-chars-minimum!!"


@pytest.fixture
def env():
    users, chats, lessons, banks = UserStore(":memory:"), ChatStore(":memory:"), LessonStore(":memory:"), \
        QuestionSetStore(":memory:")
    for dep, value in {get_user_store: users, get_chat_store: chats, get_lesson_store: lessons,
                       get_question_set_store: banks, get_token_secret: _SECRET}.items():
        app.dependency_overrides[dep] = (lambda v: lambda: v)(value)
    course = users.courses.create("Kurs", "exam_prep", trial_days=30, seat_limit=30)
    teacher = users.create("t@x.az", hash_password("sirr-12345"), "Müəllim", course_id=course["id"])
    users.set_teacher(teacher["id"], True)
    student = users.create("s@x.az", hash_password("sirr-12345"), "Əli", course_id=course["id"])
    chat = chats.create(kind="group", created_by=teacher["id"], name="Sinif 1", course_id=course["id"])
    for member in (teacher, student):
        chats.add_member(chat["id"], member["id"])
    bank = banks.create("qanunvericilik", "Konstitusiya", "text", "/tmp/x.txt", created_by=teacher["id"],
                        course_id=course["id"])
    banks.add_question(bank["id"], MCQQuestion(question="Nə vaxt?", options=["1991", "1993", "1995", "1998", "2002"],
                                               correct_index=2, explanation="1995."))
    banks.mark_ready(bank["id"])
    http = TestClient(app)
    client = MasterAIClient("http://testserver", email="t@x.az", password="sirr-12345", http=http)
    yield {"mcp": build_server(client), "chat": chat, "bank": bank, "lessons": lessons, "http": http}
    app.dependency_overrides.clear()


def call(mcp, name, **args):
    result = asyncio.run(mcp.call_tool(name, args))
    blocks = result[0] if isinstance(result, tuple) else result
    return json.loads(blocks[0].text) if len(blocks) == 1 else [json.loads(b.text) for b in blocks]


def test_tools_are_registered():
    tools = asyncio.run(build_server(MasterAIClient("http://x", token="t")).list_tools())
    assert {t.name for t in tools} >= {"list_classes", "schedule_lesson", "quiz_from_lesson", "review_bank",
                                       "lesson_attendance", "assign_homework"}


def test_login_and_list_classes(env):
    assert call(env["mcp"], "list_classes") == {"id": env["chat"]["id"], "name": "Sinif 1",
                                                "invite_code": env["chat"]["invite_code"]}


def test_schedule_and_list_lessons_and_attendance(env):
    lesson = call(env["mcp"], "schedule_lesson", chat_id=env["chat"]["id"], title="Konstitusiya",
                  starts_at="2026-11-03T10:00:00+04:00", mode="offline")
    assert lesson["title"] == "Konstitusiya" and lesson["starts_at"].startswith("2026-11-03T06:00")
    listed = call(env["mcp"], "list_lessons", chat_id=env["chat"]["id"])
    assert listed["id"] == lesson["id"]
    attendance = call(env["mcp"], "lesson_attendance", lesson_id=lesson["id"])
    assert attendance == {"present": [], "absent": ["Əli"]}


def test_bank_tools(env):
    bank = call(env["mcp"], "list_question_banks")
    assert bank["subject"] == "Qanunvericilik" and bank["status"] == "ready"
    question = call(env["mcp"], "bank_questions", question_set_id=env["bank"]["id"])
    assert question["correct"] == "1995"
    assert call(env["mcp"], "review_bank", question_set_id=env["bank"]["id"])["status"] == "none"


def test_bad_input_and_api_errors_are_readable(env):
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError, match="ISO 8601"):
        call(env["mcp"], "schedule_lesson", chat_id=1, title="x", starts_at="sabah")
    with pytest.raises(ToolError, match="Naməlum fənn"):
        call(env["mcp"], "quiz_from_lesson", lesson_id=1, subject="fizika")
    with pytest.raises(ToolError, match="404"):
        call(env["mcp"], "lesson_transcript", lesson_id=999)


def test_student_cannot_do_teacher_things(env):
    student = MasterAIClient("http://testserver", email="s@x.az", password="sirr-12345", http=env["http"])
    with pytest.raises(MasterAIError, match="403"):
        student.call("GET", "/live/question-sets")


def test_missing_credentials():
    with pytest.raises(MasterAIError, match="MASTERAI_TOKEN"):
        MasterAIClient("http://x").call("GET", "/chats")
