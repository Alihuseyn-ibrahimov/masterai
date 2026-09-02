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
