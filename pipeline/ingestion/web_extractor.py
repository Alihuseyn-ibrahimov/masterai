import logging
import re
import time

import requests
from bs4 import BeautifulSoup

from pipeline.az_legal import AMENDMENT_NUMBER_RE
from pipeline.ingestion.errors import IngestionError
from pipeline.models import MaterialSource, RawMaterial

logger = logging.getLogger("masterai.pipeline.web_extractor")

# JS-render olunan (SPA/React/Angular) saytlarda məzmun səhifə açılandan
# BİR NEÇƏ SANİYƏ sonra DOM-a əlavə olunur — dərhal `page_source` oxumaq
# boş/natamam mətnə səbəb olur (real production-da tapılıb, bax
# masterai/CLAUDE.md). `_wait_for_page_ready` bunu universal şəkildə
# (konkret sayt strukturuna bağlı olmadan) gözləyir.
_JS_READY_TIMEOUT_SECONDS = 25.0
_JS_POLL_INTERVAL_SECONDS = 1.0
# Real testdə (e-qanun.az) tapılıb: bəzi SPA-lar ƏVVƏLCƏ kiçik bir
# "qabıq" (başlıq/status/düymə) göstərir, əsl sənəd mətni isə bir qədər
# GECİKMƏ ilə (ayrıca API sorğusu) gəlir — "ardıcıl 2 ölçmə dəyişmirsə
# sabitdir" qaydası bu qabığı səhvən "hazır" kimi qəbul edirdi. İndi
# sabitlik YALNIZ mətn bu minimum uzunluğa çatdıqdan SONRA (VƏ bir neçə
# ardıcıl ölçmədə dəyişmirsə) elan olunur.
_JS_STABLE_READS_REQUIRED = 3
_JS_MIN_CONTENT_LENGTH = 300

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


# Real production-da tapılıb: müəllim linki brauzerdəki kimi, sxemsiz
# (`e-qanun.az/framework/4481`) yazır — `requests` bunu "No scheme
# supplied" ilə rədd edir və material "Uğursuz oldu" statusuna düşür.
# Sxemi olan linklərə (`http://` daxil) TOXUNULMUR.
_URL_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://")


def _normalize_url(url: str) -> str:
    """Sxemsiz ünvana `https://` əlavə edir, artıq sxemi olanı olduğu
    kimi saxlayır. Kopyala-yapışdır boşluqları da təmizlənir."""
    url = url.strip()
    if _URL_SCHEME_RE.match(url):
        return url
    return f"https://{url}"


def _download_static(url: str) -> str:
    response = requests.get(url, timeout=15, headers=_BROWSER_HEADERS)
    response.raise_for_status()
    return response.text


def _wait_for_page_ready(driver) -> None:
    """İki mərhələli, konkret sayt strukturuna bağlı OLMAYAN gözləmə:
    (1) brauzerin öz `document.readyState`-i, (2) body mətninin
    sabitləşməsi — ardıcıl `_JS_STABLE_READS_REQUIRED` ölçmədə uzunluq
    dəyişməzsə VƏ mətn `_JS_MIN_CONTENT_LENGTH`-ə çatıbsa, SPA-nın data
    fetch-inin bitdiyi qəbul edilir. Maksimum `_JS_READY_TIMEOUT_SECONDS`
    sonra, hələ dəyişirsə/kifayət qədər uzun olmasa belə, olan vəziyyət
    qəbul edilir (sonsuz gözləmənin qarşısını almaq üçün)."""
    from selenium.webdriver.common.by import By

    deadline = time.monotonic() + _JS_READY_TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        if driver.execute_script("return document.readyState") == "complete":
            break
        time.sleep(_JS_POLL_INTERVAL_SECONDS)

    previous_length = None
    stable_count = 0
    while time.monotonic() < deadline:
        current_length = len(driver.find_element(By.TAG_NAME, "body").text)
        if previous_length is not None and current_length == previous_length:
            stable_count += 1
            if stable_count >= _JS_STABLE_READS_REQUIRED and current_length >= _JS_MIN_CONTENT_LENGTH:
                return
        else:
            stable_count = 0
        previous_length = current_length
        time.sleep(_JS_POLL_INTERVAL_SECONDS)


