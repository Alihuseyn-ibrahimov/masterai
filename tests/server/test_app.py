import pytest
from fastapi.testclient import TestClient

from server.app import app, get_token_secret, get_user_store
from server.auth import verify_token
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


@pytest.fixture
def client():
    store = UserStore(":memory:")
    app.dependency_overrides[get_user_store] = lambda: store
    app.dependency_overrides[get_token_secret] = lambda: _SECRET
    yield TestClient(app)
    app.dependency_overrides.clear()



def _default_course_code() -> str:
    """Qeydiyyat qapalıdır (kurs kodu məcburi) — bu testlər mövcud
    kurs #1-ə qeydiyyatdan keçir. Store testin override-ındadır."""
    return app.dependency_overrides[get_user_store]().courses.get(1)["join_code"]

def _register(client, email="ali@example.com", password="Parol1234", display_name="Əli"):
    return client.post(
        "/auth/register",
        json={"email": email, "password": password, "display_name": display_name,
              "course_code": _default_course_code()},
    )


class TestRegister:
    def test_returns_token_and_user(self, client):
        r = _register(client)
        assert r.status_code == 201
        body = r.json()
        assert body["token"]
        assert body["user"]["email"] == "ali@example.com"
        assert body["user"]["display_name"] == "Əli"
        assert body["user"]["is_teacher"] is False
        assert body["user"]["is_admin"] is False

    def test_password_hash_never_returned(self, client):
        r = _register(client)
        assert "password_hash" not in r.json()["user"]

    def test_token_is_valid_and_decodes_to_user_id(self, client):
        body = _register(client).json()
        user_id = verify_token(body["token"], secret=_SECRET)
        assert user_id == body["user"]["id"]

    def test_duplicate_email_409(self, client):
        _register(client)
        assert _register(client).status_code == 409

    def test_duplicate_is_case_insensitive(self, client):
        _register(client, email="ali@example.com")
        assert _register(client, email="ALI@Example.com").status_code == 409

    def test_invalid_email_422(self, client):
        assert _register(client, email="bu-email-deyil").status_code == 422

    def test_short_password_422(self, client):
        assert _register(client, password="123").status_code == 422


class TestLogin:
    def test_correct_credentials_return_token(self, client):
        _register(client, email="ali@example.com", password="Parol1234")
        r = client.post("/auth/login", json={"email": "ali@example.com", "password": "Parol1234"})
        assert r.status_code == 200
        assert r.json()["token"]
        assert r.json()["user"]["is_teacher"] is False
        assert r.json()["user"]["is_admin"] is False

    def test_wrong_password_401(self, client):
        _register(client, email="ali@example.com", password="Parol1234")
        r = client.post("/auth/login", json={"email": "ali@example.com", "password": "Səhvdir1"})
        assert r.status_code == 401

    def test_unknown_email_401_same_message_as_wrong_password(self, client):
        _register(client, email="ali@example.com", password="Parol1234")
        wrong_pw = client.post(
            "/auth/login", json={"email": "ali@example.com", "password": "Səhvdir1"}
        )
        unknown_email = client.post(
            "/auth/login", json={"email": "yoxdur@example.com", "password": "Parol1234"}
        )
        assert wrong_pw.status_code == unknown_email.status_code == 401
        assert wrong_pw.json()["detail"] == unknown_email.json()["detail"]


class TestHealth:
    def test_returns_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


class TestCors:
    """Host konsolu (`app/` veb build-i) brauzerdə işlədiyi üçün CORS
    header-ləri lazımdır — bax Faza 4 real testində tapılan "bağlantı
    xətası" bug-ı, `masterai/CLAUDE.md`."""

    def test_allows_any_origin_on_actual_request(self, client):
        r = client.get("/health", headers={"Origin": "http://localhost:62270"})
        assert r.headers["access-control-allow-origin"] == "*"

    def test_preflight_allows_post_with_authorization_header(self, client):
        r = client.options(
            "/live/question-sets",
            headers={
                "Origin": "http://localhost:62270",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        assert r.status_code == 200
        assert r.headers["access-control-allow-origin"] == "*"


class TestLoggingConfiguration:
    """Real production-da tapılıb: `llm_ok provider=...` (INFO) heç vaxt
    jurnalda görünmürdü, çünki logging konfiqurasiyası yox idi və root
    logger WARNING-də qalırdı — hansı LLM provayderin cavab verdiyini
    öyrənmək mümkün deyildi."""

    def test_configures_root_logger_at_info_by_default(self, monkeypatch):
        import logging

        from server.app import _configure_logging

        monkeypatch.delenv("LOG_LEVEL", raising=False)
        root = logging.getLogger()
        original_level = root.level
        try:
            root.setLevel(logging.WARNING)
            _configure_logging()
            assert root.level == logging.INFO
        finally:
            root.setLevel(original_level)

    def test_log_level_env_var_overrides_default(self, monkeypatch):
        import logging

        from server.app import _configure_logging

        monkeypatch.setenv("LOG_LEVEL", "WARNING")
        root = logging.getLogger()
        original_level = root.level
        try:
            _configure_logging()
            assert root.level == logging.WARNING
        finally:
            root.setLevel(original_level)

    def test_provider_info_log_is_emitted_after_configuration(self, monkeypatch, caplog):
        """Əsl sınaq: konfiqurasiyadan sonra `llm_ok` HƏQİQƏTƏN yazılır."""
        import logging

        from pipeline.providers import complete_with_fallback_detail
        from server.app import _configure_logging

        monkeypatch.delenv("LOG_LEVEL", raising=False)
        root = logging.getLogger()
        original_level = root.level
        try:
            root.setLevel(logging.WARNING)
            _configure_logging()
            with caplog.at_level(logging.INFO, logger="masterai.pipeline.providers"):
                complete_with_fallback_detail(
                    "sistem", "sual", ["groq"], {"groq": lambda s, u: "cavab"}
                )
            assert "llm_ok provider=groq" in caplog.text
        finally:
            root.setLevel(original_level)

    def test_noisy_third_party_loggers_are_quieted(self, monkeypatch):
        """INFO-nu açmaq httpx/selenium kimi kitabxanaların hər sorğusunu
        jurnala tökməməlidir — əks halda VPS-in onsuz da dolu diski
        jurnalla dolar (bax masterai/CLAUDE.md, disk hadisəsi)."""
        import logging

        from server.app import _configure_logging

        monkeypatch.delenv("LOG_LEVEL", raising=False)
        _configure_logging()

        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("selenium").level == logging.WARNING

    def test_configuration_logs_its_own_proof_line(self, monkeypatch, caplog):
        """Real VPS-də tapıldı: restartdan sonra jurnalda yalnız
        gunicorn-un öz INFO mesajları görünürdü (o, onsuz da INFO-da
        idi) — bizim konfiqurasiyanın işlədiyini TƏSDİQLƏYƏN heç nə yox
        idi. İndi konfiqurasiya özü bir sətir yazır ki, hər restart
        özünü sübut etsin."""
        import logging

        from server.app import _configure_logging

        monkeypatch.delenv("LOG_LEVEL", raising=False)
        root = logging.getLogger()
        original_level = root.level
        try:
            root.setLevel(logging.WARNING)
            with caplog.at_level(logging.INFO, logger="server.app"):
                _configure_logging()
            assert "logging_configured level=INFO" in caplog.text
        finally:
            root.setLevel(original_level)
