import time

import requests
from bs4 import BeautifulSoup

from pipeline.ingestion.errors import IngestionError
from pipeline.models import MaterialSource, RawMaterial

# JS-render olunan (SPA/React/Angular) saytlarda məzmun səhifə açılandan
# BİR NEÇƏ SANİYƏ sonra DOM-a əlavə olunur — dərhal `page_source` oxumaq
# boş/natamam mətnə səbəb olur (real production-da tapılıb, bax
# masterai/CLAUDE.md). `_wait_for_page_ready` bunu universal şəkildə
# (konkret sayt strukturuna bağlı olmadan) gözləyir.
_JS_READY_TIMEOUT_SECONDS = 10.0
_JS_POLL_INTERVAL_SECONDS = 0.5

# Bu həddən az mətn statik HTML-in əsasən JS ilə doldurulduğuna işarədir —
# belə hallarda Selenium ilə render olunmuş səhifəyə keçilir.
_MIN_STATIC_TEXT_LENGTH = 100

# Bəzi saytlar (məs. Wikipedia) `requests`-in defolt User-Agent-ini
# ("python-requests/...") bot kimi tanıyıb 403 ilə rədd edir — real
# production-da (bax masterai/CLAUDE.md, "Dərs: real material
# uğursuzluğu") brauzer kimi tanınan bir UA ilə eyni sorğu 200 qaytardı.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )
}


def _download_static(url: str) -> str:
    response = requests.get(url, timeout=15, headers=_BROWSER_HEADERS)
    response.raise_for_status()
    return response.text


def _wait_for_page_ready(driver) -> None:
    """İki mərhələli, konkret sayt strukturuna bağlı OLMAYAN gözləmə:
    (1) brauzerin öz `document.readyState`-i, (2) body mətninin
    sabitləşməsi — ardıcıl 2 ölçmədə uzunluq dəyişməzsə, SPA-nın data
    fetch-inin bitdiyi qəbul edilir. Maksimum `_JS_READY_TIMEOUT_SECONDS`
    sonra, hələ dəyişirsə belə, olan vəziyyət qəbul edilir (sonsuz
    gözləmənin qarşısını almaq üçün)."""
    from selenium.webdriver.common.by import By

    deadline = time.monotonic() + _JS_READY_TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        if driver.execute_script("return document.readyState") == "complete":
            break
        time.sleep(_JS_POLL_INTERVAL_SECONDS)

    previous_length = None
    while time.monotonic() < deadline:
        current_length = len(driver.find_element(By.TAG_NAME, "body").text)
        if previous_length is not None and current_length == previous_length:
            return
        previous_length = current_length
        time.sleep(_JS_POLL_INTERVAL_SECONDS)


def _download_js_rendered(url: str) -> str:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    # Kiçik VPS-lərdə (az RAM) `/dev/shm` adətən çox kiçikdir (real
    # production-da tapılıb — "session not created: DevToolsActivePort
    # file doesn't exist") — Chrome-u `/tmp`-a keçirir, paylaşılan
    # yaddaş məhdudiyyətindən asılı olmur.
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        _wait_for_page_ready(driver)
        return driver.page_source
    finally:
        driver.quit()


def _extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def extract(source: MaterialSource) -> RawMaterial:
    try:
        html = _download_static(source.location)
    except Exception as exc:
        # `{exc}` bilərəkdən mesaja daxil edilir — əvvəllər əsl səbəb
        # (məs. Selenium/Chrome xətası) heç yerdə görünmürdü, yalnız
        # `from exc` ilə traceback-ə zəncirlənirdi, amma bunu heç kim
        # loglamırdı (bax `server/app.py`, `_process_material`-a
        # `logger.exception` əlavəsi) — istifadəçi/loqlarda dərhal görünsün.
        raise IngestionError(f"Sayt yüklənmədi: {source.location} ({exc})") from exc

    text = _extract_text(html)

    if len(text) < _MIN_STATIC_TEXT_LENGTH:
        try:
            html = _download_js_rendered(source.location)
        except Exception as exc:
            raise IngestionError(
                f"Sayt JS-rendering ilə də yüklənmədi: {source.location} ({exc})"
            ) from exc
        text = _extract_text(html)

    if not text.strip():
        raise IngestionError(f"Saytdan mətn çıxarıla bilmədi: {source.location}")

    return RawMaterial(text=text, metadata={"url": source.location})