# Real production-da tapılıb (e-qanun.az, "Dövlət qulluğu haqqında"):
# hüquqi mətnlərdə LƏĞV EDİLMİŞ müddəalar silinmir, üstündən xətt
# çəkilərək saxlanılır — AI isə bunu qüvvədə olan müddəa kimi oxuyub
# yanlış "düzgün cavab" düzəldirdi. Xəttin necə verildiyi (teq, inline
# stil, sinif, xarici CSS faylı) HTML-ə baxmaqla həmişə bilinmir, ona
# görə brauzerin özündən `getComputedStyle` ilə soruşulur — bu, sayta
# xas heç bir fərziyyə tələb etmir.
# `<html>`/`<body>` qəsdən kənarda saxlanılır: nəzəri olaraq xətt bütöv
# konteynerə verilsə, bütün səhifəni silmək olmaz.
_REMOVE_LINE_THROUGH_JS = """
const doomed = [];
for (const el of document.body.querySelectorAll('*')) {
  const style = window.getComputedStyle(el);
  const decoration = style.textDecorationLine || style.textDecoration || '';
  if (decoration.includes('line-through')) {
    doomed.push(el);
  }
}
for (const el of doomed) {
  el.remove();
}
return doomed.length;
"""

# Chrome-un başlama parametrləri.
#
# Real produksiyada ölçülüb: 19 sual dəstindən 6-sı uğursuz olub və
# onların 4-ü eyni səbəbdəndir — "session not created:
# DevToolsActivePort file doesn't exist", yəni Chrome start zamanı ölür.
# Server 512 MB RAM-lıdır (yaddaş 80%, swap 49%) və EYNİ URL bəzən
# işləyir, bəzən yox — deməli səbəb daimi konfiqurasiya deyil, YADDAŞ
# TƏZYİQİDİR.
#
# `--no-sandbox` və `--disable-dev-shm-usage` əvvəlki nasazlıqdan
# qalıb və saxlanılır. Qalanları yaddaş iştahını azaldır.
_CHROME_ARGUMENTS = (
    "--headless=new",
    "--no-sandbox",
    # `/dev/shm` kiçik VPS-lərdə çox darısqaldır — Chrome `/tmp`-a keçir.
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-software-rasterizer",
    # Qanun mətnindən sual qururuq; şəkillər HEÇ VAXT lazım deyil, amma
    # dekodlanmaları yaddaşın böyük hissəsini yeyir. Ən təsirli bayraq.
    "--blink-settings=imagesEnabled=false",
    # Hər iframe üçün ayrıca renderer prosesi 512 MB-da dözülməzdir.
    "--renderer-process-limit=1",
    "--disable-features=site-per-process",
    "--disable-extensions",
    "--disable-background-networking",
    "--window-size=1280,1024",
)

# Yaddaş təzyiqi dəyişkəndir (serverdə başqa servislər də var), ona görə
# bir uğursuzluq son söz deyil. Az sayda cəhd + gözləmə: sonsuz təkrar
# fon emalını dondurar.
_CHROME_START_ATTEMPTS = 3
_CHROME_RETRY_DELAY_SECONDS = 3.0


def _chrome_arguments() -> tuple[str, ...]:
    return _CHROME_ARGUMENTS


def _start_driver(factory, sleeper=time.sleep):
    """Chrome-u işə salır, uğursuz olsa gözləyib təkrar cəhd edir."""
    from selenium.webdriver.chrome.options import Options

    last_error: Exception | None = None
    for attempt in range(1, _CHROME_START_ATTEMPTS + 1):
        options = Options()
        for argument in _chrome_arguments():
            options.add_argument(argument)
        try:
            return factory(options=options)
        except Exception as exc:                                # noqa: BLE001
            last_error = exc
            logger.warning(
                "chrome_start_failed attempt=%s/%s error=%s",
                attempt, _CHROME_START_ATTEMPTS, exc,
            )
            if attempt < _CHROME_START_ATTEMPTS:
                sleeper(_CHROME_RETRY_DELAY_SECONDS * attempt)
    assert last_error is not None
    raise last_error


def _download_js_rendered(url: str) -> str:
    from selenium import webdriver

    driver = _start_driver(webdriver.Chrome)
    try:
        driver.get(url)
        _wait_for_page_ready(driver)
        removed = driver.execute_script(_REMOVE_LINE_THROUGH_JS)
        if removed:
            logger.info("line_through_removed count=%s url=%s", removed, url)
        return driver.page_source
    finally:
        driver.quit()


