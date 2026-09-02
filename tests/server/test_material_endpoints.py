import pytest
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion, PipelineResult
from server.app import (
    app,
    get_chat_store,
    get_connection_manager,
    get_material_generator,
    get_material_store,
    get_message_store,
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
from server.question_store import QuestionStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


def _fake_generator_success(source, questions_per_chunk=3):
    return PipelineResult(
        questions=[
            MCQQuestion(
                question=f"Sual {i}?",
                options=["A", "B", "C", "D", "E"],
                correct_index=0,
                explanation="izah",
            )
            for i in range(3)
        ],
        source=source,
        chunks_processed=1,
        chunks_failed=0,
    )


@pytest.fixture
def env(tmp_path):
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    materials = MaterialStore(":memory:")
    questions = QuestionStore(":memory:")
    messages = MessageStore(":memory:")
    manager = ConnectionManager()

    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_chat_store] = lambda: chats
    app.dependency_overrides[get_material_store] = lambda: materials
    app.dependency_overrides[get_question_store] = lambda: questions
    app.dependency_overrides[get_message_store] = lambda: messages
    app.dependency_overrides[get_connection_manager] = lambda: manager
    app.dependency_overrides[get_token_secret] = lambda: _SECRET
    app.dependency_overrides[get_material_generator] = lambda: _fake_generator_success
    app.dependency_overrides[get_upload_dir] = lambda: str(tmp_path)

    client = TestClient(app)

    member = users.create("member@example.com", "hash", "Üzv")
    other = users.create("other@example.com", "hash", "Başqası")
    chat = chats.create(kind="group", created_by=member["id"], name="Qrup")
    chats.add_member(chat["id"], member["id"])

    yield {
        "client": client,
        "chats": chats,
        "materials": materials,
        "questions": questions,
        "messages": messages,
        "chat_id": chat["id"],
        "member": member,
        "other": other,
    }
    app.dependency_overrides.clear()


def _auth(user) -> dict:
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


class TestUploadValidation:
    def test_requires_auth(self, env):
        r = env["client"].post(
            f"/chats/{env['chat_id']}/materials",
            data={"kind": "link", "location": "https://x.az"},
        )
        assert r.status_code == 401

    def test_non_member_gets_403(self, env):
        r = env["client"].post(
            f"/chats/{env['chat_id']}/materials",
            data={"kind": "link", "location": "https://x.az"},
            headers=_auth(env["other"]),
        )
        assert r.status_code == 403

    def test_unknown_chat_returns_404(self, env):
        r = env["client"].post(
            "/chats/9999/materials",
            data={"kind": "link", "location": "https://x.az"},
            headers=_auth(env["member"]),
        )
        assert r.status_code == 404

    def test_link_without_location_returns_400(self, env):
        r = env["client"].post(
            f"/chats/{env['chat_id']}/materials",
            data={"kind": "link"},
            headers=_auth(env["member"]),
        )
        assert r.status_code == 400

    def test_pdf_without_file_returns_400(self, env):
        r = env["client"].post(
            f"/chats/{env['chat_id']}/materials",
            data={"kind": "pdf"},
            headers=_auth(env["member"]),
        )
        assert r.status_code == 400

    def test_oversized_file_returns_413(self, env, monkeypatch):
        monkeypatch.setattr("server.app.MAX_UPLOAD_BYTES", 10)
        r = env["client"].post(
            f"/chats/{env['chat_id']}/materials",
            data={"kind": "pdf"},
            files={"file": ("big.pdf", b"x" * 1000, "application/pdf")},
            headers=_auth(env["member"]),
        )
        assert r.status_code == 413


class TestUploadAccepted:
    def test_link_upload_returns_202_processing(self, env):
        r = env["client"].post(
            f"/chats/{env['chat_id']}/materials",
            data={"kind": "link", "location": "https://x.az", "label": "Etiket"},
            headers=_auth(env["member"]),
        )
        assert r.status_code == 202
        body = r.json()
        assert body["status"] == "processing"
        assert body["kind"] == "link"
        assert body["label"] == "Etiket"

    def test_pdf_upload_with_file_returns_202(self, env):
        r = env["client"].post(
            f"/chats/{env['chat_id']}/materials",
            data={"kind": "pdf"},
            files={"file": ("material.pdf", b"pdf-content", "application/pdf")},
            headers=_auth(env["member"]),
        )
        assert r.status_code == 202
        assert r.json()["status"] == "processing"


class TestListMaterials:
    def test_requires_auth(self, env):
        r = env["client"].get(f"/chats/{env['chat_id']}/materials")
        assert r.status_code == 401

    def test_non_member_gets_403(self, env):
        r = env["client"].get(f"/chats/{env['chat_id']}/materials", headers=_auth(env["other"]))
        assert r.status_code == 403

    def test_unknown_chat_returns_404(self, env):
        r = env["client"].get("/chats/9999/materials", headers=_auth(env["member"]))
        assert r.status_code == 404

    def test_lists_uploaded_materials(self, env):
        env["materials"].create(
            chat_id=env["chat_id"], uploaded_by=env["member"]["id"], kind="link", location="https://x.az"
        )
        r = env["client"].get(f"/chats/{env['chat_id']}/materials", headers=_auth(env["member"]))
        assert r.status_code == 200
        assert len(r.json()) == 1
