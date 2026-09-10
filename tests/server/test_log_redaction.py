"""Jurnalda token maskalanması.

BİLİNƏN RİSK İDİ (bax `masterai/CLAUDE.md`, «Bilinən risklər»): brauzerin
WebSocket API-si custom header dəstəkləmir, ona görə JWT query param-da
göndərilir (`?token=...`). Real smoke testində uvicorn access log-unda
TAM TOKEN açıq mətn kimi göründüyü təsdiqləndi — istifadəçinin öz VPS
jurnalında da eyni sətir görüldü (2026-09-10):

    WebSocket /ws/live/347489/host?token=eyJhbGciOiJIUzI1NiIs... 403

Jurnal diskdə QALIR və `journalctl` ilə oxunur; oradan götürülmüş token
istifadəçinin hesabına tam giriş verir (bizim tokenlərin ömrü 90 gündür).

Bu modul həmin sızmanı bağlayır. QEYD: bu, tokenin URL-də olmasını
aradan qaldırmır — o, ayrıca iş üçün açıq qalır (qısaömürlü WS «ticket»,
bax CLAUDE.md). Burada həll olunan, tokenin DİSKDƏ SAXLANMASIDIR.
"""

import logging

from server.log_redaction import RedactSecretsFilter, redact_secrets


class TestRedactSecrets:
    def test_token_query_param_is_masked(self):
        line = "WebSocket /ws/live/347489/host?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc 403"
        assert redact_secrets(line) == "WebSocket /ws/live/347489/host?token=*** 403"

    def test_other_query_params_survive(self):
        line = "GET /live/question-sets?id=18&token=eyJabc&limit=5"
        assert redact_secrets(line) == "GET /live/question-sets?id=18&token=***&limit=5"

    def test_bearer_header_value_is_masked(self):
        line = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc"
        assert redact_secrets(line) == "Authorization: Bearer ***"

    def test_ticket_and_key_names_are_masked_too(self):
        assert redact_secrets("?ticket=abc123") == "?ticket=***"
        assert redact_secrets("?api_key=abc123") == "?api_key=***"
        assert redact_secrets("X-Admin-Key: hunter2") == "X-Admin-Key: ***"

    def test_text_without_secrets_is_untouched(self):
        line = "GET /health 200"
        assert redact_secrets(line) is line or redact_secrets(line) == line

    def test_case_is_ignored(self):
        assert redact_secrets("?TOKEN=abc") == "?TOKEN=***"

    def test_empty_and_none_do_not_crash(self):
        assert redact_secrets("") == ""
        assert redact_secrets(None) is None


class TestFilterOnRealRecords:
    """uvicorn access log-u mesajı `record.args` ilə qurur, `record.msg`
    isə yalnız formatdır — maskalama HƏR İKİSİNƏ tətbiq olunmalıdır,
    əks halda filtr «işləyir» görünüb heç nə etməz."""

    def _formatted(self, record: logging.LogRecord) -> str:
        RedactSecretsFilter().filter(record)
        return record.getMessage()

    def test_secret_inside_args_is_masked(self):
        record = logging.LogRecord(
            "uvicorn.access", logging.INFO, __file__, 1,
            '%s - "%s %s HTTP/%s" %d',
            ("127.0.0.1:1", "GET", "/ws/chat/5?token=eyJsecret", "1.1", 403),
            None,
        )
        message = self._formatted(record)
        assert "eyJsecret" not in message
        assert "token=***" in message

    def test_secret_inside_msg_is_masked(self):
        record = logging.LogRecord(
            "uvicorn.error", logging.INFO, __file__, 1,
            "connection rejected /ws/live/1/host?token=eyJsecret", None, None,
        )
        assert "eyJsecret" not in self._formatted(record)

    def test_non_string_args_do_not_crash(self):
        record = logging.LogRecord(
            "x", logging.INFO, __file__, 1, "%d items in %s", (5, None), None,
        )
        assert "5 items" in self._formatted(record)

    def test_dict_args_are_handled(self):
        """`logger.info("%(a)s", {"a": ...})` formasında args dict olur.

        DİQQƏT: `LogRecord`-a dict TUPLE-un içində verilir - `logger`-in
        özü belə ötürür. Birbaşa dict versək `LogRecord.__init__` onu
        args[0] kimi oxumağa çalışıb KeyError verir (bu testi yazarkən
        məhz o səhvə düşdüm)."""
        record = logging.LogRecord(
            "x", logging.INFO, __file__, 1, "%(url)s", ({"url": "/x?token=eyJsecret"},), None,
        )
        assert "eyJsecret" not in self._formatted(record)

    def test_filter_always_returns_true(self):
        """Filtr sətri GİZLƏTMİR, yalnız təmizləyir - jurnal sətirləri
        itməməlidir."""
        record = logging.LogRecord("x", logging.INFO, __file__, 1, "salam", None, None)
        assert RedactSecretsFilter().filter(record) is True


class TestInstallationTarget:
    """REQRESSİYA QORUYUCUSU — ilk versiyam məhz burada sındı.

    Filtri yalnız root HANDLER-inə qoşmuşdum. Vahid testlər keçirdi,
    amma real icrada token jurnalda TAM göründü, çünki:

      - `uvicorn.access` `propagate = False`-dur və öz handler-i var,
        yəni sətir root handler-inə heç vaxt çatmır;
      - `UvicornWorker` (production-da gunicorn ilə) həmin logger-in
        `handlers`-ini tamamilə əvəz edir.

    Hər iki halda LOGGER-ə qoşulan filtr sağ qalır. Bu test filtrin
    məhz orada olduğunu yoxlayır.
    """

    def test_filter_is_on_the_uvicorn_access_logger(self):
        from server import app as app_module  # `install_redaction()` idxalda çağırılır

        assert app_module is not None
        access = logging.getLogger("uvicorn.access")
        assert any(isinstance(f, RedactSecretsFilter) for f in access.filters), (
            "filtr `uvicorn.access` LOGGER-ində deyil - handler-ə qoşulubsa "
            "real access log-unda İŞLƏMƏYƏCƏK"
        )

    def test_filter_survives_handler_replacement(self):
        """`UvicornWorker.__init__` `logger.handlers = ...` edir - filtr
        itməməlidir."""
        from server.log_redaction import install_redaction

        access = logging.getLogger("uvicorn.access")
        install_redaction()
        access.handlers = [logging.StreamHandler()]   # worker-in etdiyi
        assert any(isinstance(f, RedactSecretsFilter) for f in access.filters)

    def test_install_is_idempotent(self):
        from server.log_redaction import install_redaction

        access = logging.getLogger("uvicorn.access")
        before = len([f for f in access.filters if isinstance(f, RedactSecretsFilter)])
        install_redaction()
        install_redaction()
        after = len([f for f in access.filters if isinstance(f, RedactSecretsFilter)])
        assert before == after == 1
