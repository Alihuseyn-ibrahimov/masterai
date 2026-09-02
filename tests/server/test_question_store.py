import pytest

from pipeline.models import MCQQuestion
from server.question_store import QuestionStore


@pytest.fixture
def store(tmp_path):
    return QuestionStore(path=str(tmp_path / "questions.db"))


def _mcq(question: str = "Paytaxt hansıdır?") -> MCQQuestion:
    return MCQQuestion(
        question=question,
        options=["Bakı", "Gəncə", "Sumqayıt", "Şəki", "Naxçıvan"],
        correct_index=0,
        explanation="Bakı Azərbaycanın paytaxtıdır.",
    )


def test_create_from_mcq_roundtrips_correctly(store):
    saved = store.create_from_mcq(material_id=1, mcq=_mcq())

    assert saved["id"] is not None
    assert saved["material_id"] == 1
    assert saved["question"] == "Paytaxt hansıdır?"
    assert saved["options"] == ["Bakı", "Gəncə", "Sumqayıt", "Şəki", "Naxçıvan"]
    assert saved["correct_index"] == 0
    assert saved["explanation"] == "Bakı Azərbaycanın paytaxtıdır."
    assert saved["created_at"]


def test_get_returns_none_when_missing(store):
    assert store.get(999) is None


def test_get_returns_created_question(store):
    created = store.create_from_mcq(material_id=1, mcq=_mcq())
    assert store.get(created["id"]) == created


def test_list_by_material(store):
    store.create_from_mcq(material_id=1, mcq=_mcq("Sual 1?"))
    store.create_from_mcq(material_id=1, mcq=_mcq("Sual 2?"))
    store.create_from_mcq(material_id=2, mcq=_mcq("Sual 3?"))

    results = store.list_by_material(1)
    assert len(results) == 2
    assert {q["question"] for q in results} == {"Sual 1?", "Sual 2?"}


def test_options_preserve_order_and_azerbaijani_characters(store):
    saved = store.create_from_mcq(material_id=1, mcq=_mcq())
    assert saved["options"][0] == "Bakı"
    assert saved["options"][4] == "Naxçıvan"


def test_count_all(store):
    assert store.count_all() == 0
    store.create_from_mcq(material_id=1, mcq=_mcq("Sual 1?"))
    store.create_from_mcq(material_id=2, mcq=_mcq("Sual 2?"))
    assert store.count_all() == 2
