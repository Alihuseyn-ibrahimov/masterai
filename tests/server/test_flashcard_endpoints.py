"""Flashcard marşrutları: generasiya, redaktə, dərc, tələbənin təkrarı (Faza 1, PR 3)."""

import threading
import time

import pytest
from fastapi.testclient import TestClient

from pipeline.flashcards import Flashcard
from pipeline.models import MCQQuestion
from server.app import (
    app,
    get_chat_store,
    get_flashcard_generator,
    get_question_set_store,
    get_token_secret,
    get_user_store,
)
from server.auth import create_token
from server.chat_store import ChatStore
from server.question_set_store import QuestionSetStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


def _card(front, back="Cavab."):
    return Flashcard(front=front, back=back, difficulty="orta")


def _wait(store, set_id, timeout=10.0):
    deadline = time.time() + timeout
    job = store.get_flashcard_job(set_id)
    while job and job["status"] == "processing" and time.time() < deadline:
        time.sleep(0.02)
        job = store.get_flashcard_job(set_id)
    return job


@pytest.fixture
def env():
    users = UserStore(":memory:")
    banks = QuestionSetStore(":memory:")
    chats = ChatStore(":memory:")
    seen = {}

    def fake_generator(source, count, subject):
        seen.update(source=source, count=count, subject=subject)
        if seen.get("gate"):
            seen["gate"].wait(5)
        return [_card("Sual 1?"), _card("Sual 2?")][:count]

    for dep, value in {get_user_store: users, get_question_set_store: banks, get_chat_store: chats,
                       get_token_secret: _SECRET, get_flashcard_generator: fake_generator}.items():
        app.dependency_overrides[dep] = (lambda v: lambda: v)(value)
    course = users.courses.create("Kurs", "exam_prep", trial_days=30, seat_limit=30)
    teacher = users.create("t@x.az", "h", "Müəllim", course_id=course["id"])
    users.set_teacher(teacher["id"], True)
    student = users.create("s@x.az", "h", "Tələbə", course_id=course["id"])
    other = users.create("o@x.az", "h", "Başqası", course_id=course["id"])
    bank = banks.create("qanunvericilik", "Qulluq", "pdf", "/tmp/x.pdf", created_by=teacher["id"],
                        course_id=course["id"])
    banks.add_question(bank["id"], MCQQuestion(question="?", options=list("abcde"), correct_index=0,
                                               explanation="i"))
    banks.mark_ready(bank["id"])
    chat = chats.create(kind="group", created_by=teacher["id"], name="Sinif", course_id=course["id"])
    chats.add_member(chat["id"], teacher["id"])
    chats.add_member(chat["id"], student["id"])
    with TestClient(app) as client:
        yield {"client": client, "banks": banks, "bank": bank, "chat": chat, "seen": seen,
               "teacher": {"Authorization": f"Bearer {create_token(teacher['id'], secret=_SECRET)}"},
               "student": {"Authorization": f"Bearer {create_token(student['id'], secret=_SECRET)}"},
               "other": {"Authorization": f"Bearer {create_token(other['id'], secret=_SECRET)}"}}
    app.dependency_overrides.clear()


def _url(env):
    return f"/live/question-sets/{env['bank']['id']}/flashcards"


def test_generation_runs_in_background_and_appends(env):
    c = env["client"]
    assert c.get(_url(env), headers=env["teacher"]).json() == {
        "status": "none", "error": None, "items": [], "chat_id": None, "chat_name": None, "published_at": None,
    }
    r = c.post(_url(env), json={"count": 2}, headers=env["teacher"])
    assert r.status_code == 202 and r.json()["status"] == "processing"
    _wait(env["banks"], env["bank"]["id"])
    body = c.get(_url(env), headers=env["teacher"]).json()
    assert body["status"] == "ready"
    assert [i["front"] for i in body["items"]] == ["Sual 1?", "Sual 2?"]
    assert env["seen"]["subject"] == "qanunvericilik" and env["seen"]["source"].kind == "pdf"

    c.post(_url(env), json={"count": 1}, headers=env["teacher"])
    _wait(env["banks"], env["bank"]["id"])
    assert len(c.get(_url(env), headers=env["teacher"]).json()["items"]) == 3   # köhnələr qalır


def test_edit_and_delete(env):
    c = env["client"]
    c.post(_url(env), json={"count": 1}, headers=env["teacher"])
    _wait(env["banks"], env["bank"]["id"])
    item = c.get(_url(env), headers=env["teacher"]).json()["items"][0]
    patch = {"front": "Yeni sual?", "back": "Yeni cavab.", "difficulty": "çətin"}
    r = c.patch(f"/live/flashcards/{item['id']}", json=patch, headers=env["teacher"])
    assert r.status_code == 200 and r.json()["front"] == "Yeni sual?" and r.json()["difficulty"] == "çətin"

    assert c.delete(f"/live/flashcards/{item['id']}", headers=env["teacher"]).status_code == 204
    assert c.get(_url(env), headers=env["teacher"]).json()["items"] == []
    assert c.delete(f"/live/flashcards/{item['id']}", headers=env["teacher"]).status_code == 404


