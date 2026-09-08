from pathlib import Path

import pytest

from pipeline.ingestion import web_extractor
from pipeline.ingestion.errors import IngestionError
from pipeline.models import MaterialSource

FIXTURES = Path(__file__).parent / "fixtures"


def test_extracts_text_and_strips_script_nav_footer(monkeypatch):
    html = (FIXTURES / "sample.html").read_text(encoding="utf-8")
    monkeypatch.setattr(web_extractor, "_download_static", lambda url: html)

    source = MaterialSource(kind="link", location="https://example.az/ders")
    raw = web_extractor.extract(source)

    assert "Konstitusiya" in raw.text
    assert "Baki seheridir" in raw.text
    assert "ignorlanmalidir" not in raw.text


def test_falls_back_to_js_rendering_when_static_text_too_short(monkeypatch):
    monkeypatch.setattr(web_extractor, "_download_static", lambda url: "<html><body></body></html>")
    monkeypatch.setattr(
        web_extractor,
        "_download_js_rendered",
        lambda url: "<html><body><p>" + "JS ile render olunan metn. " * 20 + "</p></body></html>",
    )

    source = MaterialSource(kind="link", location="https://example.az/js-ders")
    raw = web_extractor.extract(source)

    assert "JS ile render olunan metn" in raw.text


def test_extract_text_prefers_main_tag_content_over_surrounding_ui_chrome():
    """Real testdə tapılıb (e-qanun.az): JS-render olunan saytların tab/
    düymə/status mətnləri `<nav>`/`<header>` DEYİL, sadə `<div>`/`<button>`
    elementləridir — bunlar köhnə tag-siyahısı ilə tutulmurdu, nəticədə
    AI sual generasiyası UI mətnindən sual düzəldirdi. `<main>` mövcuddursa
    YALNIZ ondan mətn çıxarılmalıdır."""
    html = (
        "<html><body>"
        "<div>Mətn Şəkil Versiyalar Əlaqəli Sənədlər Qüvvədədir Yüklə</div>"
        "<main><p>Konstitusiyanın 94-cü maddəsi dövlət qulluğunu tənzimləyir.</p></main>"
        "</body></html>"
    )

    text = web_extractor._extract_text(html)

    assert "Konstitusiyanın 94-cü maddəsi" in text
    assert "Qüvvədədir" not in text
    assert "Yüklə" not in text


def test_extract_text_strips_header_button_aside_form():
    html = (
        "<html><body>"
        "<header>Sayt başlığı (ignorlanmalidır)</header>"
        "<button>Yüklə</button>"
        "<aside>Yan panel (ignorlanmalidır)</aside>"
        "<form>Axtarış (ignorlanmalidır)</form>"
        "<p>Əsas məzmun budur.</p>"
        "</body></html>"
    )

    text = web_extractor._extract_text(html)

    assert text == "Əsas məzmun budur."


def test_raises_when_static_fetch_fails(monkeypatch):
    def boom(url):
        raise ConnectionError("saxta şəbəkə xətası")

    monkeypatch.setattr(web_extractor, "_download_static", boom)

    source = MaterialSource(kind="link", location="https://example.az/olu-link")
    with pytest.raises(IngestionError):
        web_extractor.extract(source)


def test_download_static_sends_browser_user_agent(monkeypatch):
    """Wikipedia kimi saytlar `requests`-in defolt UA-sını ("python-
    requests/...") bot kimi tanıyıb 403 qaytarır — real production-da
    tapılıb (bax masterai/CLAUDE.md). Brauzer UA-sı göndərildiyini
    yoxlayır ki, reqressiya olmasın."""
    captured = {}

    class FakeResponse:
        text = "<html><body>ok</body></html>"

        def raise_for_status(self):
            pass

    def fake_get(url, timeout, headers):
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(web_extractor.requests, "get", fake_get)

    web_extractor._download_static("https://az.wikipedia.org/wiki/Test")

    assert "python-requests" not in captured["headers"]["User-Agent"]
    assert "Mozilla" in captured["headers"]["User-Agent"]


