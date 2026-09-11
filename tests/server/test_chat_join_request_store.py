"""Çata qoşulma istəyi — store qatı.

NİYƏ BU CƏDVƏL VAR: əvvəl `POST /chats/{id}/join` heç nə soruşmadan üzv
əlavə edirdi və çat ID-ləri ARDICIL idi. İndi qoşulma iki addımdır:
tələbə kod ilə istək göndərir, çatı yaradan təsdiqləyir.

`PRIMARY KEY (chat_id, user_id)` qəsdəndir — rədd edilən tələbə yenidən
istək göndərəndə köhnə sətir YENİLƏNİR. Müəllim səhvən rədd etsə,
tələbə həmişəlik bloklanmır.

Bax `docs/superpowers/specs/2026-09-11-masterai-class-chat-design.md`.
"""

from __future__ import annotations

import threading

from server.chat_join_request_store import (
    STATUS_APPROVED,
    STATUS_DECLINED,
    STATUS_PENDING,
    ChatJoinRequestStore,
)


def _store() -> ChatJoinRequestStore:
    return ChatJoinRequestStore(":memory:")


class TestStatusValues:
    def test_statuses_are_azerbaijani(self):
        """`HomeworkReportRow`-dakı eyni naxış — statuslar birbaşa
        istifadəçiyə göstərilir, tərcümə qatı yoxdur."""
        assert STATUS_PENDING == "gözləyir"
        assert STATUS_APPROVED == "təsdiqləndi"
        assert STATUS_DECLINED == "rədd edildi"


class TestRequesting:
    def test_new_request_is_pending(self):
        store = _store()
        row = store.request(chat_id=1, user_id=7)
        assert row["status"] == STATUS_PENDING
        assert row["chat_id"] == 1
        assert row["user_id"] == 7
        assert row["created_at"]
        assert row["decided_at"] is None
        assert row["decided_by"] is None

    def test_request_can_be_read_back(self):
        store = _store()
        store.request(chat_id=1, user_id=7)
        assert store.get(1, 7)["status"] == STATUS_PENDING

    def test_unknown_request_is_none(self):
        store = _store()
        assert store.get(1, 7) is None

    def test_repeating_a_pending_request_does_not_duplicate(self):
        """Tələbə düyməyə iki dəfə basa bilər — müəllimin siyahısında
        iki sətir görünməməlidir."""
        store = _store()
        store.request(chat_id=1, user_id=7)
        store.request(chat_id=1, user_id=7)
        assert len(store.list_pending(1)) == 1

    def test_requesting_again_after_decline_reopens_the_request(self):
        """Əsas qayda: rədd BLOKLAMA deyil. Müəllim səhvən rədd etsə,
        tələbə yenidən istək göndərə bilməlidir."""
        store = _store()
        store.request(chat_id=1, user_id=7)
        store.decline(chat_id=1, user_id=7, decided_by=1)

        store.request(chat_id=1, user_id=7)

        row = store.get(1, 7)
        assert row["status"] == STATUS_PENDING
        assert row["decided_at"] is None, "köhnə qərar təmizlənməyib"
        assert row["decided_by"] is None
        assert [r["user_id"] for r in store.list_pending(1)] == [7]

    def test_requesting_again_after_approval_keeps_the_approval(self):
        """Təsdiqlənmiş üzv təkrar istək göndərsə (köhnə tab, geri
        düyməsi) statusu GERİ QAYITMAMALIDIR — əks halda müəllimin
        siyahısına onsuz da üzv olan adam düşərdi."""
        store = _store()
        store.request(chat_id=1, user_id=7)
        store.approve(chat_id=1, user_ids=[7], decided_by=1)

        row = store.request(chat_id=1, user_id=7)

        assert row["status"] == STATUS_APPROVED
        assert store.list_pending(1) == []


class TestPendingList:
    def test_only_pending_rows_are_listed(self):
        store = _store()
        for user_id in (7, 8, 9):
            store.request(chat_id=1, user_id=user_id)
        store.approve(chat_id=1, user_ids=[8], decided_by=1)
        store.decline(chat_id=1, user_id=9, decided_by=1)

        assert [r["user_id"] for r in store.list_pending(1)] == [7]

    def test_pending_list_is_ordered_oldest_first(self):
        """Müəllim ekranda kimin əvvəl istədiyini görür — «ilk gələn»
        sıralaması adildir."""
        store = _store()
        for user_id in (7, 8, 9):
            store.request(chat_id=1, user_id=user_id)
        assert [r["user_id"] for r in store.list_pending(1)] == [7, 8, 9]

    def test_chats_do_not_share_requests(self):
        store = _store()
        store.request(chat_id=1, user_id=7)
        store.request(chat_id=2, user_id=8)
        assert [r["user_id"] for r in store.list_pending(1)] == [7]
        assert [r["user_id"] for r in store.list_pending(2)] == [8]

    def test_empty_chat_has_no_pending_requests(self):
        assert _store().list_pending(1) == []


