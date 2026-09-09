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


def test_extract_text_ignores_bare_div_span_ui_labels_not_inside_main():
    """Real testdə (e-qanun.az) tapılıb: status/tab etiketləri (məs.
    "Qüvvədədir") `<main>` DAXİLİNDƏ, sadə `<div>`/`<span>` kimi ola bilər
    (SPA bütün alət panelini məzmunla EYNİ konteynerdə saxlayır) — `<main>`
    süzgəci təkbaşına kifayət etmir, məzmun YALNIZ `<p>`/başlıq/siyahı kimi
    teqlərdən toplanmalıdır."""
    html = (
        "<html><body><main>"
        "<div>Mətn</div><div>Şəkil</div><span>Qüvvədədir</span><button>Yüklə</button>"
        "<h1>Dövlət qulluğu haqqında</h1>"
        "<p>" + "Bu qanun dövlət qulluğunun əsaslarını müəyyən edir. " * 5 + "</p>"
        "</main></body></html>"
    )

    text = web_extractor._extract_text(html)

    assert "Dövlət qulluğu haqqında" in text
    assert "dövlət qulluğunun əsaslarını" in text
    assert "Qüvvədədir" not in text
    assert "Yüklə" not in text
    assert "Mətn" not in text.split("\n")


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


def test_raises_when_js_rendered_page_yields_only_a_short_ui_shell(monkeypatch):
    """Real testdə tapılıb (e-qanun.az): JS-render bəzən yalnız kiçik bir
    "qabıq" (başlıq/status/düymə, ~50-60 simvol) qaytarır, əsl sənəd mətni
    heç yüklənmir — bu boş DEYİL, ona görə köhnə `not text.strip()`
    yoxlaması bunu keçirdi. Aydın xəta atılmalıdır, keyfiyyətsiz
    materialdan sual generasiya olunmamalıdır."""
    monkeypatch.setattr(web_extractor, "_download_static", lambda url: "<html><body></body></html>")
    monkeypatch.setattr(
        web_extractor,
        "_download_js_rendered",
        lambda url: "<html><body><p>926-IQ - Dövlət qulluğu haqqında</p>"
        "<span>Qüvvədədir</span><button>Yüklə</button></body></html>",
    )

    source = MaterialSource(kind="link", location="https://e-qanun.az/framework/4481")
    with pytest.raises(IngestionError, match="kifayət qədər mətn"):
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
        stable_text = "JS ile render olunan metn. " * 15  # > _JS_MIN_CONTENT_LENGTH (300)
        driver = _FakeDriver(
            ready_states=["loading", "loading", "complete"],
            body_texts=[stable_text] * (web_extractor._JS_STABLE_READS_REQUIRED + 2),
        )

        web_extractor._wait_for_page_ready(driver)

        assert driver.script_calls == 3
        # readyState=='complete' olan kimi, mətn `_JS_STABLE_READS_REQUIRED`
        # ardıcıl oxunuşda dəyişməzsə (VƏ kifayət qədər uzundursa) dərhal
        # qayıdır — bütün body_texts siyahısını oxumur.
        assert driver.body_calls == web_extractor._JS_STABLE_READS_REQUIRED + 1

    def test_does_not_stop_early_on_a_short_stable_shell(self, monkeypatch):
        """Real testdə tapılıb (e-qanun.az): səhifə ƏVVƏLCƏ kiçik, sabit bir
        "qabıq" göstərir (başlıq/status/düymə), əsl mətn SONRA gəlir — qısa
        mətn sabit qalsa belə, `_JS_MIN_CONTENT_LENGTH`-ə çatmayınca "hazır"
        elan edilməməlidir."""
        monkeypatch.setattr(web_extractor, "_JS_READY_TIMEOUT_SECONDS", 0.05)
        monkeypatch.setattr(web_extractor, "_JS_POLL_INTERVAL_SECONDS", 0.01)
        short_shell_text = "926-IQ - Dövlət qulluğu haqqında Qüvvədədir Yüklə"  # < 300
        driver = _FakeDriver(ready_states=["complete"], body_texts=[short_shell_text])

        web_extractor._wait_for_page_ready(driver)

        # Timeout-a qədər davamlı oxumağa çalışıb (erkən qayıtmayıb).
        assert driver.body_calls > web_extractor._JS_STABLE_READS_REQUIRED

    def test_gives_up_after_timeout_when_text_never_stabilizes(self, monkeypatch):
        monkeypatch.setattr(web_extractor, "_JS_READY_TIMEOUT_SECONDS", 0.05)
        monkeypatch.setattr(web_extractor, "_JS_POLL_INTERVAL_SECONDS", 0.01)

        class _EverGrowingDriver(_FakeDriver):
            def find_element(self, by, value):
                self.body_calls += 1
                return _FakeElement("x" * self.body_calls * 100)  # HƏR oxunuşda fərqli uzunluq

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
            stable_text = "sabit metn. " * 30  # > _JS_MIN_CONTENT_LENGTH (300)
            super().__init__(ready_states=["complete"], body_texts=[stable_text] * 6)
            self.page_source = f"<html><body>{stable_text}</body></html>"
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