# Real testdə (e-qanun.az) tapılıb: tab/status/düymə mətnləri (məs.
# "Qüvvədədir", "Yüklə") adətən sadə `<div>`/`<span>` daxilindədir —
# nə `<nav>`/`<header>` kimi tag-lə, nə də `<main>` xaricində olması ilə
# fərqlənir (SPA-lar bütün UI-ni, alət panelini DAXİL, `<main>`-ə qoya
# bilər). Əsl sənəd mətni demək olar HƏMİŞƏ paraqraf/başlıq/siyahı
# teqlərindədir (`<p>`, `<li>`, `<h1-6>`, cədvəl xanaları) — UI
# etiketləri isə adətən bunlarda DEYİL. Ona görə YALNIZ bu teqlərdən
# mətn toplamaq, minimal (yeni asılılıq tələb etməyən) boilerplate-
# təmizləmə həllidir.
_CONTENT_TAGS = ["p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th", "blockquote"]


# Statik (JS-siz) HTML üçün eyni qorunma — brauzer olmadığından
# `getComputedStyle` mümkün deyil, ona görə xəttin üç adi verilmə üsulu
# ayrıca tutulur: (1) semantik teqlər, (2) `style` atributu, (3)
# səhifənin ÖZ `<style>` blokunda `line-through` təyin edən sinif adları
# (sinif adları koda yazılmır, hər səhifədən oxunur).
_STRIKETHROUGH_TAGS = ["s", "strike", "del"]
_LINE_THROUGH_CSS_CLASS_RE = re.compile(r"\.([A-Za-z_][A-Za-z0-9_-]*)")


def _line_through_class_names(soup) -> set[str]:
    names: set[str] = set()
    for style_tag in soup.find_all("style"):
        css = style_tag.get_text()
        for rule in css.split("}"):
            if "line-through" not in rule.lower():
                continue
            selector = rule.rsplit("{", 1)[0]
            names.update(_LINE_THROUGH_CSS_CLASS_RE.findall(selector))
    return names


def _remove_strikethrough(soup) -> None:
    """Ləğv edilmiş (üstündən xətt çəkilmiş) müddəaları sənəddən çıxarır."""
    struck_classes = _line_through_class_names(soup)

    for tag in soup(_STRIKETHROUGH_TAGS):
        tag.decompose()

    for tag in soup.find_all(style=True):
        if "line-through" in tag["style"].lower():
            tag.decompose()

    if struck_classes:
        for tag in soup.find_all(class_=True):
            if struck_classes.intersection(tag.get("class", [])):
                tag.decompose()


# ---- Düzəliş qeydləri -------------------------------------------------------
# e-qanun səhifələrində hər dəyişdirilmiş bənddən sonra mötərizədə qeyd
# durur: «(7 dekabr 2007-ci il tarixli 504-IIIQD nömrəli Qanunla əlavə
# edilmişdir)». Bu, hüquqi mətn deyil, redaksiya tarixçəsidir — model
# oradan sual qurur və sual imtahan üçün dəyərsiz çıxır (real dəst 18,
# sual 5-də təsdiqləndi).
#
# ƏSAS RİSK ÇOX SİLMƏKDİR. Qanun maddəsinin özü heç vaxt itməməlidir,
# ona görə:
#   - yalnız MÖTƏRİZƏ/KVADRAT MÖTƏRİZƏ içindəki hissə silinir,
#   - içərisi qısadırsa (yəni sırf qeyddirsə) silinir; uzun və məzmunlu
#     mötərizə SAXLANILIR, düzəliş nömrəsi olsa belə.
# Bir qeydi buraxmaq bir hökmü itirməkdən yaxşıdır.

# Ayırıcı şərt. Yalnız uzunluğa baxmaq AZDIR — testdə göründü ki,
# məzmunlu mötərizə ilə düzəliş qeydi uzunluqda üst-üstə düşür və əsl
# hökm silinirdi. Ona görə iki yol:
#   a) mötərizə çox qısadır (sırf istinad ola bilər), və ya
#   b) düzəliş qeydinin öz FORMASI var: «... tarixli ... nömrəli ...».
# Hər iki halda düzəliş nömrəsi də olmalıdır.
_ANNOTATION_SHORT_LENGTH = 60
_ANNOTATION_MAX_LENGTH = 160
_AMENDMENT_SHAPE_WORDS = ("tarixli", "nömrəli")
_BRACKETED_RE = re.compile(r"[(\[]([^()\[\]]*)[)\]]")


