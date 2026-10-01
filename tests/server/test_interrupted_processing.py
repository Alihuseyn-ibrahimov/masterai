"""Servis yenidən başlayanda yarımçıq qalmış emallar (2026-10-01, produksiya).

Sual bankı və çat materialı FON TASK-ı ilə emal olunur (proses-daxili,
`-w 1`). Servis emal ortasında restart olsa (deploy, yaddaş çatışmazlığı),
task ölür, status isə əbədi `processing` qalır. Produksiyada 9 sentyabrdan
qalma iki bank 3 həftə «Hazırlanır» göstərirdi. Başlanğıcda bu sətirlər
izahla `failed` olur - müəllim nə baş verdiyini görür və yenidən yükləyir.
"""

from server.material_store import MaterialStore
from server.question_set_store import QuestionSetStore


def test_question_sets_processing_become_failed_with_reason():
    store = QuestionSetStore(":memory:")
    stuck = store.create("mentiq", "Yarımçıq", "link", "https://x", created_by=1)
    done = store.create("mentiq", "Hazır", "link", "https://x", created_by=1)
    store.mark_ready(done["id"])
    broken = store.create("mentiq", "Uğursuz", "link", "https://x", created_by=1)
    store.mark_failed(broken["id"], "əvvəlki səbəb")

    assert store.fail_interrupted("Server yenidən başladı") == 1

    assert store.get(stuck["id"])["status"] == "failed"
    assert store.get(stuck["id"])["error"] == "Server yenidən başladı"
    assert store.get(done["id"])["status"] == "ready"
    assert store.get(broken["id"])["error"] == "əvvəlki səbəb"  # köhnə səbəb üstünə yazılmır


def test_question_sets_second_call_is_noop():
    store = QuestionSetStore(":memory:")
    store.create("mentiq", "Yarımçıq", "link", "https://x", created_by=1)
    store.fail_interrupted("x")
    assert store.fail_interrupted("x") == 0


def test_materials_processing_become_failed():
    store = MaterialStore(":memory:")
    stuck = store.create(1, 1, "link", "https://x")
    done = store.create(1, 1, "link", "https://y")
    store.update_status(done["id"], "ready")

    assert store.fail_interrupted() == 1

    assert store.get(stuck["id"])["status"] == "failed"
    assert store.get(done["id"])["status"] == "ready"


def test_app_cleans_up_on_startup():
    """Yalnız metod yox - app onu başlanğıcda HƏQİQƏTƏN çağırır."""
    import inspect

    import server.app as app_module

    source = inspect.getsource(app_module)
    assert "question_set_store.fail_interrupted(" in source
    assert "material_store.fail_interrupted(" in source
