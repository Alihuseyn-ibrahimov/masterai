"""Gündəlik yükləmə limiti — spec 2026-09-29 §4.5.

Hər yükləmə (çat materialı VƏ sual bankı) AI generasiyasını işə salır,
yəni xərcdir. Limit kurs üzrədir (defolt tələbə 5, müəllim 30), ikisi
BİRLİKDƏ sayılır, gün Bakı vaxtı ilə (UTC+4) başlayır. Yeni sayğac
yazılmır — mövcud `materials` və `question_sets` cədvəllərindən sayılır.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion, PipelineResult
from server.app import (
    _baku_day_start_utc,
    app,
    get_chat_store,
    get_connection_manager,
    get_material_generator,
    get_material_store,
    get_message_store,
    get_question_set_store,
    get_question_store,
    get_token_secret,
    get_upload_dir,
    get_user_store,
)
from server.auth import create_token
from server.chat_store import ChatStore
from server.connection_manager import ConnectionManager
from server.material_store import MaterialStore
from server.message_store import MessageStore
from server.question_set_store import QuestionSetStore
from server.question_store import QuestionStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


def _generator(source, question_count=10):
    return PipelineResult(
        questions=[MCQQuestion(question="Q?", options=["A", "B", "C", "D", "E"],
                               correct_index=0, explanation="izah")],
        source=source, chunks_processed=1, chunks_failed=0,
        requested_question_count=question_count,
    )


class TestBakuDay:
    def test_before_midnight_baku(self):
        # 19:59 UTC = 23:59 Bakı — hələ 1 oktyabr günüdür
        now = datetime(2026, 10, 1, 19, 59, tzinfo=timezone.utc)
        assert _baku_day_start_utc(now) == datetime(2026, 9, 30, 20, 0, tzinfo=timezone.utc)

    def test_after_midnight_baku(self):
        # 20:00 UTC = 00:00 Bakı — yeni gün (2 oktyabr)
        now = datetime(2026, 10, 1, 20, 0, tzinfo=timezone.utc)
        assert _baku_day_start_utc(now) == datetime(2026, 10, 1, 20, 0, tzinfo=timezone.utc)


class TestStoreCounts:
    def test_materials_counted_since(self):
        store = MaterialStore(":memory:")
        old = store.create(1, 7, "link", "https://x")
        store.create(1, 7, "link", "https://y")
        store.create(1, 8, "link", "https://z")  # başqa istifadəçi
        store._conn.execute("UPDATE materials SET created_at = ? WHERE id = ?",
                            ("2026-01-01T00:00:00+00:00", old["id"]))
        store._conn.commit()
        assert store.count_by_uploader_since(7, "2026-06-01T00:00:00+00:00") == 1

    def test_question_sets_counted_since(self):
        store = QuestionSetStore(":memory:")
        old = store.create("mentiq", "A", "link", "https://x", created_by=7)
        store.create("mentiq", "B", "link", "https://x", created_by=7)
        store._conn.execute("UPDATE question_sets SET created_at = ? WHERE id = ?",
                            ("2026-01-01T00:00:00+00:00", old["id"]))
        store._conn.commit()
        assert store.count_by_creator_since(7, "2026-06-01T00:00:00+00:00") == 1


@pytest.fixture
def env(tmp_path):
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    materials = MaterialStore(":memory:")
    question_sets = QuestionSetStore(":memory:")
    overrides = {
        get_user_store: users, get_chat_store: chats, get_material_store: materials,
        get_question_set_store: question_sets, get_message_store: MessageStore(":memory:"),
        get_question_store: QuestionStore(":memory:"), get_connection_manager: ConnectionManager(),
        get_material_generator: _generator, get_upload_dir: str(tmp_path), get_token_secret: _SECRET,
    }

    def _const(value):
        return lambda: value

    for dep, value in overrides.items():
        app.dependency_overrides[dep] = _const(value)

    course = users.courses.create("English", "english", trial_days=30, seat_limit=30)
    teacher = users.create("t@x.az", "h", "T", course_id=course["id"])
    users.set_teacher(teacher["id"], True)
    student = users.create("s@x.az", "h", "S", course_id=course["id"])
    chat = chats.create(kind="group", created_by=teacher["id"], name="Sinif", course_id=course["id"])
    chats.add_member(chat["id"], teacher["id"])
    chats.add_member(chat["id"], student["id"])
    yield {
        "client": TestClient(app), "users": users, "materials": materials,
        "question_sets": question_sets, "course": course, "chat": chat,
        "teacher": users.get_by_id(teacher["id"]), "student": users.get_by_id(student["id"]),
    }
    app.dependency_overrides.clear()


def _auth(user):
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


def _upload_material(env, user):
    return env["client"].post(
        f"/chats/{env['chat']['id']}/materials",
        data={"kind": "link", "location": "https://x.az", "question_count": 3},
        headers=_auth(user),
    )


def _create_bank(env, user):
    return env["client"].post(
        "/live/question-sets",
        data={"subject": "mentiq", "title": "Unit", "kind": "link", "location": "https://x.az"},
        headers=_auth(user),
    )


class TestQuota:
    def test_student_default_limit_is_five(self, env):
        for _ in range(5):
            assert _upload_material(env, env["student"]).status_code == 202
        r = _upload_material(env, env["student"])
        assert r.status_code == 429
        assert "5" in r.json()["detail"]
        assert len(env["materials"].list_by_chat(env["chat"]["id"])) == 5  # 6-cı yazılmayıb

    def test_teacher_limit_counts_materials_and_banks_together(self, env):
        env["users"].courses.set_upload_limits(env["course"]["id"], student=5, teacher=2)
        assert _upload_material(env, env["teacher"]).status_code == 202
        assert _create_bank(env, env["teacher"]).status_code == 202
        assert _create_bank(env, env["teacher"]).status_code == 429
        assert _upload_material(env, env["teacher"]).status_code == 429

    def test_limits_are_per_user(self, env):
        env["users"].courses.set_upload_limits(env["course"]["id"], student=1, teacher=30)
        assert _upload_material(env, env["student"]).status_code == 202
        assert _upload_material(env, env["student"]).status_code == 429
        assert _upload_material(env, env["teacher"]).status_code == 202

    def test_yesterdays_uploads_do_not_count(self, env):
        env["users"].courses.set_upload_limits(env["course"]["id"], student=1, teacher=30)
        _upload_material(env, env["student"])
        env["materials"]._conn.execute(
            "UPDATE materials SET created_at = '2020-01-01T00:00:00+00:00'")
        env["materials"]._conn.commit()
        assert _upload_material(env, env["student"]).status_code == 202

    def test_platform_owner_exempt(self, env):
        env["users"].courses.set_upload_limits(env["course"]["id"], student=5, teacher=1)
        env["users"].set_platform_owner(env["teacher"]["id"], True)
        for _ in range(3):
            assert _upload_material(env, env["teacher"]).status_code == 202