class TestApproval:
    def test_approving_records_who_and_when(self):
        store = _store()
        store.request(chat_id=1, user_id=7)

        store.approve(chat_id=1, user_ids=[7], decided_by=42)

        row = store.get(1, 7)
        assert row["status"] == STATUS_APPROVED
        assert row["decided_by"] == 42
        assert row["decided_at"]

    def test_bulk_approval_returns_the_users_it_changed(self):
        """İlk dərs ssenarisi: müəllim «Hamısını təsdiqlə» basır.
        Çağıran qaytarılan siyahıya görə çata üzv əlavə edir — ona görə
        REAL dəyişilənlər qayıtmalıdır."""
        store = _store()
        for user_id in (7, 8, 9):
            store.request(chat_id=1, user_id=user_id)

        approved = store.approve(chat_id=1, user_ids=[7, 8, 9], decided_by=1)

        assert sorted(approved) == [7, 8, 9]
        assert store.list_pending(1) == []

    def test_approving_someone_who_never_requested_changes_nothing(self):
        """Uydurma `user_id` ilə sorğu göndərilə bilər — təsdiq YALNIZ
        mövcud gözləyən istək üzərində işləməlidir."""
        store = _store()
        store.request(chat_id=1, user_id=7)

        approved = store.approve(chat_id=1, user_ids=[7, 999], decided_by=1)

        assert approved == [7]
        assert store.get(1, 999) is None

    def test_approving_twice_is_idempotent(self):
        store = _store()
        store.request(chat_id=1, user_id=7)
        store.approve(chat_id=1, user_ids=[7], decided_by=1)

        assert store.approve(chat_id=1, user_ids=[7], decided_by=1) == []
        assert store.get(1, 7)["status"] == STATUS_APPROVED

    def test_approval_does_not_reach_into_another_chat(self):
        """`chat_id` süzgəci olmasa, bir çatın sahibi başqa çatın
        istəyini təsdiqləyə bilərdi."""
        store = _store()
        store.request(chat_id=1, user_id=7)
        store.request(chat_id=2, user_id=7)

        store.approve(chat_id=1, user_ids=[7], decided_by=1)

        assert store.get(2, 7)["status"] == STATUS_PENDING

    def test_declined_request_is_not_approved_in_bulk(self):
        """«Hamısını təsdiqlə» yalnız GÖZLƏYƏNLƏRƏ aiddir — köhnə
        siyahı ilə göndərilən sorğu rədd edilmiş adamı geri
        gətirməməlidir."""
        store = _store()
        store.request(chat_id=1, user_id=7)
        store.decline(chat_id=1, user_id=7, decided_by=1)

        assert store.approve(chat_id=1, user_ids=[7], decided_by=1) == []
        assert store.get(1, 7)["status"] == STATUS_DECLINED

    def test_empty_approval_list_is_safe(self):
        store = _store()
        store.request(chat_id=1, user_id=7)
        assert store.approve(chat_id=1, user_ids=[], decided_by=1) == []
        assert store.get(1, 7)["status"] == STATUS_PENDING


class TestDecline:
    def test_declining_records_who_and_when(self):
        store = _store()
        store.request(chat_id=1, user_id=7)

        assert store.decline(chat_id=1, user_id=7, decided_by=42) is True

        row = store.get(1, 7)
        assert row["status"] == STATUS_DECLINED
        assert row["decided_by"] == 42
        assert row["decided_at"]

    def test_declining_a_missing_request_returns_false(self):
        assert _store().decline(chat_id=1, user_id=7, decided_by=1) is False

    def test_declining_an_approved_request_returns_false(self):
        """Çıxarma ayrıca əməliyyatdır — «rədd» təsdiqlənmiş üzvü
        çatdan atmır, ona görə bu keçid BAĞLIDIR."""
        store = _store()
        store.request(chat_id=1, user_id=7)
        store.approve(chat_id=1, user_ids=[7], decided_by=1)

        assert store.decline(chat_id=1, user_id=7, decided_by=1) is False
        assert store.get(1, 7)["status"] == STATUS_APPROVED


class TestPersistence:
    def test_rows_survive_a_reopen(self, tmp_path):
        """Servis restart olanda gözləyən istəklər İTMƏMƏLİDİR."""
        path = str(tmp_path / "join.db")
        store = ChatJoinRequestStore(path)
        store.request(chat_id=1, user_id=7)

        reopened = ChatJoinRequestStore(path)

        assert [r["user_id"] for r in reopened.list_pending(1)] == [7]


class TestThreadSafety:
    def test_concurrent_requests_do_not_corrupt_the_table(self):
        """`check_same_thread=False` bağlantını thread-safe ETMİR (bax
        `user_store.py` modul qeydi) — real WebSocket testində bu,
        sqlite korlanmasına səbəb olmuşdu.

        DÜRÜSTLÜK QEYDİ: bu test EHTİMALİDİR, zəmanət deyil — yarış
        şəraiti hər icrada baş vermir. Kilidi söndürüb ölçdüm: sadə
        `Thread.start()` ilə 5 icradan yalnız 1-i tuturdu. `Barrier`
        thread-ləri EYNİ ANDA buraxır və thread sayı artırılıb — tutma
        faizi bununla xeyli qalxır (ölçü `progress.md`-dədir). Yenə də
        bu testin yaşıl olması kilidin varlığını İSBAT ETMİR; kilid
        qaydası koddadır, test yalnız açıq pozuntunu tutur.
        """
        store = _store()
        thread_count = 40
        gate = threading.Barrier(thread_count)
        errors: list[Exception] = []

        def worker(user_id: int) -> None:
            gate.wait()
            try:
                store.request(chat_id=1, user_id=user_id)
            except Exception as exc:  # noqa: BLE001 — testin özü səbəbi göstərir
                errors.append(exc)

        threads = [
            threading.Thread(target=worker, args=(i,)) for i in range(thread_count)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == [], f"kilid işləmir: {errors}"
        assert len(store.list_pending(1)) == thread_count
