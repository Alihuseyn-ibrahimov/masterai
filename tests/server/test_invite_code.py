"""Dəvət kodu — generator və `ChatStore` inteqrasiyası.

NİYƏ KOD LAZIMDIR: çata qoşulma `POST /chats/{id}/join` ilə olurdu və çat
ID-ləri `AUTOINCREMENT`, yəni ARDICIL. Təxmin də lazım deyildi — 1-dən
saymaqla sistemdəki bütün qrup çatlarına girmək olurdu. Təsdiq tək
başına kifayət etmir: ardıcıl ID hər çata istək spam etməyə imkan verir.

Bax `docs/superpowers/specs/2026-09-11-masterai-class-chat-design.md`.
"""

from __future__ import annotations

from server.chat_store import ChatStore
from server.invite_code import CODE_ALPHABET, format_code, generate_code


class TestAlphabet:
    def test_confusable_characters_are_excluded(self):
        """Müəllim kodu sinifə SƏSLƏ deyir. `0/O` və `1/I/L` qarışdırılır,
        ona görə əlifbada olmamalıdır."""
        for char in "0O1IL":
            assert char not in CODE_ALPHABET, f"{char!r} qarışdırıla bilər"

    def test_alphabet_is_uppercase_and_digits_only(self):
        assert CODE_ALPHABET
        assert all(c.isupper() or c.isdigit() for c in CODE_ALPHABET)

    def test_alphabet_has_no_duplicates(self):
        assert len(set(CODE_ALPHABET)) == len(CODE_ALPHABET)

    def test_brute_force_is_infeasible_under_the_rate_limit(self):
        """Kodun uzunluğu TƏK BAŞINA mənalı ölçü deyil - əsl müdafiə
        sürət limitidir (dəqiqədə 5 cəhd, bax spec). Ona görə test
        həmin limit altında kodu tapmağın nə qədər çəkdiyini yoxlayır.

        İlk versiyamda burada «>1 milyard variant» yazmışdım; həmin
        rəqəm nə əlifbadan çıxırdı (31^6 = 887 milyon), nə də real
        təhlükəni ölçürdü."""
        space = len(CODE_ALPHABET) ** 6
        attempts_per_year = 5 * 60 * 24 * 365
        # Orta halda axtarış sahəsinin yarısı gəzilir.
        years = (space / 2) / attempts_per_year
        assert years > 100, f"kod {years:.0f} ilə tapılır - çox qısadır"


class TestGenerator:
    def test_generated_code_has_six_characters(self):
        assert len(generate_code()) == 6

    def test_generated_code_uses_only_the_alphabet(self):
        for _ in range(50):
            assert set(generate_code()) <= set(CODE_ALPHABET)

    def test_codes_differ(self):
        """Qoruyucu: generator sabit dəyər qaytarsa, bütün çatlar eyni
        kodu alardı və test bunu görməzdi."""
        assert len({generate_code() for _ in range(50)}) > 40

    def test_random_source_can_be_injected(self):
        """Test determinizmi üçün — real istifadədə `secrets` işlədilir."""
        assert generate_code(choose=lambda seq: seq[0]) == CODE_ALPHABET[0] * 6


class TestFormatting:
    def test_code_is_shown_in_two_groups(self):
        """`K7M3QX` yox, `K7M-3QX` — səslə deyiləndə qrup ayrımı kömək edir."""
        assert format_code("K7M3QX") == "K7M-3QX"

    def test_formatting_is_only_for_display(self):
        """Saxlanan dəyər defissizdir; format yalnız göstərişdədir."""
        assert format_code("ABCDEF") == "ABC-DEF"
        assert len(format_code("ABCDEF").replace("-", "")) == 6


