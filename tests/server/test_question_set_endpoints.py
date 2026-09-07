import time

import pytest
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion, PipelineResult
from pipeline.pipeline import PipelineError
from server.app import (
    app,
    get_material_generator,
    get_question_set_store,
    get_token_secret,
    get_upload_dir,
    get_user_store,
)
from server.auth import create_token
from server.question_set_store import QuestionSetStore
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


def _fake_generator_failure(source, questions_per_chunk=3):
    raise PipelineError("real test üçün süni xəta")


def _wait_until_not_processing(question_sets, question_set_id, timeout=2.0):
    deadline = time.time() + timeout
    qs = question_sets.get(question_set_id)
    while qs["status"] == "processing" and time.time() < deadline:
        time.sleep(0.02)
        qs = question_sets.get(question_set_id)
    return qs


@pytest.fixture
def env(tmp_path):
    users = UserStore(":memory:")
    question_sets = QuestionSetStore(":memory:")

    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_question_set_store] = lambda: question_sets
    app.dependency_overrides[get_token_secret] = lambda: _SECRET
    app.dependency_overrides[get_material_generator] = lambda: _fake_generator_success
    app.dependency_overrides[get_upload_dir] = lambda: str(tmp_path)

    client = TestClient(app)
    teacher = users.create("teacher@masternr1.az", "hash", "Müəllim")

    yield {"client": client, "question_sets": question_sets, "teacher": teacher}
    app.dependency_overrides.clear()


def _auth(user) -> dict:
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


class TestCreateValidation:
    def test_requires_auth(self, env):
        r = env["client"].post(
            "/live/question-sets",
            data={"subject": "mentiq", "title": "A", "kind": "link", "location": "https://x.az"},
        )
        assert r.status_code == 401

    def test_unknown_subject_returns_400(self, env):
        r = env["client"].post(
            "/live/question-sets",
            data={"subject": "riyaziyyat", "title": "A", "kind": "link", "location": "https://x.az"},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 400

    def test_unknown_kind_returns_400(self, env):
        r = env["client"].post(
            "/live/question-sets",
            data={"subject": "mentiq", "title": "A", "kind": "video", "location": "https://x.az"},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 400

    def test_link_without_location_returns_400(self, env):
        r = env["client"].post(
            "/live/question-sets",
            data={"subject": "mentiq", "title": "A", "kind": "link"},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 400

    def test_pdf_without_file_returns_400(self, env):
        r = env["client"].post(
            "/live/question-sets",
            data={"subject": "mentiq", "title": "A", "kind": "pdf"},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 400

    def test_oversized_file_returns_413(self, env, monkeypatch):
        monkeypatch.setattr("server.app.MAX_UPLOAD_BYTES", 10)
        r = env["client"].post(
            "/live/question-sets",
            data={"subject": "mentiq", "title": "A", "kind": "pdf"},
            files={"file": ("big.pdf", b"x" * 1000, "application/pdf")},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 413


class TestCreateAccepted:
    def test_link_returns_202_processing(self, env):
        r = env["client"].post(
            "/live/question-sets",
            data={"subject": "mentiq", "title": "Silloqizmlər", "kind": "link", "location": "https://x.az"},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 202
        body = r.json()
        assert body["status"] == "processing"
        assert body["subject"] == "mentiq"
        assert body["title"] == "Silloqizmlər"
        assert body["question_count"] == 0

    def test_pdf_with_file_returns_202(self, env):
        r = env["client"].post(
            "/live/question-sets",
            data={"subject": "qanunvericilik", "title": "Konstitusiya", "kind": "pdf"},
            files={"file": ("material.pdf", b"pdf-content", "application/pdf")},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 202
        assert r.json()["status"] == "processing"


class TestGetAndList:
    def test_get_requires_auth(self, env):
        r = env["client"].get("/live/question-sets/1")
        assert r.status_code == 401

    def test_get_unknown_returns_404(self, env):
        r = env["client"].get("/live/question-sets/999", headers=_auth(env["teacher"]))
        assert r.status_code == 404

    def test_list_requires_auth(self, env):
        r = env["client"].get("/live/question-sets")
        assert r.status_code == 401

    def test_list_returns_created_sets_with_question_count(self, env):
        env["client"].post(
            "/live/question-sets",
            data={"subject": "mentiq", "title": "A", "kind": "link", "location": "https://x.az"},
            headers=_auth(env["teacher"]),
        )
        qs = _wait_until_not_processing(env["question_sets"], env["question_sets"].list_all()[0]["id"])

        r = env["client"].get("/live/question-sets", headers=_auth(env["teacher"]))
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["status"] == "ready"
        assert body[0]["question_count"] == 3


class TestBackgroundProcessing:
    def test_successful_processing_creates_questions(self, env):
        r = env["client"].post(
            "/live/question-sets",
            data={"subject": "informatika", "title": "Alqoritmlər", "kind": "link", "location": "https://x.az"},
            headers=_auth(env["teacher"]),
        )
        qs_id = r.json()["id"]

        qs = _wait_until_not_processing(env["question_sets"], qs_id)

        assert qs["status"] == "ready"
        assert env["question_sets"].count_questions(qs_id) == 3

        detail = env["client"].get(f"/live/question-sets/{qs_id}", headers=_auth(env["teacher"]))
        assert detail.json()["question_count"] == 3
        assert detail.json()["error"] is None

    def test_failed_processing_marks_failed_with_error(self, env):
        app.dependency_overrides[get_material_generator] = lambda: _fake_generator_failure

        r = env["client"].post(
            "/live/question-sets",
            data={"subject": "mentiq", "title": "A", "kind": "link", "location": "https://x.az"},
            headers=_auth(env["teacher"]),
        )
        qs_id = r.json()["id"]

        qs = _wait_until_not_processing(env["question_sets"], qs_id)

        assert qs["status"] == "failed"
        assert "süni xəta" in qs["error"]
        assert env["question_sets"].count_questions(qs_id) == 0