def _looks_like_amendment_note(inner: str) -> bool:
    if not AMENDMENT_NUMBER_RE.search(inner):
        return False
    if len(inner) <= _ANNOTATION_SHORT_LENGTH:
        return True
    lowered = inner.casefold()
    has_shape = all(word in lowered for word in _AMENDMENT_SHAPE_WORDS)
    return has_shape and len(inner) <= _ANNOTATION_MAX_LENGTH


def _strip_amendment_annotations(text: str) -> str:
    def replace(match: re.Match) -> str:
        return "" if _looks_like_amendment_note(match.group(1)) else match.group(0)

    cleaned = _BRACKETED_RE.sub(replace, text)
    # Qeyd silinəndən sonra qalan ikiqat boşluqlar səliqəyə salınır.
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return re.sub(r" +([.,;:])", r"\1", cleaned).strip()


# ---- Düzəliş tarixçəsi bloku -----------------------------------------------
# REAL SƏHİFƏDƏ ÖLÇÜLDÜ. Əvvəlki qayda (mötərizə içindəki qeydlər)
# e-qanun.az/framework/4481-də SIFIR nəticə verdi: 561 düzəliş nömrəsi
# var idi, 561-i də qaldı. Səbəb — fərziyyəm səhv idi: real səhifədə
# qeydlər mötərizədə deyil, sənədin sonunda NÖMRƏLƏNMİŞ SİYAHIDADIR:
#
#     1. 13 fevral 2001-ci il tarixli 74-IIQD nömrəli
#     2. 2 iyul 2002-ci il tarixli 359-IIQD nömrəli
#     3. 3 dekabr 2002-ci il tarixli 398-IIQD nömrəli
#
# 561 belə sətir. Bu, hüquqi mətn deyil, redaksiya jurnalıdır — model
# oradan sual qurur (dəst 18, sual 5 məhz belə yaranıb).
#
# TƏHLÜKƏSİZLİK: yalnız ARDICIL sətirlərdən ibarət BLOK silinir. Tək
# istinad hüquqi mətnin içində ola bilər və toxunulmur; iki sətir də
# azdır. Üç və daha çox ardıcıl sətir isə siyahıdır.
_HISTORY_LINE_RE = re.compile(
    r"^\s*\d{1,4}\s*[.)]\s+.*" + AMENDMENT_NUMBER_RE.pattern,
    re.IGNORECASE,
)
# Tarixçə yazıları bir sətirdə BİTMİR — hər yazıdan sonra davam sətri
# gəlir (real səhifədə ölçüldü, ardıcıl seriya heç vaxt 1-dən yuxarı
# qalxmırdı). Ona görə qayda KLASTER üzrə işləyir: bir-birinə yaxın
# yazılar bir blok sayılır və blok bütövlükdə, davam sətirləri ilə
# birlikdə silinir.
_HISTORY_MIN_ENTRIES = 3
# İki yazı arasında bu qədər sətir ola bilər. Kiçik saxlanılır: sənədin
# əvvəlində və sonunda tək-tək istinadlar varsa, aralarındakı BÜTÜN
# qanun mətni silinərdi — ən təhlükəli hal, ayrıca testlə qorunur.
_HISTORY_MAX_GAP = 4


def _strip_amendment_history(text: str) -> str:
    lines = text.splitlines()
    entries = [index for index, line in enumerate(lines) if _HISTORY_LINE_RE.match(line)]
    if len(entries) < _HISTORY_MIN_ENTRIES:
        return text

    # Yaxın yazıları klasterlərə yığ.
    clusters: list[list[int]] = [[entries[0]]]
    for index in entries[1:]:
        if index - clusters[-1][-1] <= _HISTORY_MAX_GAP:
            clusters[-1].append(index)
        else:
            clusters.append([index])

    keep = [True] * len(lines)
    removed_any = False
    for cluster in clusters:
        if len(cluster) < _HISTORY_MIN_ENTRIES:
            continue
        start = cluster[0]
        # Son yazının davam sətirləri də blokun hissəsidir.
        end = min(cluster[-1] + _HISTORY_MAX_GAP, len(lines) - 1)
        for position in range(start, end + 1):
            keep[position] = False
        removed_any = True

    if not removed_any:
        return text

    return "\n".join(line for line, wanted in zip(lines, keep) if wanted)


