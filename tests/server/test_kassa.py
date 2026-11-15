"""Kurs Kassası (addım 2): `server/kassa.py` hesablaması və `/live/kassa*`.

Spec: docs/superpowers/specs/2026-11-15-kurs-kassasi-design.md
Kurs sərhədi (başqa kurs = 404) test_course_boundary.py-dədir.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from server import kassa
from server.app import (
    app, get_chat_store, get_connection_manager, get_message_store,
    get_payment_store, get_token_secret, get_user_store,
)
from server.auth import create_token
from server.chat_store import ChatStore
from server.connection_manager import ConnectionManager
from server.kassa import Enrollment
from server.message_store import MessageStore
from server.payment_store import PaymentStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"
UTC = timezone.utc
NOW = datetime(2026, 11, 20, tzinfo=UTC)


def _e(student_id, joined="2026-09-01T00:00:00+00:00", amount=100, chat_id=1):
    return Enrollment(chat_id, "Abituriyent", student_id, f"Tələbə {student_id}", joined, amount)


def _r(student_id, month, amount=100, chat_id=1):
    return {"chat_id": chat_id, "student_id": student_id, "month": month, "amount": amount,
            "paid_at": f"{month}-03T10:00:00+00:00"}


# ---------- saf hesablama ----------

def test_months_helpers():
    assert kassa.next_month("2026-12") == "2027-01"
    assert kassa.prev_month("2026-01") == "2025-12"
    assert kassa.months_back("2026-02", 3) == ["2025-12", "2026-01", "2026-02"]


def test_expected_collected_outstanding_and_net():
    out = kassa.summarize(
        "2026-11", NOW, [_e(1), _e(2), _e(3, amount=80)],
        [_r(1, "2026-11"), _r(3, "2026-11", 80)],
        [{"id": 1, "month": "2026-11", "category": "İcarə", "amount": 50, "note": "", "created_at": "x"}],
    )
    assert out["expected"] == 280
    assert out["collected"] == 180
    assert out["outstanding"] == 100
    assert out["collection_rate"] == round(180 / 280, 4)
    assert out["net"] == 130
    assert [d["student_id"] for d in out["debtors"]] == [2]
    assert out["expenses_by_category"] == [{"category": "İcarə", "amount": 50}]


def test_student_without_fee_is_not_a_debtor_but_is_counted():
    out = kassa.summarize("2026-11", NOW, [_e(1, amount=None)], [], [])
    assert out["debtors"] == [] and out["expected"] == 0
    assert out["collection_rate"] is None
    assert out["students_without_fee"] == 1


def test_student_joined_after_month_is_not_billed():
    out = kassa.summarize("2026-10", NOW, [_e(1, joined="2026-11-02T00:00:00+00:00")], [], [])
    assert out["expected"] == 0 and out["debtors"] == []


def test_overdue_days_count_from_join_date_inside_month():
    out = kassa.summarize("2026-11", NOW, [_e(1, joined="2026-11-10T00:00:00+00:00")], [], [])
    assert out["debtors"][0]["days_overdue"] == 10
    assert out["debtors"][0]["unpaid_months"] == 1


def test_past_month_overdue_stops_at_month_end():
    out = kassa.summarize("2026-09", NOW, [_e(1)], [], [])
    assert out["debtors"][0]["days_overdue"] == 30


def test_unpaid_streak_and_likely_left_flag():
    out = kassa.summarize("2026-11", NOW, [_e(1), _e(2)],
                          [_r(1, "2026-09"), _r(2, "2026-09"), _r(2, "2026-10")], [])
    by_id = {d["student_id"]: d for d in out["debtors"]}
    assert by_id[1]["unpaid_months"] == 2 and by_id[1]["likely_left"]
    assert by_id[1]["last_paid_month"] == "2026-09"
    assert by_id[2]["unpaid_months"] == 1 and not by_id[2]["likely_left"]
    # Ən uzun borc yuxarıda.
    assert out["debtors"][0]["student_id"] == 1


def test_streak_does_not_count_months_before_joining():
    out = kassa.summarize("2026-11", NOW, [_e(1, joined="2026-10-15T00:00:00+00:00")], [], [])
    assert out["debtors"][0]["unpaid_months"] == 2


def test_same_student_in_two_groups_is_billed_twice():
    out = kassa.summarize("2026-11", NOW, [_e(1, chat_id=1), _e(1, chat_id=2, amount=70)],
                          [_r(1, "2026-11", chat_id=1)], [])
    assert out["expected"] == 170
    assert [(d["chat_id"], d["amount"]) for d in out["debtors"]] == [(2, 70)]
    assert len(out["by_chat"]) == 2


def test_trend_covers_six_months_oldest_first():
    out = kassa.summarize("2026-11", NOW, [_e(1)], [_r(1, "2026-10")],
                          [{"id": 1, "month": "2026-10", "category": "Reklam", "amount": 30,
                            "note": "", "created_at": "x"}])
    months = [t["month"] for t in out["trend"]]
    assert months == ["2026-06", "2026-07", "2026-08", "2026-09", "2026-10", "2026-11"]
    october = out["trend"][4]
    assert october == {"month": "2026-10", "expected": 100, "collected": 100, "expenses": 30, "net": 70}
    assert out["trend"][0]["expected"] == 0  # iyunda hələ qoşulmamışdı


# ---------- endpoint-lər ----------

@pytest.fixture
def env():
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    payments = PaymentStore(":memory:")
    messages = MessageStore(":memory:")
    for dep, value in {
        get_user_store: users, get_chat_store: chats, get_payment_store: payments,
        get_message_store: messages, get_connection_manager: ConnectionManager(),
        get_token_secret: _SECRET,
    }.items():
        app.dependency_overrides[dep] = (lambda v: lambda: v)(value)

    course = users.courses.create("Master NR 1", "exam_prep", trial_days=30, seat_limit=30)

    def person(email, name, *, teacher=False, admin=False):
        row = users.create(email, "h", name, course_id=course["id"])
        users.set_teacher(row["id"], teacher)
        users.set_admin(row["id"], admin)
        return users.get_by_id(row["id"])

    boss = person("rehber@m.az", "Rəhbər", teacher=True, admin=True)
    teacher = person("muellim@m.az", "Müəllim", teacher=True)
    s1 = person("s1@m.az", "Aysel")
    s2 = person("s2@m.az", "Murad")
    chat = chats.create(kind="group", created_by=teacher["id"], name="Abituriyent A", course_id=course["id"])
    for u in (teacher, s1, s2):
        chats.add_member(chat["id"], u["id"])
    payments.set_fee(chat["id"], s1["id"], 120)
    payments.set_fee(chat["id"], s2["id"], 120)
    yield {"client": TestClient(app), "payments": payments, "messages": messages, "chat": chat,
           "boss": boss, "teacher": teacher, "s1": s1, "s2": s2, "course": course}
    app.dependency_overrides.clear()


def _auth(user) -> dict:
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


def _month() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def test_kassa_requires_course_admin(env):
    assert env["client"].get("/live/kassa").status_code == 401
    assert env["client"].get("/live/kassa", headers=_auth(env["s1"])).status_code == 403
    assert env["client"].get("/live/kassa", headers=_auth(env["teacher"])).status_code == 403


def test_kassa_summary_lists_debtors_and_skips_teachers(env):
    m = _month()
    env["payments"].mark_paid(env["chat"]["id"], env["s1"]["id"], m, 120, marked_by=env["boss"]["id"])
    r = env["client"].get("/live/kassa", params={"month": m}, headers=_auth(env["boss"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["expected"] == 240 and body["collected"] == 120 and body["outstanding"] == 120
    assert [d["display_name"] for d in body["debtors"]] == ["Murad"]
    assert body["by_chat"][0]["students"] == 2


def test_kassa_rejects_bad_month(env):
    r = env["client"].get("/live/kassa", params={"month": "2026-13"}, headers=_auth(env["boss"]))
    assert r.status_code == 422


def test_expense_add_list_delete(env):
    m = _month()
    c, h = env["client"], _auth(env["boss"])
    r = c.post("/live/kassa/expenses", json={"month": m, "category": "İcarə", "amount": 400, "note": " ofis "},
               headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["note"] == "ofis"
    body = c.get("/live/kassa", params={"month": m}, headers=h).json()
    assert body["expenses_total"] == 400 and body["net"] == -400
    assert c.delete(f"/live/kassa/expenses/{r.json()['id']}", headers=h).status_code == 204
    assert c.get("/live/kassa", params={"month": m}, headers=h).json()["expenses_total"] == 0


def test_expense_validation(env):
    h = _auth(env["boss"])
    bad = [{"month": "2026-11", "category": "Yemək", "amount": 10},
           {"month": "2026-11", "category": "İcarə", "amount": 0}]
    for body in bad:
        assert env["client"].post("/live/kassa/expenses", json=body, headers=h).status_code == 422


def test_teacher_cannot_delete_expense(env):
    e = env["payments"].add_expense(env["course"]["id"], "2026-11", "Reklam", 50, "", env["boss"]["id"])
    r = env["client"].delete(f"/live/kassa/expenses/{e['id']}", headers=_auth(env["teacher"]))
    assert r.status_code == 403
    assert env["payments"].get_expense(e["id"]) is not None


def test_admin_marks_paid_without_being_chat_member(env):
    m = _month()
    body = {"chat_id": env["chat"]["id"], "student_id": env["s2"]["id"], "month": m}
    r = env["client"].post("/live/kassa/mark", json=body, headers=_auth(env["boss"]))
    assert r.status_code == 204, r.text
    paid = env["payments"].list_payments_for_chat(env["chat"]["id"], m)
    assert paid[env["s2"]["id"]]["amount"] == 120


def test_mark_rejects_non_member_student(env):
    body = {"chat_id": env["chat"]["id"], "student_id": env["boss"]["id"], "month": _month()}
    assert env["client"].post("/live/kassa/mark", json=body, headers=_auth(env["boss"])).status_code == 404


def test_teacher_cannot_mark_via_kassa(env):
    body = {"chat_id": env["chat"]["id"], "student_id": env["s2"]["id"], "month": _month()}
    assert env["client"].post("/live/kassa/mark", json=body, headers=_auth(env["teacher"])).status_code == 403


def test_remind_writes_to_class_chat(env):
    body = {"chat_id": env["chat"]["id"], "student_id": env["s2"]["id"], "month": "2026-11"}
    r = env["client"].post("/live/kassa/remind", json=body, headers=_auth(env["boss"]))
    assert r.status_code == 204, r.text
    text = env["messages"].list_by_chat(env["chat"]["id"])[-1]["content"]
    assert "Murad" in text and "120 AZN" in text and "2026-11" in text


# ---------- qəbz oxuyucusu (addım 5) ----------

def test_match_receipt_needs_first_name_and_prefers_same_family():
    people = [
        Enrollment(1, "A", 1, "Aysel Məmmədova", "2026-09-01T00:00:00+00:00", 120),
        Enrollment(2, "B", 2, "Aysel Quliyeva", "2026-09-01T00:00:00+00:00", 100),
        Enrollment(1, "A", 3, "Murad Quliyev", "2026-09-01T00:00:00+00:00", 120),
    ]
    assert kassa.match_receipt(None, "X", people) == []
    assert [e.student_id for e in kassa.match_receipt("aysel", None, people)] == [1, 2]
    # Ödəyən «QULIYEV» (bank SMS-i latın böyük hərflə): qızın soyadı «Quliyeva».
    assert [e.student_id for e in kassa.match_receipt("Aysel", "RAUF QULIYEV", people)] == [2, 1]
    assert kassa.match_receipt("Leyla", None, people) == []


def test_receipt_month_handles_year_boundary():
    assert kassa.receipt_month(1, "2026-12-28", "2026-12-30") == "2027-01"
    assert kassa.receipt_month(12, "2027-01-03", "2027-01-05") == "2026-12"
    assert kassa.receipt_month(11, None, "2026-11-15") == "2026-11"
    assert kassa.receipt_month(None, "2026-10-02", "2026-11-15") == "2026-10"


def test_receipt_endpoint_returns_candidates_and_writes_nothing(env):
    from pipeline.receipt_reader import read_receipt
    from server.app import get_receipt_reader

    app.dependency_overrides[get_receipt_reader] = lambda: (lambda text: read_receipt(text, None))
    text = "Salam müəllim, Ayselin noyabr pulunu köçürdüm, 120 AZN. *4417 kartından."
    r = env["client"].post("/live/kassa/receipt", json={"text": text}, headers=_auth(env["boss"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["found"] and body["source"] == "rules"
    assert body["amount"] == 120 and body["student"] == "Aysel" and body["card_last4"] == "4417"
    assert body["month"].endswith("-11")
    assert [c["student_id"] for c in body["candidates"]] == [env["s1"]["id"]]
    assert body["candidates"][0]["monthly_amount"] == 120 and body["candidates"][0]["paid"] is False
    assert env["payments"].list_records_for_chats([env["chat"]["id"]], "2000-01", "2100-12") == []

    env["payments"].mark_paid(env["chat"]["id"], env["s1"]["id"], body["month"], 120,
                              marked_by=env["boss"]["id"])
    again = env["client"].post("/live/kassa/receipt", json={"text": text}, headers=_auth(env["boss"]))
    assert again.json()["candidates"][0]["paid"] is True

    empty = env["client"].post("/live/kassa/receipt", json={"text": "salam, sabah gələcəyik"},
                               headers=_auth(env["boss"]))
    assert empty.json() == {**empty.json(), "found": False, "source": "none", "candidates": []}


def test_receipt_endpoint_is_admin_only(env):
    body = {"text": "120 AZN Aysel"}
    assert env["client"].post("/live/kassa/receipt", json=body).status_code == 401
    assert env["client"].post("/live/kassa/receipt", json=body,
                              headers=_auth(env["teacher"])).status_code == 403
    assert env["client"].post("/live/kassa/receipt", json={"text": "x" * 4001},
                              headers=_auth(env["boss"])).status_code == 422
