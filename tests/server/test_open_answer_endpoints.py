"""Ev tapşırığında açıq cavab + AI yoxlaması + müəllim təsdiqi (Faza 1, PR 2)."""

import threading
import time

import pytest
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion
from pipeline.open_grading import CriterionGrade, GradeResult
from server.app import (
    app,
    get_chat_store,
    get_homework_store,
    get_open_answer_grader,
    get_question_set_store,
    get_token_secret,
    get_user_store,
)
from server.auth import create_token
from server.chat_store import ChatStore
from server.homework_store import HomeworkStore
from server.question_set_store import QuestionSetStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"
RUBRIC = [{"criterion": "Müsabiqəni deyir", "points": 2}, {"criterion": "DİM-i deyir", "points": 3}]


def _wait(store, answer_id, timeout=10.0):
    deadline = time.time() + timeout
    row = store.get_open_answer(answer_id)
    while row["status"] == "grading" and time.time() < deadline:
        time.sleep(0.02)
        row = store.get_open_answer(answer_id)
    return row


@pytest.fixture
def env():
    users, banks, chats, homework = (UserStore(":memory:"), QuestionSetStore(":memory:"),
                                     ChatStore(":memory:"), HomeworkStore(":memory:"))
    seen = {}

    def fake_grader(question, model_answer, rubric, answer):
        seen.update(question=question, rubric=rubric, answer=answer)
        if seen.get("gate"):
            seen["gate"].wait(5)
        if seen.get("broken"):
            raise RuntimeError("Groq düşdü")
        return GradeResult(criteria=[CriterionGrade(criterion=r["criterion"], points=r["points"],
                                                    awarded=r["points"] - 1, comment="qismən")
                                     for r in rubric], feedback="Orqanı daha dəqiq yazın.")

    for dep, value in {get_user_store: users, get_question_set_store: banks, get_chat_store: chats,
                       get_homework_store: homework, get_token_secret: _SECRET,
                       get_open_answer_grader: fake_grader}.items():
        app.dependency_overrides[dep] = (lambda v: lambda: v)(value)
    course = users.courses.create("Kurs", "exam_prep", trial_days=30, seat_limit=30)
    teacher = users.create("t@x.az", "h", "Müəllim", course_id=course["id"])
    users.set_teacher(teacher["id"], True)
    student = users.create("s@x.az", "h", "Tələbə", course_id=course["id"])
    other = users.create("o@x.az", "h", "Başqası", course_id=course["id"])
    chat = chats.create(kind="group", created_by=teacher["id"], name="Sinif", course_id=course["id"])
    for uid in (teacher["id"], student["id"], other["id"]):
        chats.add_member(chat["id"], uid)
    bank = banks.create("qanunvericilik", "Qulluq", "pdf", "/tmp/x.pdf", created_by=teacher["id"],
                        course_id=course["id"])
    banks.add_question(bank["id"], MCQQuestion(question="?", options=list("abcde"), correct_index=0, explanation="i"))
    banks.mark_ready(bank["id"])
    banks.start_open_job(bank["id"])
    banks.finish_open_job(bank["id"], [{"kind": "qisa", "question": "Qəbul necə aparılır?",
                                        "model_answer": "Müsabiqə ilə, DİM keçirir.", "rubric": RUBRIC}])
    oq = banks.list_open_questions(bank["id"])[0]
    assignment = homework.create_assignment(chat["id"], bank["id"], "2099-01-01", created_by=teacher["id"])
    with TestClient(app) as client:
        auth = lambda u: {"Authorization": f"Bearer {create_token(u['id'], secret=_SECRET)}"}  # noqa: E731
        attempt = client.post(f"/homework/assignments/{assignment['id']}/start", headers=auth(student)).json()
        yield {"client": client, "homework": homework, "banks": banks, "bank": bank, "oq": oq, "seen": seen,
               "assignment": assignment, "attempt_id": attempt["attempt_id"],
               "teacher": auth(teacher), "student": auth(student), "other": auth(other)}
    app.dependency_overrides.clear()


def _submit(env, text="Müsabiqə yolu ilə aparılır, DİM keçirir.", headers=None):
    return env["client"].post(f"/homework/attempts/{env['attempt_id']}/open-answers",
                              json={"open_question_id": env["oq"]["id"], "answer": text},
                              headers=headers or env["student"])


