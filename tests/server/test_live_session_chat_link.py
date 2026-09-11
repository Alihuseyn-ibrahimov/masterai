"""Canlı sessiyanın çata bağlanması — store qatı.

NİYƏ: sessiya indiyə qədər HEÇ BİR çata bağlı deyildi (bax
`.planning/.../findings.md` — məhz buna görə liderlik lövhəsi yalnız ev
tapşırığı xallarını sayırdı). Tələbə sessiyaya PIN yazaraq girirdi.
İndi sessiya çatın içindən başlayır: «hansı sinif» sualı çat üzvlüyü ilə
cavablanır.

Sütun NULLABLE-dır (köhnə sessiyalar çatsızdır və tarixçədə oxunmalıdır),
endpoint isə onu MƏCBURİ tələb edir — bu fərq qəsdəndir.
"""

from __future__ import annotations

import sqlite3

from server.live_session_store import LiveSessionStore


class TestSchema:
    def test_new_session_stores_the_chat_and_the_creator(self):
        store = LiveSessionStore(":memory:")
        session = store.create_session(question_set_id=1, chat_id=5, created_by=9)
        assert session["chat_id"] == 5
        assert session["created_by"] == 9

    def test_chat_id_is_optional_at_the_store_level(self):
        """Köhnə çağırışlar (tarixçə testləri, PIN axını) pozulmamalıdır
        — məcburilik ENDPOINT qatındadır, store-da yox."""
        store = LiveSessionStore(":memory:")
        session = store.create_session(question_set_id=1)
        assert session["chat_id"] is None
        assert session["created_by"] is None

    def test_lookup_by_pin_also_returns_the_chat(self):
        """PIN axını Faza 4-də silinir, amma hələ işləkdir — həmin
        yoldan gələn sessiya da çatını daşımalıdır."""
        store = LiveSessionStore(":memory:")
        created = store.create_session(question_set_id=1, chat_id=5, created_by=9)
        found = store.get_by_pin(created["pin"])
        assert found["chat_id"] == 5
        assert found["created_by"] == 9


class TestExistingDatabaseMigration:
    def test_sessions_created_before_the_columns_existed_still_load(self, tmp_path):
        """REAL HAL: canlı bazada onsuz da sessiyalar var. `ALTER TABLE`
        sütunu NULL ilə əlavə edir — köhnə sessiyalar OXUNA BİLMƏLİDİR,
        çünki tələbələrin tarixçəsi onlara söykənir."""
        path = str(tmp_path / "live.db")
        old = sqlite3.connect(path)
        old.executescript(
            """
            CREATE TABLE live_sessions (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                question_set_id         INTEGER NOT NULL,
                pin                     TEXT NOT NULL,
                status                  TEXT NOT NULL,
                current_question_index  INTEGER NOT NULL,
                report_json             TEXT,
                created_at              TEXT NOT NULL
            );
            """
        )
        old.execute(
            "INSERT INTO live_sessions (question_set_id, pin, status, "
            "current_question_index, created_at) VALUES (1, '123456', 'finished', 0, '2026-09-01')"
        )
        old.commit()
        old.close()

        store = LiveSessionStore(path)

        migrated = store.get(1)
        assert migrated is not None, "köhnə sessiya oxunmur"
        assert migrated["chat_id"] is None
        assert migrated["created_by"] is None


class TestActiveSessionForChat:
    def test_returns_the_open_session_of_the_chat(self):
        """`chat.html` bunu göstərir: «sinifdə canlı sessiya var»."""
        store = LiveSessionStore(":memory:")
        session = store.create_session(question_set_id=1, chat_id=5, created_by=9)
        found = store.active_for_chat(5)
        assert found["id"] == session["id"]

    def test_active_session_is_also_returned(self):
        """GEC QOŞULMA üçün vacibdir: sessiya başlayandan sonra da
        çatda görünməlidir, yoxsa gecikən tələbə onu tapa bilməz."""
        store = LiveSessionStore(":memory:")
        session = store.create_session(question_set_id=1, chat_id=5, created_by=9)
        store.start(session["id"], 600)
        assert store.active_for_chat(5)["id"] == session["id"]

    def test_finished_session_is_not_returned(self):
        store = LiveSessionStore(":memory:")
        session = store.create_session(question_set_id=1, chat_id=5, created_by=9)
        store.set_status(session["id"], "finished")
        assert store.active_for_chat(5) is None

    def test_other_chats_are_not_returned(self):
        store = LiveSessionStore(":memory:")
        store.create_session(question_set_id=1, chat_id=5, created_by=9)
        assert store.active_for_chat(6) is None

    def test_chat_without_a_session_returns_none(self):
        assert LiveSessionStore(":memory:").active_for_chat(5) is None

    def test_the_newest_session_wins(self):
        """Müəllim səhvən iki sessiya açsa, çatda SONUNCU göstərilməlidir
        — köhnəsini göstərmək tələbəni yanlış sessiyaya aparardı."""
        store = LiveSessionStore(":memory:")
        store.create_session(question_set_id=1, chat_id=5, created_by=9)
        newer = store.create_session(question_set_id=2, chat_id=5, created_by=9)
        assert store.active_for_chat(5)["id"] == newer["id"]

    def test_a_chatless_session_never_appears(self):
        """Köhnə (PIN) sessiyalarda `chat_id` NULL-dur. SQL-də `= NULL`
        heç vaxt doğru olmur, amma səhv yazılsa bütün çatlara sızardı."""
        store = LiveSessionStore(":memory:")
        store.create_session(question_set_id=1)
        assert store.active_for_chat(5) is None
        assert store.active_for_chat(None) is None