def test_raises_when_both_static_and_js_yield_no_text(monkeypatch):
    monkeypatch.setattr(web_extractor, "_download_static", lambda url: "<html><body></body></html>")
    monkeypatch.setattr(web_extractor, "_download_js_rendered", lambda url: "<html><body></body></html>")

    source = MaterialSource(kind="link", location="https://example.az/bos-sehife")
    with pytest.raises(IngestionError):
        web_extractor.extract(source)


class _FakeElement:
    def __init__(self, text: str):
        self.text = text


class _FakeDriver:
    """`document.readyState` və body mətninin ardıcıl oxunuşlarını
    simulyasiya edir — real Selenium sürücüsü olmadan `_wait_for_page_ready`-i
    sınamaq üçün (bax `_wait_for_page_ready`, konkret sayt strukturuna
    bağlı olmayan universal gözləmə)."""

    def __init__(self, ready_states: list[str], body_texts: list[str]):
        self._ready_states = ready_states
        self._body_texts = body_texts
        self.script_calls = 0
        self.body_calls = 0

    def execute_script(self, script: str) -> str:
        value = self._ready_states[min(self.script_calls, len(self._ready_states) - 1)]
        self.script_calls += 1
        return value

    def find_element(self, by, value):
        text = self._body_texts[min(self.body_calls, len(self._body_texts) - 1)]
        self.body_calls += 1
        return _FakeElement(text)


class TestWaitForPageReady:
    def test_returns_once_ready_state_complete_and_body_text_stabilizes(self, monkeypatch):
        monkeypatch.setattr(web_extractor, "_JS_READY_TIMEOUT_SECONDS", 2.0)
        monkeypatch.setattr(web_extractor, "_JS_POLL_INTERVAL_SECONDS", 0.01)
        driver = _FakeDriver(
            ready_states=["loading", "loading", "complete"],
            body_texts=["JS ile render olunan metn"] * 5,
        )

        web_extractor._wait_for_page_ready(driver)

        assert driver.script_calls == 3
        # readyState=='complete' olan kimi, mətn 2 ardıcıl oxunuşda
        # dəyişməzsə dərhal qayıdır — 5 dəfə oxumur.
        assert driver.body_calls == 2

    def test_gives_up_after_timeout_when_text_never_stabilizes(self, monkeypatch):
        monkeypatch.setattr(web_extractor, "_JS_READY_TIMEOUT_SECONDS", 0.05)
        monkeypatch.setattr(web_extractor, "_JS_POLL_INTERVAL_SECONDS", 0.01)

        class _EverGrowingDriver(_FakeDriver):
            def find_element(self, by, value):
                self.body_calls += 1
                return _FakeElement("x" * self.body_calls)  # HƏR oxunuşda fərqli uzunluq

        driver = _EverGrowingDriver(ready_states=["complete"], body_texts=[])

        # sonsuz dövrəyə düşmədən, timeout-dan sonra sükutla qayıtmalıdır
        web_extractor._wait_for_page_ready(driver)

        assert driver.body_calls > 0


def test_download_js_rendered_waits_for_ready_then_returns_page_source(monkeypatch):
    monkeypatch.setattr(web_extractor, "_JS_READY_TIMEOUT_SECONDS", 2.0)
    monkeypatch.setattr(web_extractor, "_JS_POLL_INTERVAL_SECONDS", 0.01)

    quit_calls = []

    class _FakeChromeDriver(_FakeDriver):
        def __init__(self, **_kwargs):
            super().__init__(ready_states=["complete"], body_texts=["sabit metn"] * 3)
            self.page_source = "<html><body>sabit metn</body></html>"
            self.got_url = None

        def get(self, url):
            self.got_url = url

        def quit(self):
            quit_calls.append(True)

    import selenium.webdriver as real_webdriver

    monkeypatch.setattr(real_webdriver, "Chrome", _FakeChromeDriver)

    html = web_extractor._download_js_rendered("https://example.az/spa")

    assert "sabit metn" in html
    assert quit_calls == [True]