class TestChatStoreIntegration:
    def test_new_chat_gets_an_invite_code(self):
        chats = ChatStore(":memory:")
        chat = chats.create(kind="group", created_by=1, name="11-A")
        assert chat["invite_code"]
        assert len(chat["invite_code"]) == 6

    def test_codes_are_unique_across_chats(self):
        chats = ChatStore(":memory:")
        codes = {
            chats.create(kind="group", created_by=1, name=f"S{i}")["invite_code"]
            for i in range(30)
        }
        assert len(codes) == 30

    def test_chat_can_be_found_by_code(self):
        chats = ChatStore(":memory:")
        chat = chats.create(kind="group", created_by=1, name="11-A")
        found = chats.get_by_invite_code(chat["invite_code"])
        assert found is not None
        assert found["id"] == chat["id"]

    def test_lookup_is_case_insensitive(self):
        """Tələbə kodu kiçik hərflə yaza bilər - bu, səhv sayılmamalıdır."""
        chats = ChatStore(":memory:")
        chat = chats.create(kind="group", created_by=1, name="11-A")
        assert chats.get_by_invite_code(chat["invite_code"].lower()) is not None

    def test_lookup_ignores_the_display_hyphen(self):
        """Müəllim ekranda `K7M-3QX` görür və tələbə onu olduğu kimi yazır."""
        chats = ChatStore(":memory:")
        chat = chats.create(kind="group", created_by=1, name="11-A")
        assert chats.get_by_invite_code(format_code(chat["invite_code"])) is not None

    def test_lookup_ignores_surrounding_spaces(self):
        chats = ChatStore(":memory:")
        chat = chats.create(kind="group", created_by=1, name="11-A")
        assert chats.get_by_invite_code(f"  {chat['invite_code']}  ") is not None

    def test_unknown_code_returns_none(self):
        chats = ChatStore(":memory:")
        chats.create(kind="group", created_by=1, name="11-A")
        assert chats.get_by_invite_code("ZZZZZZ") is None

    def test_empty_code_returns_none(self):
        """Boş sətir bütün çatları qaytarmamalıdır."""
        chats = ChatStore(":memory:")
        chats.create(kind="group", created_by=1, name="11-A")
        assert chats.get_by_invite_code("") is None
        assert chats.get_by_invite_code(None) is None

    def test_code_can_be_regenerated(self):
        """Kod sinifdən kənara çıxsa (şəkil, ekran paylaşımı) müəllim
        onu yeniləyir - köhnə kod dərhal işləməz olur."""
        chats = ChatStore(":memory:")
        chat = chats.create(kind="group", created_by=1, name="11-A")
        old = chat["invite_code"]

        new = chats.regenerate_invite_code(chat["id"])

        assert new != old
        assert chats.get_by_invite_code(old) is None
        assert chats.get_by_invite_code(new)["id"] == chat["id"]

    def test_direct_chats_have_no_invite_code(self):
        """Şəxsi çata kod ilə qoşulmaq anlayışı yoxdur."""
        chats = ChatStore(":memory:")
        chat = chats.create(kind="direct", created_by=1)
        assert chat["invite_code"] is None


class TestExistingDatabaseMigration:
    def test_chats_created_before_the_column_existed_get_a_code(self, tmp_path):
        """REAL HAL: canlı bazada artıq çatlar var. `ALTER TABLE` sütunu
        NULL ilə əlavə edir - backfill olmasa həmin çatlara heç vaxt
        qoşulmaq olmazdı."""
        import sqlite3

        path = str(tmp_path / "chats.db")
        # Köhnə sxemi əl ilə qururuq: `invite_code` sütunu YOXDUR.
        old = sqlite3.connect(path)
        old.executescript(
            """
            CREATE TABLE chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                name TEXT,
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE chat_members (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                joined_at TEXT NOT NULL,
                PRIMARY KEY (chat_id, user_id)
            );
            """
        )
        old.execute(
            "INSERT INTO chats (kind, name, created_by, created_at) "
            "VALUES ('group', 'Köhnə sinif', 1, '2026-09-01')"
        )
        old.commit()
        old.close()

        chats = ChatStore(path)

        migrated = chats.get(1)
        assert migrated["invite_code"], "köhnə çat kodsuz qaldı"
        assert chats.get_by_invite_code(migrated["invite_code"])["id"] == 1

    def test_existing_members_are_untouched(self, tmp_path):
        """Miqrasiya heç kimi çatdan ÇIXARMAMALIDIR."""
        import sqlite3

        path = str(tmp_path / "chats.db")
        old = sqlite3.connect(path)
        old.executescript(
            """
            CREATE TABLE chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                name TEXT,
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE chat_members (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                joined_at TEXT NOT NULL,
                PRIMARY KEY (chat_id, user_id)
            );
            """
        )
        old.execute(
            "INSERT INTO chats (kind, name, created_by, created_at) "
            "VALUES ('group', 'Köhnə sinif', 1, '2026-09-01')"
        )
        for user_id in (1, 2, 3):
            old.execute(
                "INSERT INTO chat_members (chat_id, user_id, joined_at) "
                "VALUES (1, ?, '2026-09-01')",
                (user_id,),
            )
        old.commit()
        old.close()

        chats = ChatStore(path)

        assert sorted(chats.list_member_ids(1)) == [1, 2, 3]
