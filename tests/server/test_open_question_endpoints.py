"""Açıq suallar marşrutları (Faza 1, 2026-11-03)."""

import threading
import time

import pytest
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion
from pipeline.open_questions import OpenQuestion
from server.app import (
    app,
    get_open_question_generator,
    get_question_set_store,
    get_token_secret,
    get_user_store,
)
from server.auth import create_token
from server.question_set_store import QuestionSetStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


def _oq(text, kind="qisa"):
    return OpenQuestion(question=text, kind=kind, model_answer="Müsabiqə ilə.",
                        rubric=[{"criterion": "Müsabiqəni deyir", "points": 2},
                                {"criterion": "Orqanı deyir", "points": 1}], difficulty="orta")


def _wait(store, set_id, timeout=10.0):
    deadline = time.time() + timeout
    job = store.get_open_job(set_id)
    while job and job["status"] == "processing" and time.time() < deadline:
        time.sleep(0.02)
        job = store.get_open_job(set_id)
    return job


@pytest.fixture
def env():
    users = UserStore(":memory:")
    banks = QuestionSetStore(":memory:")
    seen = {}

    def fake_generator(source, count, kind, subject):
        seen.update(source=source, count=count, kind=kind, subject=subject)
        if seen.get("gate"):
            seen["gate"].wait(5)
        return [_oq("Qəbul necə aparılır?"), _oq("Müsabiqəni izah edin.", "esse")][:count]

    for dep, value in {get_user_store: users, get_question_set_store: banks, get_token_secret: _SECRET,
                       get_open_question_generator: fake_generator}.items():
        app.dependency_overrides[dep] = (lambda v: lambda: v)(value)
    course = users.courses.create("Kurs", "exam_prep", trial_days=30, seat_limit=30)
    teacher = users.create("t@x.az", "h", "Müəllim", course_id=course["id"])
    users.set_teacher(teacher["id"], True)
    student = users.create("s@x.az", "h", "Tələbə", course_id=course["id"])
    bank = banks.create("qanunvericilik", "Qulluq", "pdf", "/tmp/x.pdf", created_by=teacher["id"],
                        course_id=course["id"])
    banks.add_question(bank["id"], MCQQuestion(question="?", options=list("abcde"), correct_index=0,
                                               explanation="i"))
    banks.mark_ready(bank["id"])
    with TestClient(app) as client:
        yield {"client": client, "banks": banks, "bank": bank, "seen": seen,
               "auth": {"Authorization": f"Bearer {create_token(teacher['id'], secret=_SECRET)}"},
               "student": {"Authorization": f"Bearer {create_token(student['id'], secret=_SECRET)}"}}
    app.dependency_overrides.clear()


def _url(env):
    return f"/live/question-sets/{env['bank']['id']}/open-questions"


def test_generation_runs_in_background_and_appends(env):
    c = env["client"]
    assert c.get(_url(env), headers=env["auth"]).json() == {"status": "none", "error": None, "items": []}
    r = c.post(_url(env), json={"count": 2, "kind": "qarisiq"}, headers=env["auth"])
    assert r.status_code == 202 and r.json()["status"] == "processing"
    _wait(env["banks"], env["bank"]["id"])
    body = c.get(_url(env), headers=env["auth"]).json()
    assert body["status"] == "ready"
    assert [(i["kind"], i["max_points"]) for i in body["items"]] == [("qisa", 3), ("esse", 3)]
    assert env["seen"]["subject"] == "qanunvericilik" and env["seen"]["source"].kind == "pdf"

    c.post(_url(env), json={"count": 1}, headers=env["auth"])
    _wait(env["banks"], env["bank"]["id"])
    assert len(c.get(_url(env), headers=env["auth"]).json()["items"]) == 3   # köhnələr qalır


def test_edit_and_delete(env):
    c = env["client"]
    c.post(_url(env), json={"count": 1}, headers=env["auth"])
    _wait(env["banks"], env["bank"]["id"])
    item = c.get(_url(env), headers=env["auth"]).json()["items"][0]
    patch = {"kind": "esse", "question": "Müsabiqə prosedurunu izah edin.", "model_answer": "DİM keçirir.",
             "rubric": [{"criterion": "DİM-i deyir", "points": 4}], "difficulty": "çətin"}
    r = c.patch(f"/live/open-questions/{item['id']}", json=patch, headers=env["auth"])
    assert r.status_code == 200
    assert r.json()["max_points"] == 4 and r.json()["kind"] == "esse" and r.json()["difficulty"] == "çətin"

    bad = {**patch, "rubric": [{"criterion": "x", "points": 9}]}
    assert c.patch(f"/live/open-questions/{item['id']}", json=bad, headers=env["auth"]).status_code == 422

    assert c.delete(f"/live/open-questions/{item['id']}", headers=env["auth"]).status_code == 204
    assert c.get(_url(env), headers=env["auth"]).json()["items"] == []
    assert c.delete(f"/live/open-questions/{item['id']}", headers=env["auth"]).status_code == 404


def test_second_generation_while_running_is_409(env):
    env["seen"]["gate"] = threading.Event()
    assert env["client"].post(_url(env), json={}, headers=env["auth"]).status_code == 202
    assert env["client"].post(_url(env), json={}, headers=env["auth"]).status_code == 409
    env["seen"]["gate"].set()
    _wait(env["banks"], env["bank"]["id"])


def test_failure_keeps_old_questions(env):
    c = env["client"]
    c.post(_url(env), json={"count": 1}, headers=env["auth"])
    _wait(env["banks"], env["bank"]["id"])

    def broken(source, count, kind, subject):
        raise RuntimeError("Groq düşdü")

    app.dependency_overrides[get_open_question_generator] = lambda: broken
    c.post(_url(env), json={"count": 1}, headers=env["auth"])
    _wait(env["banks"], env["bank"]["id"])
    body = c.get(_url(env), headers=env["auth"]).json()
    assert body["status"] == "failed" and "Groq düşdü" in body["error"]
    assert len(body["items"]) == 1


def test_validation_student_and_unready_bank(env):
    c = env["client"]
    assert c.post(_url(env), json={"count": 16}, headers=env["auth"]).status_code == 422
    assert c.post(_url(env), json={"kind": "test"}, headers=env["auth"]).status_code == 422
    assert c.post(_url(env), json={}, headers=env["student"]).status_code == 403
    assert c.get(_url(env), headers=env["student"]).status_code == 403
    other = env["banks"].create("mentiq", "Hazırlanır", "pdf", "/tmp/y.pdf", created_by=1,
                                course_id=env["bank"]["course_id"])
    r = c.post(f"/live/question-sets/{other['id']}/open-questions", json={}, headers=env["auth"])
    assert r.status_code == 409


def test_interrupted_job_is_failed_on_restart(env):
    banks = env["banks"]
    banks.start_open_job(env["bank"]["id"])
    assert banks.fail_interrupted_open_jobs("restart") == 1
    assert banks.get_open_job(env["bank"]["id"])["status"] == "failed"
