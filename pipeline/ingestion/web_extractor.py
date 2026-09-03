import requests
from bs4 import BeautifulSoup

from pipeline.ingestion.errors import IngestionError
from pipeline.models import MaterialSource, RawMaterial

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


def _download_js_rendered(url: str) -> str:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
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
        raise IngestionError(f"Sayt yüklənmədi: {source.location}") from exc

    text = _extract_text(html)

    if len(text) < _MIN_STATIC_TEXT_LENGTH:
        try:
            html = _download_js_rendered(source.location)
        except Exception as exc:
            raise IngestionError(
                f"Sayt JS-rendering ilə də yüklənmədi: {source.location}"
            ) from exc
        text = _extract_text(html)

    if not text.strip():
        raise IngestionError(f"Saytdan mətn çıxarıla bilmədi: {source.location}")

    return RawMaterial(text=text, metadata={"url": source.location})
