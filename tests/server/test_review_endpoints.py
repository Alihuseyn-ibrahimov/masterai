"""AI yoxlama komandası marşrutları (gün 10)."""

import threading
import time

import pytest
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion
from pipeline.review_team import Issue, QuestionReview
from server.app import app, get_question_set_store, get_reviewer, get_token_secret, get_user_store
from server.auth import create_token
from server.question_set_store import QuestionSetStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"
FIX = MCQQuestion(question="Milli Məclis neçə deputatdandır?", options=["100", "101", "120", "125", "150"],
                  correct_index=3, explanation="125 [1].")


def q(text, correct=0):
    return MCQQuestion(question=text, options=["a", "b", "c", "d", "e"], correct_index=correct, explanation="i")


def _wait(store, set_id, timeout=10.0):
    deadline = time.time() + timeout
    review = store.get_review(set_id)
    while review and review["status"] == "processing" and time.time() < deadline:
        time.sleep(0.02)
        review = store.get_review(set_id)
    return review


@pytest.fixture
def env():
    users = UserStore(":memory:")
    banks = QuestionSetStore(":memory:")
    seen = {}

    def fake_reviewer(source, questions):
        seen["source"], seen["questions"] = source, questions
        if seen.get("gate"):
            seen["gate"].wait(5)
        return [QuestionReview(index=0, verdict="ok"),
                QuestionReview(index=1, verdict="fix", issues=[Issue(agent="fact_checker", text="Materialda 125.")],
                               suggestion=FIX),
                QuestionReview(index=7, verdict="ok")]  # mövcud olmayan sual - atılır

    for dep, value in {get_user_store: users, get_question_set_store: banks, get_token_secret: _SECRET,
                       get_reviewer: fake_reviewer}.items():
        app.dependency_overrides[dep] = (lambda v: lambda: v)(value)
    course = users.courses.create("Kurs", "exam_prep", trial_days=30, seat_limit=30)
    teacher = users.create("t@x.az", "h", "Müəllim", course_id=course["id"])
    users.set_teacher(teacher["id"], True)
    student = users.create("s@x.az", "h", "Tələbə", course_id=course["id"])
    bank = banks.create("qanunvericilik", "Konstitusiya", "pdf", "/tmp/x.pdf", created_by=teacher["id"],
                        course_id=course["id"])
    q1 = banks.add_question(bank["id"], q("Konstitusiya nə vaxt?"))
    q2 = banks.add_question(bank["id"], q("Milli Məclis neçə deputat?", 2))
    banks.mark_ready(bank["id"])
    with TestClient(app) as client:
        yield {"client": client, "banks": banks, "bank": bank, "q": [q1, q2], "seen": seen,
               "auth": {"Authorization": f"Bearer {create_token(teacher['id'], secret=_SECRET)}"},
               "student": {"Authorization": f"Bearer {create_token(student['id'], secret=_SECRET)}"}}
    app.dependency_overrides.clear()


def _url(env):
    return f"/live/question-sets/{env['bank']['id']}/review"


def test_review_runs_in_background_and_stores_results(env):
    assert env["client"].get(_url(env), headers=env["auth"]).json()["status"] == "none"
    r = env["client"].post(_url(env), headers=env["auth"])
    assert r.status_code == 202 and r.json()["status"] == "processing"
    _wait(env["banks"], env["bank"]["id"])
    body = env["client"].get(_url(env), headers=env["auth"]).json()
    assert body["status"] == "ready"
    assert [(i["question_id"], i["verdict"]) for i in body["items"]] == [(env["q"][0]["id"], "ok"),
                                                                         (env["q"][1]["id"], "fix")]
    fix = body["items"][1]
    assert fix["issues"] == [{"agent": "fact_checker", "agent_label": "Fakt yoxlayıcı", "text": "Materialda 125."}]
    assert fix["suggestion"]["correct_index"] == 3
    assert env["seen"]["source"].kind == "pdf" and len(env["seen"]["questions"]) == 2


def test_applying_suggestion_clears_that_review(env):
    env["client"].post(_url(env), headers=env["auth"])
    _wait(env["banks"], env["bank"]["id"])
    suggestion = env["client"].get(_url(env), headers=env["auth"]).json()["items"][1]["suggestion"]
    r = env["client"].patch(f"/live/questions/{env['q'][1]['id']}", json=suggestion, headers=env["auth"])
    assert r.status_code == 200 and r.json()["correct_index"] == 3
    items = env["client"].get(_url(env), headers=env["auth"]).json()["items"]
    assert [i["question_id"] for i in items] == [env["q"][0]["id"]]


def test_second_review_while_running_is_409(env):
    env["seen"]["gate"] = threading.Event()
    assert env["client"].post(_url(env), headers=env["auth"]).status_code == 202
    assert env["client"].post(_url(env), headers=env["auth"]).status_code == 409
    env["seen"]["gate"].set()
    _wait(env["banks"], env["bank"]["id"])
    assert env["client"].post(_url(env), headers=env["auth"]).status_code == 202
    _wait(env["banks"], env["bank"]["id"])


def test_failure_is_reported(env):
    def broken(source, questions):
        raise RuntimeError("Groq düşdü")

    app.dependency_overrides[get_reviewer] = lambda: broken
    env["client"].post(_url(env), headers=env["auth"])
    review = _wait(env["banks"], env["bank"]["id"])
    assert review["status"] == "failed" and "Groq düşdü" in review["error"]


def test_bank_not_ready_and_student_forbidden(env):
    other = env["banks"].create("x", "Hazırlanır", "pdf", "/tmp/y.pdf", created_by=1, course_id=1)
    assert env["client"].post(_url(env), headers=env["student"]).status_code == 403
    r = env["client"].post(f"/live/question-sets/{other['id']}/review", headers=env["auth"])
    assert r.status_code in (404, 409)


def test_deleting_question_removes_review(env):
    env["client"].post(_url(env), headers=env["auth"])
    _wait(env["banks"], env["bank"]["id"])
    env["client"].delete(f"/live/questions/{env['q'][0]['id']}", headers=env["auth"])
    items = env["client"].get(_url(env), headers=env["auth"]).json()["items"]
    assert [i["question_id"] for i in items] == [env["q"][1]["id"]]


def test_interrupted_review_marked_failed():
    store = QuestionSetStore(":memory:")
    assert store.start_review(5)
    assert store.fail_interrupted_reviews("restart") == 1
    assert store.get_review(5)["status"] == "failed"
