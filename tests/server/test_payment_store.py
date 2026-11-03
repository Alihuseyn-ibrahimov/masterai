"""`server/payment_store.py` — Ödəniş izləməsi (Faza 3 PR 3)."""

import pytest

from server.payment_store import PaymentStore, current_month


@pytest.fixture
def store():
    return PaymentStore(":memory:")


def test_current_month_format():
    assert len(current_month()) == 7
    assert current_month()[4] == "-"


class TestFee:
    def test_no_fee_by_default(self, store):
        assert store.list_fees_for_chat(1) == {}

    def test_set_and_list(self, store):
        store.set_fee(1, 5, 30)
        assert store.list_fees_for_chat(1) == {5: 30}

    def test_updating_fee_overwrites_not_duplicates(self, store):
        store.set_fee(1, 5, 30)
        store.set_fee(1, 5, 40)
        assert store.list_fees_for_chat(1) == {5: 40}

    def test_does_not_leak_across_chats(self, store):
        store.set_fee(1, 5, 30)
        store.set_fee(2, 5, 50)
        assert store.list_fees_for_chat(1) == {5: 30}
        assert store.list_fees_for_chat(2) == {5: 50}


class TestPaymentRecords:
    def test_empty_by_default(self, store):
        assert store.list_payments_for_chat(1, "2026-11") == {}

    def test_mark_and_list(self, store):
        store.mark_paid(1, 5, "2026-11", 30, marked_by=2)
        rows = store.list_payments_for_chat(1, "2026-11")
        assert rows[5]["amount"] == 30
        assert rows[5]["marked_by"] == 2

    def test_remarking_same_month_overwrites(self, store):
        store.mark_paid(1, 5, "2026-11", 30, marked_by=2)
        store.mark_paid(1, 5, "2026-11", 40, marked_by=3)
        rows = store.list_payments_for_chat(1, "2026-11")
        assert len(rows) == 1
        assert rows[5]["amount"] == 40
        assert rows[5]["marked_by"] == 3

    def test_different_months_are_separate_records(self, store):
        store.mark_paid(1, 5, "2026-10", 30, marked_by=2)
        store.mark_paid(1, 5, "2026-11", 30, marked_by=2)
        assert len(store.list_payments_for_chat(1, "2026-10")) == 1
        assert len(store.list_payments_for_chat(1, "2026-11")) == 1

    def test_unmark_removes_record(self, store):
        store.mark_paid(1, 5, "2026-11", 30, marked_by=2)
        store.unmark_paid(1, 5, "2026-11")
        assert store.list_payments_for_chat(1, "2026-11") == {}

    def test_unmark_unknown_record_is_noop(self, store):
        store.unmark_paid(1, 5, "2026-11")  # heç bir xəta atmır