def test_second_generation_while_running_is_409(env):
    env["seen"]["gate"] = threading.Event()
    assert env["client"].post(_url(env), json={}, headers=env["teacher"]).status_code == 202
    assert env["client"].post(_url(env), json={}, headers=env["teacher"]).status_code == 409
    env["seen"]["gate"].set()
    _wait(env["banks"], env["bank"]["id"])


def test_validation_student_and_unready_bank(env):
    c = env["client"]
    assert c.post(_url(env), json={"count": 31}, headers=env["teacher"]).status_code == 422
    assert c.post(_url(env), json={}, headers=env["student"]).status_code == 403
    assert c.get(_url(env), headers=env["student"]).status_code == 403
    other_bank = env["banks"].create("mentiq", "Hazırlanır", "pdf", "/tmp/y.pdf", created_by=1,
                                     course_id=env["bank"]["course_id"])
    r = c.post(f"/live/question-sets/{other_bank['id']}/flashcards", json={}, headers=env["teacher"])
    assert r.status_code == 409


def test_interrupted_job_is_failed_on_restart(env):
    banks = env["banks"]
    banks.start_flashcard_job(env["bank"]["id"])
    assert banks.fail_interrupted_flashcard_jobs("restart") == 1
    assert banks.get_flashcard_job(env["bank"]["id"])["status"] == "failed"


def _publish(env):
    c, bank, chat = env["client"], env["bank"], env["chat"]
    c.post(_url(env), json={"count": 2}, headers=env["teacher"])
    _wait(env["banks"], bank["id"])
    r = c.post(f"/live/question-sets/{bank['id']}/flashcards/publish", json={"chat_id": chat["id"]},
              headers=env["teacher"])
    assert r.status_code == 200
    return r.json()


def test_publish_announces_once_and_appears_for_student(env):
    c = env["client"]
    _publish(env)
    # Təkrar dərc ikinci mesaj yazmır.
    r2 = c.post(f"/live/question-sets/{env['bank']['id']}/flashcards/publish",
               json={"chat_id": env["chat"]["id"]}, headers=env["teacher"])
    assert r2.status_code == 200

    decks = c.get("/me/flashcards", headers=env["student"]).json()
    assert [(d["question_set_id"], d["due_count"], d["total_count"]) for d in decks] == [
        (env["bank"]["id"], 2, 2)
    ]
    cards = c.get(f"/me/flashcards/{env['bank']['id']}", headers=env["student"]).json()
    assert [card["front"] for card in cards] == ["Sual 1?", "Sual 2?"]
    assert "back" in cards[0]


def test_publish_requires_cards_and_group_chat(env):
    c = env["client"]
    r = c.post(f"/live/question-sets/{env['bank']['id']}/flashcards/publish",
              json={"chat_id": env["chat"]["id"]}, headers=env["teacher"])
    assert r.status_code == 400   # hələ kart yoxdur


def test_unpublish_hides_from_student(env):
    c = env["client"]
    _publish(env)
    assert c.post(f"/live/question-sets/{env['bank']['id']}/flashcards/unpublish",
                  headers=env["teacher"]).status_code == 204
    assert c.get("/me/flashcards", headers=env["student"]).json() == []
    assert c.get(f"/me/flashcards/{env['bank']['id']}", headers=env["student"]).status_code == 404


def test_review_updates_due_count_and_is_per_user(env):
    c = env["client"]
    _publish(env)
    cards = c.get(f"/me/flashcards/{env['bank']['id']}", headers=env["student"]).json()
    r = c.post(f"/me/flashcards/{cards[0]['id']}/review", json={"know": True}, headers=env["student"])
    assert r.status_code == 204
    decks = c.get("/me/flashcards", headers=env["student"]).json()
    assert decks[0]["due_count"] == 1   # bir kart bilindi, vaxtı sonraya keçdi

    # Çatın üzvü olmayan başqası bu bankı görmür və cavablaya bilmir.
    assert c.get("/me/flashcards", headers=env["other"]).json() == []
    assert c.get(f"/me/flashcards/{env['bank']['id']}", headers=env["other"]).status_code == 404
    assert c.post(f"/me/flashcards/{cards[0]['id']}/review", json={"know": True},
                  headers=env["other"]).status_code == 404
