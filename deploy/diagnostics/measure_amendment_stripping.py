"""Düzəliş qeydlərinin çıxarılmasını REAL səhifədə ölçür.

NİYƏ AYRICA SKRİPT: qayda e-qanun-un markup-unu görmədən, yalnız real
sualdakı mətnə baxaraq yazılıb. İşlədiyini iddia etməzdən əvvəl real
səhifədə ölçmək lazımdır — «yəqin işləyir» demirik.

Serverdə işlədilir (şəbəkə oradadır):

    cd /opt/pr-agent/repo/masterai
    .venv/bin/python deploy/diagnostics/measure_amendment_stripping.py \
        https://e-qanun.az/framework/4481

Heç nəyi dəyişmir — yalnız endirir, ölçür və çap edir.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Python `sys.path`-a SKRİPTİN qovluğunu qoyur, cari qovluğu yox — ona
# görə `deploy/diagnostics/`-dən çağırılanda `pipeline` görünmür
# (real serverdə məhz bu xəta alındı). Layihə kökü əl ilə əlavə olunur.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from bs4 import BeautifulSoup

import re

from pipeline.az_legal import AMENDMENT_NUMBER_RE
from pipeline.ingestion import web_extractor


# Tək qalmış Azərbaycan hərfi: «v ə zif ə tutan» naxışı. Bu ölçüdə
# aşkarlandı — mətndə hərflər sözdən ayrılıb.
_BROKEN_SPACING_RE = re.compile(r"(?<= )[əöüçığşƏÖÜÇIĞŞ](?= )")


def _text_without_stripping(html: str) -> str:
    """Qeydlər ÇIXARILMADAN mətn — müqayisə üçün baza.

    `_extract_text()` artıq çıxarır, ona görə onunla ölçmək mənasız
    olardı (əvvəlki diaqnostikada məhz bu səhv edilmişdi: alət öz
    nəticəsini özü ilə müqayisə edirdi və «-20 simvol» kimi mənasız
    rəqəm verirdi)."""
    soup = BeautifulSoup(html, "html.parser")
    web_extractor._remove_strikethrough(soup)
    for tag in soup(["script", "style", "nav", "footer", "header", "button", "aside", "form"]):
        tag.decompose()
    root = soup.find("main") or soup.find("article") or soup
    blocks = [
        block.get_text(" ", strip=True)
        for block in root.find_all(web_extractor._CONTENT_TAGS)
        if block.get_text(strip=True)
    ]
    joined = "\n".join(blocks)
    if len(joined) >= web_extractor._MIN_STATIC_TEXT_LENGTH:
        return joined
    return root.get_text(separator="\n", strip=True)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    url = web_extractor._normalize_url(argv[1])

    print(f"Endirilir: {url}")
    # `extract()`-in ÖZ məntiqi təkrarlanır: qərar HTML uzunluğuna görə
    # YOX, çıxarılan MƏTNİN uzunluğuna görə verilir.
    #
    # Əvvəlki versiyada HTML uzunluğuna baxırdım və nəticədə e-qanun
    # səhifəsində cəmi 7 simvol mətnlə ölçü aparıldı — yəni ölçü heç
    # baş tutmadı, amma çıxış "0% çıxarıldı" deyib uğurlu görünürdü.
    try:
        html = web_extractor._download_static(url)
        before = _text_without_stripping(html)
        if len(before) < web_extractor._MIN_STATIC_TEXT_LENGTH:
            print(f"  statik mətn qısadır ({len(before)} simvol), JS ilə yüklənir...")
            html = web_extractor._download_js_rendered(url)
            before = _text_without_stripping(html)
    except Exception as exc:                                  # noqa: BLE001
        print(f"XƏTA: səhifə endirilmədi: {exc}")
        return 1

    if len(before) < web_extractor._MIN_STATIC_TEXT_LENGTH:
        print()
        print(f"ÖLÇÜ APARILMADI: mətn cəmi {len(before)} simvoldur.")
        print("Səhifə yüklənmirsə qaydanı yoxlamaq mümkün deyil —")
        print("əvvəlcə Chrome problemini həll edin (check_chrome.py).")
        return 1

    # Zəncir ƏL İLƏ təkrarlanmır — pipeline-ın öz funksiyası çağırılır.
    after = web_extractor._clean_legal_text(before)

    hits_before = AMENDMENT_NUMBER_RE.findall(before)
    hits_after = AMENDMENT_NUMBER_RE.findall(after)

    print()
    print("=" * 68)
    print("ÖLÇÜ")
    print("=" * 68)
    print(f"  mətn uzunluğu, əvvəl : {len(before):>8} simvol")
    print(f"  mətn uzunluğu, sonra : {len(after):>8} simvol")
    removed = len(before) - len(after)
    share = removed / len(before) * 100 if before else 0
    print(f"  çıxarılan            : {removed:>8} simvol  ({share:.1f}%)")
    print()
    print(f"  düzəliş nömrəsi, əvvəl: {len(hits_before):>4}")
    print(f"  düzəliş nömrəsi, sonra: {len(hits_after):>4}")

    print()
    print("=" * 68)
    print("SİLİNƏN QEYDLƏRDƏN NÜMUNƏLƏR (ilk 5)")
    print("=" * 68)
    # SİLİNƏN və DƏYİŞDİRİLƏN sətirlər fərqlidir. Əvvəl ikisi
    # qarışdırılırdı və sadəcə ikiqat boşluğu yığışdırılmış adi sətirlər
    # «silinib» kimi göstərilirdi — yanıldıcı idi.
    after_lines = set(after.splitlines())
    removed = [
        line for line in before.splitlines()
        if line not in after_lines and AMENDMENT_NUMBER_RE.search(line)
    ]
    for line in removed[:5]:
        print(f"  - {line[:150]}")
    if not removed:
        print("  (düzəliş nömrəsi olan heç bir sətir silinməyib)")
    if shown == 0:
        print("  (heç nə silinmir — qayda bu səhifədə işləmir, bax aşağı)")

    print()
    print("=" * 68)
    print("AYRI PROBLEM: POZULMUŞ HƏRF ARALIĞI")
    print("=" * 68)
    print("Bu ölçüdə aşkarlandı: mətndə Azərbaycan hərfləri sözdən")
    print("AYRILIB, məsələn «v ə zif ə tutan d ö vl ə t qulluq ç ular ı na».")
    print("Model belə mətni oxuyursa, sual keyfiyyəti ondan zərər görür.")
    print()
    broken = _BROKEN_SPACING_RE.findall(after)
    words = len(after.split())
    print(f"  ayrılmış hərf halı : {len(broken):>7}")
    print(f"  ümumi söz sayı     : {words:>7}")
    if words:
        print(f"  nisbət             : {len(broken) / words * 100:>7.1f}%")
    if broken:
        print()
        print("  nümunələr:")
        for line in after.splitlines():
            if len(_BROKEN_SPACING_RE.findall(line)) >= 3:
                print(f"    - {line[:120]}")
                break

    print()
    print("=" * 68)
    print("SİLİNMƏYƏN, AMMA DÜZƏLİŞ NÖMRƏSİ OLAN HİSSƏLƏR (ilk 5)")
    print("=" * 68)
    print("Bunlar ya əsl hüquqi mətndir (düzgün saxlanılıb), ya da")
    print("qaydanın tutmadığı formadır (düzəliş lazımdır).")
    print()
    shown = 0
    for line in after.splitlines():
        if AMENDMENT_NUMBER_RE.search(line):
            print(f"  - {line[:150]}")
            shown += 1
            if shown >= 5:
                break
    if shown == 0:
        print("  (qalmayıb)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