def _clean_legal_text(text: str) -> str:
    """Hüquqi mətnin bütün təmizləmə addımları — YEGANƏ yer.

    Diaqnostika da məhz bunu çağırır. Səbəb: əvvəl diaqnostika zənciri
    ƏL İLƏ təkrar yazırdı və `_strip_amendment_history` əlavə olunanda
    ora düşmədi — nəticədə ölçü «heç nə silinmir» dedi, halbuki qayda
    işləyirdi. İki yerdə saxlanılan zəncir mütləq ayrılır.
    """
    return _strip_amendment_annotations(_strip_amendment_history(text))


def _extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # `<style>` bloklarından xətt-siniflərini ÖYRƏNMƏK üçün bu addım
    # stil teqlərinin silinməsindən ƏVVƏL gəlməlidir.
    _remove_strikethrough(soup)
    for tag in soup(["script", "style", "nav", "footer", "header", "button", "aside", "form"]):
        tag.decompose()
    # `<main>`/`<article>` (HTML5-in semantik "əsas məzmun" konvensiyası)
    # varsa, ondan başlamaq axtarış sahəsini daralda bilər (məs. yan
    # panel kənarda qalır) — amma əsas süzgəc aşağıdakı məzmun-teq
    # filtridir.
    main = soup.find("main") or soup.find("article")
    root = main if main is not None else soup

    content_blocks = [
        block.get_text(" ", strip=True)
        for block in root.find_all(_CONTENT_TAGS)
        if block.get_text(strip=True)
    ]
    content_text = "\n".join(content_blocks)
    if len(content_text) >= _MIN_STATIC_TEXT_LENGTH:
        return _clean_legal_text(content_text)

    # Ehtiyat yolu — sayt mətni semantik teqlərdə saxlamırsa (pis
    # markup), köhnə "hər şeyi oxu" davranışına geri qayıt ki, material
    # tamamilə itməsin.
    return _clean_legal_text(root.get_text(separator="\n", strip=True))


def extract(source: MaterialSource) -> RawMaterial:
    url = _normalize_url(source.location)

    try:
        html = _download_static(url)
    except Exception as exc:
        # `{exc}` bilərəkdən mesaja daxil edilir — əvvəllər əsl səbəb
        # (məs. Selenium/Chrome xətası) heç yerdə görünmürdü, yalnız
        # `from exc` ilə traceback-ə zəncirlənirdi, amma bunu heç kim
        # loglamırdı (bax `server/app.py`, `_process_material`-a
        # `logger.exception` əlavəsi) — istifadəçi/loqlarda dərhal görünsün.
        raise IngestionError(f"Sayt yüklənmədi: {url} ({exc})") from exc

    text = _extract_text(html)

    if len(text) < _MIN_STATIC_TEXT_LENGTH:
        try:
            html = _download_js_rendered(url)
        except Exception as exc:
            raise IngestionError(
                f"Sayt JS-rendering ilə də yüklənmədi: {url} ({exc})"
            ) from exc
        text = _extract_text(html)
        # Real testdə tapılıb: JS-render bəzən yalnız kiçik bir "qabıq"
        # (başlıq/status/düymə) qaytarır, əsl sənəd mətni heç yüklənmir —
        # bu, aşağıdakı `not text.strip()` yoxlamasından keçir (boş DEYİL,
        # sadəcə çox qısadır) və nəticədə keyfiyyətsiz materialdan sual
        # generasiya olunur. Eyni minimum uzunluq həddi burada da tələb
        # olunur ki, belə hallar aydın xəta kimi RƏDD edilsin.
        if len(text) < _MIN_STATIC_TEXT_LENGTH:
            raise IngestionError(
                f"Sayt JS-rendering ilə yükləndi, amma kifayət qədər mətn "
                f"tapılmadı ({len(text)} simvol): {url}"
            )

    if not text.strip():
        raise IngestionError(f"Saytdan mətn çıxarıla bilmədi: {url}")

    return RawMaterial(text=text, metadata={"url": url})
