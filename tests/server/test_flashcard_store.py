"""Flashcard saxlanması: generasiya işi, redaktə, dərc, Leitner təkrarı (Faza 1, PR 3)."""

import pytest

from server.question_set_store import QuestionSetStore


@pytest.fixture
def store(tmp_path):
    return QuestionSetStore(path=str(tmp_path / "question_sets.db"))


@pytest.fixture
def bank(store):
    return store.create(subject="mentiq", title="Bank", material_kind="pdf",
                        material_location="x.pdf", created_by=1)


def _cards():
    return [{"front": "Sual 1?", "back": "Cavab 1.", "difficulty": "orta"},
            {"front": "Sual 2?", "back": "Cavab 2.", "difficulty": None}]


def test_job_lifecycle(store, bank):
    assert store.start_flashcard_job(bank["id"]) is True
    assert store.start_flashcard_job(bank["id"]) is False  # artıq gedir
    store.finish_flashcard_job(bank["id"], _cards())
    job = store.get_flashcard_job(bank["id"])
    assert job["status"] == "ready"
    cards = store.list_flashcards(bank["id"])
    assert [c["front"] for c in cards] == ["Sual 1?", "Sual 2?"]
    # İkinci generasiya əlavə edir, silmir.
    store.start_flashcard_job(bank["id"])
    store.finish_flashcard_job(bank["id"], [{"front": "Sual 3?", "back": "Cavab 3.", "difficulty": "asan"}])
    assert len(store.list_flashcards(bank["id"])) == 3


def test_job_failure_and_interrupted(store, bank):
    store.start_flashcard_job(bank["id"])
    store.fail_flashcard_job(bank["id"], "Groq düşdü")
    assert store.get_flashcard_job(bank["id"])["status"] == "failed"
    store.start_flashcard_job(bank["id"])
    assert store.fail_interrupted_flashcard_jobs("restart") == 1
    assert store.get_flashcard_job(bank["id"])["status"] == "failed"


def test_update_and_delete_flashcard(store, bank):
    store.start_flashcard_job(bank["id"])
    store.finish_flashcard_job(bank["id"], _cards())
    card = store.list_flashcards(bank["id"])[0]
    updated = store.update_flashcard(card["id"], front="Yeni sual?", back="Yeni cavab.", difficulty="çətin")
    assert updated["front"] == "Yeni sual?" and updated["difficulty"] == "çətin"
    store.delete_flashcard(card["id"])
    assert store.get_flashcard(card["id"]) is None
    assert len(store.list_flashcards(bank["id"])) == 1


def test_publish_and_unpublish(store, bank):
    store.start_flashcard_job(bank["id"])
    store.finish_flashcard_job(bank["id"], _cards())
    assert store.get_flashcard_publication(bank["id"]) is None
    store.publish_flashcards(bank["id"], chat_id=7, published_by=1)
    pub = store.get_flashcard_publication(bank["id"])
    assert pub["chat_id"] == 7
    decks = store.list_published_flashcard_decks_for_chats([7, 9])
    assert [d["question_set_id"] for d in decks] == [bank["id"]]
    store.unpublish_flashcards(bank["id"])
    assert store.get_flashcard_publication(bank["id"]) is None
    assert store.list_published_flashcard_decks_for_chats([7]) == []


def test_publication_hidden_when_no_cards_yet(store, bank):
    # Müəllim çatı seçə bilər, amma kart hələ yoxdursa tələbə boş kart görməsin.
    store.publish_flashcards(bank["id"], chat_id=7, published_by=1)
    assert store.list_published_flashcard_decks_for_chats([7]) == []


def test_leitner_review_progresses_and_resets(store, bank):
    store.start_flashcard_job(bank["id"])
    store.finish_flashcard_job(bank["id"], _cards())
    card = store.list_flashcards(bank["id"])[0]

    # Hələ baxılmayıb - həmişə vaxtı çatıb sayılır.
    due, total = store.count_due_flashcards(bank["id"], user_id=9)
    assert (due, total) == (2, 2)

    state = store.record_flashcard_review(card["id"], user_id=9, know=True)
    assert state["box"] == 2
    state = store.record_flashcard_review(card["id"], user_id=9, know=True)
    assert state["box"] == 3
    state = store.record_flashcard_review(card["id"], user_id=9, know=True)
    assert state["box"] == 3  # 3-dən artıq qutu yoxdur

    # Bilən kart tezliklə vaxtı çatmış siyahısında deyil.
    due_cards = store.list_due_flashcards(bank["id"], user_id=9)
    assert [c["id"] for c in due_cards] == [store.list_flashcards(bank["id"])[1]["id"]]

    # Bilmirəm 1-ci qutuya atır.
    state = store.record_flashcard_review(card["id"], user_id=9, know=False)
    assert state["box"] == 1


def test_review_state_is_per_user(store, bank):
    store.start_flashcard_job(bank["id"])
    store.finish_flashcard_job(bank["id"], _cards())
    card = store.list_flashcards(bank["id"])[0]
    store.record_flashcard_review(card["id"], user_id=1, know=True)
    assert store.flashcard_review_state(card["id"], user_id=1)["box"] == 2
    assert store.flashcard_review_state(card["id"], user_id=2) is None
    due, _ = store.count_due_flashcards(bank["id"], user_id=2)
    assert due == 2  # ikinci tələbə üçün hələ hamısı yeni
