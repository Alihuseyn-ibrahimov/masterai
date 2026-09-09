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


# Real diaqnostikada tapıldı: e-qanun səhifələrinin sonunda qanunun
# DƏYİŞİKLİK TARİXÇƏSİ var — "... nömrəli Qanunu ilə ... sözləri
# çıxarılmışdır" tipli annotasiyalar. Bunlar qanunun MƏZMUNU deyil,
# biblioqrafik qeydlərdir, üstəlik ləğv edilmiş ifadələri xətt
# ÇƏKİLMƏDƏN sitat gətirdiyi üçün xətt-təmizləməsindən yan keçir.
# Aşağıdakı işarələr sayta yox, Azərbaycan qanunvericilik mətnlərinin
# standart ifadələrinə əsaslanır.
_HISTORY_MARKERS = (
    "nömrəli azərbaycan respublikasının qanunu",
    "sözləri çıxarılmışdır",
    "sözlər çıxarılmışdır",
    "redaksiyada verilmişdir",
    "qüvvədən düşmüş hesab edilmişdir",
    "istifadə olunmuş mənbə sənədlərinin siyahısı",
    "qanunvericilik toplusu",
    "rəsmi internet saytı",
)


def _measure_amendment_history(text: str) -> None:
    """Dəyişiklik tarixçəsi annotasiyalarının həcmini ölçür."""
    lines = text.split("\n")
    history_chars = sum(
        len(line) for line in lines if any(m in line.lower() for m in _HISTORY_MARKERS)
    )
    history_lines = sum(
        1 for line in lines if any(m in line.lower() for m in _HISTORY_MARKERS)
    )
    total = len(text) or 1

    print("\n--- Dəyişiklik tarixçəsi (qanunun məzmunu DEYİL) ---")
    print(f"  Belə sətir sayı:     {history_lines} / {len(lines)}")
    print(f"  Tutduğu simvol:      {history_chars} ({history_chars * 100 // total}% mətnin)")

    heading = "İSTİFADƏ OLUNMUŞ MƏNBƏ SƏNƏDLƏRİNİN SİYAHISI"
    where = text.upper().find(heading.upper())
    if where >= 0:
        print(f"  \"{heading}\" başlığı {where}-ci simvoldadır,")
        print(f"  ondan sonra {total - where} simvol var ({(total - where) * 100 // total}% mətnin).")
    else:
        print(f"  \"{heading}\" başlığı tapılmadı.")


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

    # Əsl sınaq: ləğv edilmiş ifadə təmiz mətndə qalıbsa, bu İKİ tamam
    # fərqli şeyi ifadə edə bilər və onları yalnız TƏKRAR SAYI ayırır:
    #   dirty=2 → clean=1  : xətt-çəkilmiş nüsxə silinib, sənədin başqa
    #                        yerindəki (xətt çəkilməmiş) nüsxə qalıb — DÜZGÜN
    #   dirty=1 → clean=1  : silinməyib — kodda boşluq var
    normalized_dirty = " ".join(dirty.split())
    normalized_clean = " ".join(clean.split())

    print("\nLəğv edilmiş ifadələrin təkrar sayı (təmizləmədən əvvəl → sonra):")
    checked = 0
    truly_leaked = 0
    for _tag_name, _class_name, text in samples:
        phrase = " ".join(text.split()).strip(" ,.;:")
        if len(phrase) < 25:  # qısa parça təsadüfən başqa yerdə ola bilər
            continue
        before = normalized_dirty.count(phrase)
        after = normalized_clean.count(phrase)

        if after == 0:
            verdict = "tam təmizləndi ✓"
        elif before > after:
            verdict = f"xətt-çəkilmiş nüsxə silindi ✓ (qalan {after} nüsxə xətsizdir)"
        else:
            verdict = "SİLİNMƏYİB ✗ — kodda boşluq"
            truly_leaked += 1

        print(f"\n  {before} → {after}  {verdict}")
        print(f"    ifadə: {phrase[:_SNIPPET_LIMIT]}")

        if after:
            where = normalized_clean.find(phrase)
            context = normalized_clean[max(0, where - 200) : where + len(phrase) + 200]
            print(f"    qalan nüsxənin ətrafı: ...{context}...")

        checked += 1
        if checked >= _FIND_SAMPLES:
            break

    print(f"\nYekun: yoxlanan {checked} ifadədən {truly_leaked} ədədi HƏQİQƏTƏN silinməyib.")

    _measure_amendment_history(clean)


if __name__ == "__main__":
    main()
