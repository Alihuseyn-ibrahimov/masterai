"""VPS diaqnostikası: sayt mətnində ləğv edilmiş (xətt-çəkilmiş) hissələr.

Sandbox-dan e-qanun.az-a çıxış yoxdur, ona görə xəttin real səhifədə
HANSI üsulla verildiyi yalnız VPS-də yoxlana bilər. Bu skript güman
etmir — brauzerin özündən soruşur və nəticəni RƏQƏMLƏ göstərir.

DİQQƏT (bu skriptin ilk versiyasındakı ölçmə səhvi): `_extract_text()`
ÖZÜ də xətt-çəkilmiş teqləri silir, ona görə "təmizləmədən əvvəl"
vəziyyəti almaq üçün `_remove_strikethrough` müvəqqəti SÖNDÜRÜLMƏLİDİR.
Əks halda eyni iki təmizlənmiş mətn müqayisə olunur və fərq ~0 çıxır.

İşlətmək (VPS-də):
    cd /opt/pr-agent/repo/masterai
    .venv/bin/python deploy/diagnostics/check_strikethrough.py https://e-qanun.az/framework/4481
"""

import sys

sys.path.insert(0, ".")

from pipeline.ingestion import web_extractor  # noqa: E402

_SAMPLE_LIMIT = 8
_SNIPPET_LIMIT = 120
_FIND_SAMPLES = 3


def _extract_without_cleaning(html: str) -> str:
    """`_extract_text`-i xətt-təmizləməsi SÖNDÜRÜLMÜŞ halda işlədir."""
    original = web_extractor._remove_strikethrough
    web_extractor._remove_strikethrough = lambda soup: None
    try:
        return web_extractor._extract_text(html)
    finally:
        web_extractor._remove_strikethrough = original


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
        html = driver.page_source
    finally:
        driver.quit()

    dirty = _extract_without_cleaning(html)
    clean = web_extractor._extract_text(html)

    print(f"Xətt-çəkilmiş element sayı: {len(samples)}")
    print(f"Mətn — təmizləmə OLMADAN:   {len(dirty)} simvol")
    print(f"Mətn — təmizləmə İLƏ:       {len(clean)} simvol")
    print(f"ÇIXARILAN (əsas göstərici): {len(dirty) - len(clean)} simvol\n")

    if not samples:
        print("DİQQƏT: heç bir xətt-çəkilmiş element tapılmadı.")
        print("Deməli sayt ləğv edilmiş müddəaları BAŞQA üsulla göstərir")
        print("(məs. rəng, ayrıca qeyd, kursiv).")
        return

    print(f"İlk {min(_SAMPLE_LIMIT, len(samples))} nümunə:")
    for tag_name, class_name, text in samples[:_SAMPLE_LIMIT]:
        snippet = " ".join(text.split())[:_SNIPPET_LIMIT]
        print(f"  <{tag_name.lower()} class={class_name!r}>: {snippet}")

    # Əsl sınaq: ləğv edilmiş konkret ifadələr TƏMİZ mətndə qalıbmı?
    print("\nLəğv edilmiş ifadələrin təmiz mətndə yoxlanışı:")
    checked = 0
    leaked = 0
    for _tag_name, _class_name, text in samples:
        phrase = " ".join(text.split()).strip(" ,.;:")
        if len(phrase) < 25:  # çox qısa parça təsadüfən başqa yerdə ola bilər
            continue
        in_dirty = phrase in " ".join(dirty.split())
        in_clean = phrase in " ".join(clean.split())
        status = "SIZIB (hələ də var!)" if in_clean else "təmizlənib ✓"
        if not in_dirty:
            status += "  [qeyd: təmizlənməmiş mətndə də yox idi]"
        print(f"  {status}: {phrase[:_SNIPPET_LIMIT]}")
        leaked += int(in_clean)
        checked += 1
        if checked >= _FIND_SAMPLES:
            break

    print(f"\nYekun: yoxlanan {checked} ifadədən {leaked} ədədi hələ də mətndədir.")


if __name__ == "__main__":
    main()