def test_student_answers_ai_grades_teacher_confirms(env):
    c = env["client"]
    items = c.get(f"/homework/attempts/{env['attempt_id']}/open-questions", headers=env["student"]).json()
    assert [(i["question"], i["max_points"], i["answer"]) for i in items] == [("Qəbul necə aparılır?", 5, None)]

    r = _submit(env)
    assert r.status_code == 202 and r.json()["status"] == "grading"
    assert r.json()["model_answer"] is None                 # yoxlanana qədər nümunə gizlidir
    _wait(env["homework"], r.json()["id"])

    answer = c.get(f"/homework/attempts/{env['attempt_id']}/open-questions",
                   headers=env["student"]).json()[0]["answer"]
    assert answer["status"] == "graded" and answer["ai_points"] == 3 and answer["final_points"] is None
    assert [g["awarded"] for g in answer["criteria"]] == [1, 2]
    assert answer["feedback"] == "Orqanı daha dəqiq yazın." and answer["model_answer"]
    assert env["seen"]["rubric"] == RUBRIC

    rows = c.get(f"/homework/assignments/{env['assignment']['id']}/open-answers", headers=env["teacher"]).json()
    assert [(row["display_name"], row["ai_points"]) for row in rows] == [("Tələbə", 3)]
    url = f"/homework/open-answers/{rows[0]['id']}/confirm"
    assert c.post(url, json={"points": 6}, headers=env["teacher"]).status_code == 400
    confirmed = c.post(url, json={"points": 4, "comment": " Yaxşı "}, headers=env["teacher"]).json()
    assert confirmed["status"] == "confirmed" and confirmed["final_points"] == 4
    assert confirmed["teacher_comment"] == "Yaxşı"
    answer = c.get(f"/homework/attempts/{env['attempt_id']}/open-questions",
                   headers=env["student"]).json()[0]["answer"]
    assert answer["final_points"] == 4 and answer["teacher_comment"] == "Yaxşı"


def test_one_answer_per_question(env):
    first = _submit(env)
    _wait(env["homework"], first.json()["id"])
    assert _submit(env).status_code == 409


def test_failed_grading_is_left_to_teacher(env):
    env["seen"]["broken"] = True
    row = _wait(env["homework"], _submit(env).json()["id"])
    assert row["status"] == "failed" and "Groq" in row["error"]
    rows = env["client"].get(f"/homework/assignments/{env['assignment']['id']}/open-answers",
                             headers=env["teacher"]).json()
    assert rows[0]["status"] == "failed" and rows[0]["ai_points"] is None
    r = env["client"].post(f"/homework/open-answers/{rows[0]['id']}/confirm", json={"points": 5},
                           headers=env["teacher"])
    assert r.status_code == 200 and r.json()["final_points"] == 5


def test_teacher_confirm_before_ai_finishes_is_kept(env):
    env["seen"]["gate"] = threading.Event()
    answer_id = _submit(env).json()["id"]
    env["client"].post(f"/homework/open-answers/{answer_id}/confirm", json={"points": 1}, headers=env["teacher"])
    env["seen"]["gate"].set()
    time.sleep(0.2)
    row = env["homework"].get_open_answer(answer_id)
    assert row["status"] == "confirmed" and row["final_points"] == 1


def test_access_rules(env):
    c = env["client"]
    # Başqa tələbə bu cəhdi görə və cavablaya bilmir.
    assert c.get(f"/homework/attempts/{env['attempt_id']}/open-questions", headers=env["other"]).status_code == 404
    assert _submit(env, headers=env["other"]).status_code == 404
    # Başqa bankın sualı bu tapşırığa cavablanmır.
    other_bank = env["banks"].create("mentiq", "B", "pdf", "/tmp/y.pdf", created_by=1, course_id=env["bank"]["course_id"])
    env["banks"].start_open_job(other_bank["id"])
    env["banks"].finish_open_job(other_bank["id"], [{"kind": "qisa", "question": "Başqa?", "model_answer": "x",
                                                    "rubric": RUBRIC}])
    foreign = env["banks"].list_open_questions(other_bank["id"])[0]
    r = c.post(f"/homework/attempts/{env['attempt_id']}/open-answers",
               json={"open_question_id": foreign["id"], "answer": "bir iki üç"}, headers=env["student"])
    assert r.status_code == 404
    assert _submit(env, text="   ").status_code == 400
    # Tələbə hesabatı görə və bal verə bilmir.
    answer_id = _submit(env).json()["id"]
    _wait(env["homework"], answer_id)
    assert c.get(f"/homework/assignments/{env['assignment']['id']}/open-answers",
                 headers=env["student"]).status_code == 403
    assert c.post(f"/homework/open-answers/{answer_id}/confirm", json={"points": 5},
                  headers=env["student"]).status_code == 403


def test_answer_survives_question_deletion(env):
    answer_id = _submit(env).json()["id"]
    _wait(env["homework"], answer_id)
    env["banks"].delete_open_question(env["oq"]["id"])
    items = env["client"].get(f"/homework/attempts/{env['attempt_id']}/open-questions",
                              headers=env["student"]).json()
    assert len(items) == 1 and items[0]["answer"]["id"] == answer_id and items[0]["max_points"] == 5


def test_interrupted_grading_fails_on_restart(env):
    row = env["homework"].submit_open_answer(env["homework"].get_attempt(env["attempt_id"]), env["oq"], "x y z")
    assert env["homework"].fail_interrupted_open_grading("restart") >= 1
    assert env["homework"].get_open_answer(row["id"])["status"] == "failed"
