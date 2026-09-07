import pytest
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion
from server.app import app, get_question_set_store, get_token_secret, get_user_store
from server.auth import create_token
from server.question_set_store import QuestionSetStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


@pytest.fixture
def env():
    users = UserStore(":memory:")
    question_sets = QuestionSetStore(":memory:")

    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_question_set_store] = lambda: question_sets
    app.dependency_overrides[get_token_secret] = lambda: _SECRET

    client = TestClient(app)
    teacher = users.create("teacher@masternr1.az", "hash", "Müəllim")
    users.set_teacher(teacher["id"], True)
    teacher = users.get_by_id(teacher["id"])
    student = users.create("telebe@masternr1.az", "hash", "Tələbə")

    qs = question_sets.create(
        subject="mentiq", title="Silloqizmlər", material_kind="link",
        material_location="https://x.az", created_by=teacher["id"],
    )
    question = question_sets.add_question(
        qs["id"],
        MCQQuestion(question="Köhnə sual?", options=["A", "B", "C", "D", "E"], correct_index=0, explanation="izah"),
    )

    yield {
        "client": client, "question_sets": question_sets,
        "teacher": teacher, "student": student, "qs": qs, "question": question,
    }
    app.dependency_overrides.clear()


def _auth(user) -> dict:
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


class TestListQuestions:
    def test_requires_auth(self, env):
        assert env["client"].get(f"/live/question-sets/{env['qs']['id']}/questions").status_code == 401

    def test_non_teacher_gets_403(self, env):
        r = env["client"].get(
            f"/live/question-sets/{env['qs']['id']}/questions", headers=_auth(env["student"])
        )
        assert r.status_code == 403

    def test_unknown_question_set_returns_404(self, env):
        r = env["client"].get("/live/question-sets/999/questions", headers=_auth(env["teacher"]))
        assert r.status_code == 404

    def test_returns_full_content_including_answer(self, env):
        r = env["client"].get(
            f"/live/question-sets/{env['qs']['id']}/questions", headers=_auth(env["teacher"])
        )
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["question"] == "Köhnə sual?"
        assert rows[0]["correct_index"] == 0
        assert rows[0]["explanation"] == "izah"


class TestUpdateQuestion:
    _payload = {
        "question": "Yeni sual?",
        "options": ["X", "Y", "Z", "W", "V"],
        "correct_index": 2,
        "explanation": "yeni izah",
    }

    def test_requires_auth(self, env):
        r = env["client"].patch(f"/live/questions/{env['question']['id']}", json=self._payload)
        assert r.status_code == 401

    def test_non_teacher_gets_403(self, env):
        r = env["client"].patch(
            f"/live/questions/{env['question']['id']}", json=self._payload, headers=_auth(env["student"])
        )
        assert r.status_code == 403

    def test_unknown_question_returns_404(self, env):
        r = env["client"].patch("/live/questions/999", json=self._payload, headers=_auth(env["teacher"]))
        assert r.status_code == 404

    def test_wrong_options_count_returns_422(self, env):
        bad = {**self._payload, "options": ["X", "Y"]}
        r = env["client"].patch(
            f"/live/questions/{env['question']['id']}", json=bad, headers=_auth(env["teacher"])
        )
        assert r.status_code == 422

    def test_out_of_range_correct_index_returns_422(self, env):
        bad = {**self._payload, "correct_index": 9}
        r = env["client"].patch(
            f"/live/questions/{env['question']['id']}", json=bad, headers=_auth(env["teacher"])
        )
        assert r.status_code == 422

    def test_teacher_updates_question(self, env):
        r = env["client"].patch(
            f"/live/questions/{env['question']['id']}", json=self._payload, headers=_auth(env["teacher"])
        )
        assert r.status_code == 200
        body = r.json()
        assert body["question"] == "Yeni sual?"
        assert body["correct_index"] == 2
        assert env["question_sets"].get_question(env["question"]["id"])["question"] == "Yeni sual?"


class TestDeleteQuestion:
    def test_requires_auth(self, env):
        assert env["client"].delete(f"/live/questions/{env['question']['id']}").status_code == 401

    def test_non_teacher_gets_403(self, env):
        r = env["client"].delete(f"/live/questions/{env['question']['id']}", headers=_auth(env["student"]))
        assert r.status_code == 403

    def test_unknown_question_returns_404(self, env):
        r = env["client"].delete("/live/questions/999", headers=_auth(env["teacher"]))
        assert r.status_code == 404

    def test_teacher_deletes_question(self, env):
        r = env["client"].delete(f"/live/questions/{env['question']['id']}", headers=_auth(env["teacher"]))
        assert r.status_code == 204
        assert env["question_sets"].get_question(env["question"]["id"]) is None
