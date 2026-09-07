import pytest

from pipeline.models import MCQQuestion
from server.question_set_store import QuestionSetStore


@pytest.fixture
def store(tmp_path):
    return QuestionSetStore(path=str(tmp_path / "question_sets.db"))


def _mcq(question="Sual?") -> MCQQuestion:
    return MCQQuestion(
        question=question,
        options=["A", "B", "C", "D", "E"],
        correct_index=0,
        explanation="izah",
    )


def test_create_defaults_to_processing_status(store):
    qs = store.create(
        subject="mentiq", title="Silloqizmlər", material_kind="link",
        material_location="https://x.az", created_by=1,
    )

    assert qs["id"] is not None
    assert qs["subject"] == "mentiq"
    assert qs["title"] == "Silloqizmlər"
    assert qs["status"] == "processing"
    assert qs["material_kind"] == "link"
    assert qs["material_location"] == "https://x.az"
    assert qs["error"] is None
    assert qs["created_by"] == 1
    assert qs["created_at"]


def test_get_returns_none_when_missing(store):
    assert store.get(999) is None


def test_get_returns_created_question_set(store):
    created = store.create(
        subject="informatika", title="Alqoritmlər", material_kind="pdf",
        material_location="/tmp/a.pdf", created_by=1,
    )
    assert store.get(created["id"]) == created


def test_list_all_orders_newest_first(store):
    first = store.create(
        subject="mentiq", title="A", material_kind="link",
        material_location="https://a.az", created_by=1,
    )
    second = store.create(
        subject="informatika", title="B", material_kind="link",
        material_location="https://b.az", created_by=1,
    )
    results = store.list_all()
    assert [r["id"] for r in results] == [second["id"], first["id"]]


def test_mark_ready(store):
    created = store.create(
        subject="mentiq", title="A", material_kind="link",
        material_location="https://a.az", created_by=1,
    )
    store.mark_ready(created["id"])
    assert store.get(created["id"])["status"] == "ready"


def test_mark_failed_stores_error(store):
    created = store.create(
        subject="mentiq", title="A", material_kind="link",
        material_location="https://a.az", created_by=1,
    )
    store.mark_failed(created["id"], "Sayt yüklənmədi")
    updated = store.get(created["id"])
    assert updated["status"] == "failed"
    assert updated["error"] == "Sayt yüklənmədi"


def test_add_question_and_list_questions(store):
    qs = store.create(
        subject="mentiq", title="A", material_kind="link",
        material_location="https://a.az", created_by=1,
    )
    store.add_question(qs["id"], _mcq("1-ci sual?"))
    store.add_question(qs["id"], _mcq("2-ci sual?"))

    questions = store.list_questions(qs["id"])
    assert len(questions) == 2
    assert questions[0]["question"] == "1-ci sual?"
    assert questions[0]["options"] == ["A", "B", "C", "D", "E"]
    assert questions[0]["correct_index"] == 0


def test_list_questions_does_not_leak_across_question_sets(store):
    """Bax modul qeydi — `live_questions.question_set_id` `materials.id`
    ilə qarışmamalı olduğu kimi, iki müxtəlif `question_set`-in sualları
    da bir-birinə qarışmamalıdır."""
    qs1 = store.create(
        subject="mentiq", title="A", material_kind="link",
        material_location="https://a.az", created_by=1,
    )
    qs2 = store.create(
        subject="informatika", title="B", material_kind="link",
        material_location="https://b.az", created_by=1,
    )
    store.add_question(qs1["id"], _mcq("qs1 sualı"))
    store.add_question(qs2["id"], _mcq("qs2 sualı"))

    assert [q["question"] for q in store.list_questions(qs1["id"])] == ["qs1 sualı"]
    assert [q["question"] for q in store.list_questions(qs2["id"])] == ["qs2 sualı"]


def test_count_questions(store):
    qs = store.create(
        subject="mentiq", title="A", material_kind="link",
        material_location="https://a.az", created_by=1,
    )
    assert store.count_questions(qs["id"]) == 0
    store.add_question(qs["id"], _mcq())
    assert store.count_questions(qs["id"]) == 1


def test_get_question_returns_none_when_missing(store):
    assert store.get_question(999) is None


def test_update_question_changes_content(store):
    qs = store.create(
        subject="mentiq", title="A", material_kind="link",
        material_location="https://a.az", created_by=1,
    )
    created = store.add_question(qs["id"], _mcq("Köhnə sual?"))
    updated = store.update_question(
        created["id"],
        question="Yeni sual?",
        options=["X", "Y", "Z", "W", "V"],
        correct_index=2,
        explanation="yeni izah",
    )
    assert updated["question"] == "Yeni sual?"
    assert updated["options"] == ["X", "Y", "Z", "W", "V"]
    assert updated["correct_index"] == 2
    assert updated["explanation"] == "yeni izah"
    assert store.get_question(created["id"]) == updated


def test_delete_question_removes_it(store):
    qs = store.create(
        subject="mentiq", title="A", material_kind="link",
        material_location="https://a.az", created_by=1,
    )
    created = store.add_question(qs["id"], _mcq())
    store.delete_question(created["id"])
    assert store.get_question(created["id"]) is None
    assert store.count_questions(qs["id"]) == 0
