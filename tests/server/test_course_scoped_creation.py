"""Yaradılan çat və sual bankı yaradanın kursuna yazılır.

Bu olmasa Faza 4-ün kurs sərhədi yoxlaması hər yeni obyekti kurs #1-də
görərdi və ingilis kursunun bankları «başqa kursun» sayılardı.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion, PipelineResult
from server.app import (
    app,
    get_chat_store,
    get_friendship_store,
    get_material_generator,
    get_question_set_store,
    get_token_secret,
    get_upload_dir,
    get_user_store,
)
from server.auth import create_token
from server.chat_store import ChatStore
from server.friendship_store import FriendshipStore
from server.question_set_store import QuestionSetStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"
_NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _generator(source, question_count=10):
    return PipelineResult(
        questions=[
            MCQQuestion(question="Q?", options=["A", "B", "C", "D", "E"],
                        correct_index=0, explanation="izah")
        ],
        source=source, chunks_processed=1, chunks_failed=0,
        requested_question_count=question_count,
    )


@pytest.fixture
def env(tmp_path):
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    question_sets = QuestionSetStore(":memory:")
    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_chat_store] = lambda: chats
    app.dependency_overrides[get_friendship_store] = lambda: FriendshipStore(":memory:")
    app.dependency_overrides[get_question_set_store] = lambda: question_sets
    app.dependency_overrides[get_token_secret] = lambda: _SECRET
    app.dependency_overrides[get_material_generator] = lambda: _generator
    app.dependency_overrides[get_upload_dir] = lambda: str(tmp_path)

    # Uzaq gələcəkdə bitən sınaq — Faza 2 qapısı bu testləri bağlamasın.
    course = users.courses.create("English", "english", trial_days=3650, seat_limit=30)
    teacher = users.create("t@example.az", "h", "Müəllim", course_id=course["id"])
    users.set_teacher(teacher["id"], True)
    yield {
        "client": TestClient(app),
        "chats": chats,
        "question_sets": question_sets,
        "teacher": users.get_by_id(teacher["id"]),
        "course": course,
    }
    app.dependency_overrides.clear()


def _auth(user):
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


def test_group_chat_gets_creator_course(env):
    r = env["client"].post(
        "/chats", json={"kind": "group", "name": "Sinif"}, headers=_auth(env["teacher"])
    )
    assert r.status_code == 201
    assert env["chats"].get(r.json()["id"])["course_id"] == env["course"]["id"]


def test_question_set_gets_creator_course(env):
    r = env["client"].post(
        "/live/question-sets",
        data={"subject": "mentiq", "title": "Unit 1", "kind": "link", "location": "https://x.az"},
        headers=_auth(env["teacher"]),
    )
    assert r.status_code == 202
    assert env["question_sets"].get(r.json()["id"])["course_id"] == env["course"]["id"]
