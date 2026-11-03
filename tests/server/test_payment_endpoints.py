"""`/live/chats/{id}/payments*` — Ödəniş izləməsi (Faza 3 PR 3). Əl ilə
qeyd, onlayn kartla ödəniş bu fazada YOX (bax plan sənədi)."""

import pytest
from fastapi.testclient import TestClient

from server.app import (
    app, get_chat_store, get_connection_manager, get_message_store,
    get_payment_store, get_token_secret, get_user_store,
)
from server.auth import create_token
from server.chat_store import ChatStore
from server.connection_manager import ConnectionManager
from server.message_store import MessageStore
from server.payment_store import PaymentStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


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

    client = TestClient(app)
    teacher = users.create("teacher@masternr1.az", "hash", "Müəllim")
    users.set_teacher(teacher["id"], True)
    teacher = users.get_by_id(teacher["id"])
    student = users.create("telebe@masternr1.az", "hash", "Tələbə")
    other_teacher = users.create("basqa@masternr1.az", "hash", "Başqa Müəllim")
    users.set_teacher(other_teacher["id"], True)
    other_teacher = users.get_by_id(other_teacher["id"])
    chat = chats.create(kind="group", created_by=teacher["id"], name="Sinif")
    chats.add_member(chat["id"], teacher["id"])
    chats.add_member(chat["id"], student["id"])

    yield {
        "client": client, "users": users, "chats": chats, "payments": payments,
        "messages": messages, "teacher": teacher, "student": student,
        "other_teacher": other_teacher, "chat": chat,
    }
    app.dependency_overrides.clear()


def _auth(user) -> dict:
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


class TestSetFee:
    def test_requires_auth(self, env):
        r = env["client"].post(
            f"/live/chats/{env['chat']['id']}/payments/fee",
            json={"student_id": env["student"]["id"], "monthly_amount": 30},
        )
        assert r.status_code == 401

    def test_non_teacher_member_gets_403(self, env):
        r = env["client"].post(
            f"/live/chats/{env['chat']['id']}/payments/fee",
            json={"student_id": env["student"]["id"], "monthly_amount": 30},
            headers=_auth(env["student"]),
        )
        assert r.status_code == 403

    def test_teacher_not_a_member_gets_403(self, env):
        r = env["client"].post(
            f"/live/chats/{env['chat']['id']}/payments/fee",
            json={"student_id": env["student"]["id"], "monthly_amount": 30},
            headers=_auth(env["other_teacher"]),
        )
        assert r.status_code == 403

    def test_student_not_in_chat_returns_404(self, env):
        other = env["users"].create("yad@masternr1.az", "hash", "Yad")
        r = env["client"].post(
            f"/live/chats/{env['chat']['id']}/payments/fee",
            json={"student_id": other["id"], "monthly_amount": 30},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 404

    def test_teacher_sets_fee(self, env):
        r = env["client"].post(
            f"/live/chats/{env['chat']['id']}/payments/fee",
            json={"student_id": env["student"]["id"], "monthly_amount": 30},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 200
        assert r.json() == {"student_id": env["student"]["id"], "monthly_amount": 30}


class TestListPayments:
    def test_requires_auth(self, env):
        assert env["client"].get(f"/live/chats/{env['chat']['id']}/payments").status_code == 401

    def test_defaults_to_current_month_and_excludes_teacher(self, env):
        r = env["client"].get(f"/live/chats/{env['chat']['id']}/payments", headers=_auth(env["teacher"]))
        assert r.status_code == 200
        body = r.json()
        assert len(body["rows"]) == 1
        row = body["rows"][0]
        assert row["student_id"] == env["student"]["id"]
        assert row["monthly_amount"] is None
        assert row["paid"] is False

    def test_shows_fee_and_paid_status(self, env):
        env["payments"].set_fee(env["chat"]["id"], env["student"]["id"], 30)
        env["payments"].mark_paid(env["chat"]["id"], env["student"]["id"], "2026-11", 30, marked_by=env["teacher"]["id"])
        r = env["client"].get(f"/live/chats/{env['chat']['id']}/payments?month=2026-11", headers=_auth(env["teacher"]))
        row = r.json()["rows"][0]
        assert row["monthly_amount"] == 30
        assert row["paid"] is True
        assert row["paid_amount"] == 30


class TestMarkPayment:
    def test_falls_back_to_fee_amount_when_not_given(self, env):
        env["payments"].set_fee(env["chat"]["id"], env["student"]["id"], 25)
        r = env["client"].post(
            f"/live/chats/{env['chat']['id']}/payments/mark",
            json={"student_id": env["student"]["id"], "month": "2026-11"},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 200
        assert r.json()["paid_amount"] == 25

    def test_no_fee_and_no_amount_is_400(self, env):
        r = env["client"].post(
            f"/live/chats/{env['chat']['id']}/payments/mark",
            json={"student_id": env["student"]["id"], "month": "2026-11"},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 400

    def test_explicit_amount_overrides_fee(self, env):
        env["payments"].set_fee(env["chat"]["id"], env["student"]["id"], 25)
        r = env["client"].post(
            f"/live/chats/{env['chat']['id']}/payments/mark",
            json={"student_id": env["student"]["id"], "month": "2026-11", "amount": 15},
            headers=_auth(env["teacher"]),
        )
        assert r.json()["paid_amount"] == 15

    def test_invalid_month_format_rejected(self, env):
        r = env["client"].post(
            f"/live/chats/{env['chat']['id']}/payments/mark",
            json={"student_id": env["student"]["id"], "month": "2026-13", "amount": 10},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 422


class TestUnmarkPayment:
    def test_removes_record(self, env):
        env["payments"].mark_paid(env["chat"]["id"], env["student"]["id"], "2026-11", 30, marked_by=env["teacher"]["id"])
        r = env["client"].delete(
            f"/live/chats/{env['chat']['id']}/payments",
            params={"student_id": env["student"]["id"], "month": "2026-11"},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 204
        assert env["payments"].list_payments_for_chat(env["chat"]["id"], "2026-11") == {}


class TestRemindPayment:
    def test_no_fee_is_400(self, env):
        r = env["client"].post(
            f"/live/chats/{env['chat']['id']}/payments/{env['student']['id']}/remind",
            json={"month": "2026-11"},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 400

    def test_posts_reminder_to_class_chat(self, env):
        env["payments"].set_fee(env["chat"]["id"], env["student"]["id"], 30)
        r = env["client"].post(
            f"/live/chats/{env['chat']['id']}/payments/{env['student']['id']}/remind",
            json={"month": "2026-11"},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 204
        msgs = env["messages"].list_by_chat(env["chat"]["id"])
        assert len(msgs) == 1
        assert "30 AZN" in msgs[0]["content"]
        assert "Tələbə" in msgs[0]["content"]