class TestNormalizeUrl:
    """Real production-da tapılıb: müəllim host konsoluna linki
    `e-qanun.az/framework/4481` kimi (sxemsiz) yazdı — `requests` bunu
    "Invalid URL ...: No scheme supplied" ilə rədd etdi və material
    "Uğursuz oldu" statusuna düşdü. Brauzerə ünvan yazanda heç kim
    `https://` yazmır; bu, istifadəçi səhvi deyil, bizim qəbul
    etməli olduğumuz normal giriş formasıdır."""

    def test_adds_https_to_scheme_less_url(self):
        assert (
            web_extractor._normalize_url("e-qanun.az/framework/4481")
            == "https://e-qanun.az/framework/4481"
        )

    def test_keeps_existing_https_scheme(self):
        assert (
            web_extractor._normalize_url("https://e-qanun.az/framework/4481")
            == "https://e-qanun.az/framework/4481"
        )

    def test_keeps_existing_http_scheme_untouched(self):
        """`http://` qəsdən `https://`-ə ÇEVRİLMİR — bəzi saytlar yalnız
        HTTP-də işləyir, istifadəçinin açıq seçimi pozulmamalıdır."""
        assert web_extractor._normalize_url("http://example.az/ders") == "http://example.az/ders"

    def test_strips_surrounding_whitespace(self):
        """Kopyala-yapışdır zamanı boşluq/sətir sonu asanlıqla düşür."""
        assert web_extractor._normalize_url("  e-qanun.az/framework/4481\n") == (
            "https://e-qanun.az/framework/4481"
        )

    def test_adds_https_to_www_prefixed_url(self):
        assert web_extractor._normalize_url("www.example.az") == "https://www.example.az"


def test_extract_normalizes_scheme_less_location_before_download(monkeypatch):
    """`extract()` sxemsiz linki HƏM statik yükləməyə, HƏM də nəticə
    metadatasına normallaşdırılmış formada ötürməlidir."""
    requested = {}

    def fake_download(url):
        requested["url"] = url
        return "<html><body><p>" + "Qanunun mətni buradadır. " * 20 + "</p></body></html>"

    monkeypatch.setattr(web_extractor, "_download_static", fake_download)

    source = MaterialSource(kind="link", location="e-qanun.az/framework/4481")
    raw = web_extractor.extract(source)

    assert requested["url"] == "https://e-qanun.az/framework/4481"
    assert raw.metadata["url"] == "https://e-qanun.az/framework/4481"


def test_extract_normalizes_scheme_less_location_for_js_fallback(monkeypatch):
    """JS-render ehtiyat yolu da eyni normallaşdırılmış URL-i almalıdır —
    əks halda statik yol düzəlir, Selenium yolu isə sınıq qalır."""
    requested = {}

    monkeypatch.setattr(web_extractor, "_download_static", lambda url: "<html><body></body></html>")

    def fake_js(url):
        requested["url"] = url
        return "<html><body><p>" + "JS ile gelen qanun metni. " * 20 + "</p></body></html>"

    monkeypatch.setattr(web_extractor, "_download_js_rendered", fake_js)

    source = MaterialSource(kind="link", location="e-qanun.az/framework/4481")
    web_extractor.extract(source)

    assert requested["url"] == "https://e-qanun.az/framework/4481"
