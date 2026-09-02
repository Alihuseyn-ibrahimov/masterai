import pytest

from server.material_store import MaterialStore


@pytest.fixture
def store(tmp_path):
    return MaterialStore(path=str(tmp_path / "materials.db"))


def test_create_defaults_to_processing_status(store):
    material = store.create(chat_id=1, uploaded_by=2, kind="pdf", location="/tmp/a.pdf")

    assert material["id"] is not None
    assert material["chat_id"] == 1
    assert material["uploaded_by"] == 2
    assert material["kind"] == "pdf"
    assert material["location"] == "/tmp/a.pdf"
    assert material["status"] == "processing"
    assert material["created_at"]


def test_get_returns_none_when_missing(store):
    assert store.get(999) is None


def test_get_returns_created_material(store):
    created = store.create(chat_id=1, uploaded_by=2, kind="link", location="https://x.az")
    assert store.get(created["id"]) == created


def test_list_by_chat(store):
    store.create(chat_id=1, uploaded_by=2, kind="pdf", location="/a.pdf")
    store.create(chat_id=1, uploaded_by=2, kind="image", location="/b.png")
    store.create(chat_id=2, uploaded_by=2, kind="link", location="https://x.az")

    results = store.list_by_chat(1)
    assert len(results) == 2
    assert {m["location"] for m in results} == {"/a.pdf", "/b.png"}


def test_update_status(store):
    created = store.create(chat_id=1, uploaded_by=2, kind="pdf", location="/a.pdf")
    store.update_status(created["id"], "ready")

    assert store.get(created["id"])["status"] == "ready"


def test_create_with_label(store):
    material = store.create(
        chat_id=1, uploaded_by=2, kind="pdf", location="/a.pdf", label="Tarix mühazirəsi"
    )
    assert material["label"] == "Tarix mühazirəsi"
    assert store.get(material["id"])["label"] == "Tarix mühazirəsi"


def test_create_without_label_defaults_to_none(store):
    material = store.create(chat_id=1, uploaded_by=2, kind="pdf", location="/a.pdf")
    assert material["label"] is None


def test_list_by_chat_includes_label(store):
    store.create(chat_id=1, uploaded_by=2, kind="pdf", location="/a.pdf", label="Etiket")
    results = store.list_by_chat(1)
    assert results[0]["label"] == "Etiket"


def test_count_all(store):
    assert store.count_all() == 0
    store.create(chat_id=1, uploaded_by=2, kind="pdf", location="/a.pdf")
    store.create(chat_id=1, uploaded_by=2, kind="link", location="https://x.az")
    assert store.count_all() == 2


def test_count_by_status(store):
    a = store.create(chat_id=1, uploaded_by=2, kind="pdf", location="/a.pdf")
    store.create(chat_id=1, uploaded_by=2, kind="link", location="https://x.az")
    store.update_status(a["id"], "ready")

    assert store.count_by_status("ready") == 1
    assert store.count_by_status("processing") == 1
    assert store.count_by_status("failed") == 0
