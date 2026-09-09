"""VPS diaqnostikası: sayt mətnində ləğv edilmiş (xətt-çəkilmiş) hissələr.

Sandbox-dan e-qanun.az-a çıxış yoxdur, ona görə xəttin real səhifədə
HANSI üsulla verildiyi yalnız VPS-də yoxlana bilər. Bu skript güman
etmir — brauzerin özündən soruşur və nəticəni RƏQƏMLƏ göstərir.

İşlətmək (VPS-də):
    cd /opt/pr-agent/repo/masterai
    .venv/bin/python deploy/diagnostics/check_strikethrough.py https://e-qanun.az/framework/4481
"""

import sys

sys.path.insert(0, ".")

from pipeline.ingestion import web_extractor  # noqa: E402

_SAMPLE_LIMIT = 8
_SNIPPET_LIMIT = 120


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "https://e-qanun.az/framework/4481"
    url = web_extractor._normalize_url(url)
    print(f"URL: {url}\n")

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        web_extractor._wait_for_page_ready(driver)

        # Silməzdən ƏVVƏL: xətt-çəkilmiş elementlərin mətnini topla.
        samples = driver.execute_script(
            """
            const found = [];
            for (const el of document.body.querySelectorAll('*')) {
              const style = window.getComputedStyle(el);
              const decoration = style.textDecorationLine || style.textDecoration || '';
              if (decoration.includes('line-through')) {
                found.push([el.tagName, el.className, (el.innerText || '').trim()]);
              }
            }
            return found;
            """
        )
        html_before = driver.page_source
        text_before = web_extractor._extract_text(html_before)

        removed = driver.execute_script(web_extractor._REMOVE_LINE_THROUGH_JS)
        text_after = web_extractor._extract_text(driver.page_source)
    finally:
        driver.quit()

    print(f"Xətt-çəkilmiş element sayı: {len(samples)}")
    print(f"Silinən element sayı:       {removed}")
    print(f"Mətn uzunluğu (əvvəl):      {len(text_before)} simvol")
    print(f"Mətn uzunluğu (sonra):      {len(text_after)} simvol")
    print(f"Çıxarılan:                  {len(text_before) - len(text_after)} simvol\n")

    if not samples:
        print("DİQQƏT: heç bir xətt-çəkilmiş element tapılmadı.")
        print("Deməli sayt ləğv edilmiş müddəaları BAŞQA üsulla göstərir")
        print("(məs. rəng, ayrıca qeyd, kursiv) — aşağıdakı nümunələrə bax.")
        return

    print(f"İlk {min(_SAMPLE_LIMIT, len(samples))} nümunə:")
    for tag_name, class_name, text in samples[:_SAMPLE_LIMIT]:
        snippet = " ".join(text.split())[:_SNIPPET_LIMIT]
        print(f"  <{tag_name.lower()} class={class_name!r}>: {snippet}")


if __name__ == "__main__":
    main()
