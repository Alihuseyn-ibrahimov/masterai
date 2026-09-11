"""nginx konfiqurasiyası ilə backend marşrutları arasındakı uyğunluq.

Statik sayt və API artıq EYNİ domeni paylaşır (`masterai.prdostu.com`).
Ayırma nginx-dəki yol-kökü siyahısına əsaslanır — backend-ə yeni ÜST
SƏVİYYƏLİ endpoint əlavə edilib siyahıya yazılmasa, nginx onu statik
fayl kimi axtarar və istifadəçi **404** alar. Bu, yalnız production-da,
yalnız həmin endpoint çağırılanda üzə çıxar.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NGINX_CONF = ROOT / "deploy" / "nginx-masterai.conf"
APP_PY = ROOT / "server" / "app.py"

_ROUTE_RE = re.compile(r'@app\.(?:get|post|put|patch|delete|websocket)\(\s*"(/[^"]*)"')
_PREFIX_BLOCK_RE = re.compile(r"location\s+~\s+\^/\(([^)]+)\)")


def _backend_prefixes() -> set[str]:
    """Backend marşrutlarının BİRİNCİ yol seqmenti."""
    prefixes = set()
    for route in _ROUTE_RE.findall(APP_PY.read_text(encoding="utf-8")):
        segment = route.strip("/").split("/")[0]
        if segment:
            prefixes.add(segment)
    return prefixes


def _nginx_regex_prefixes() -> set[str]:
    match = _PREFIX_BLOCK_RE.search(NGINX_CONF.read_text(encoding="utf-8"))
    assert match, "nginx konfiqurasiyasında API yol siyahısı tapılmadı"
    return set(match.group(1).split("|"))


def _nginx_dedicated_prefixes() -> set[str]:
    """Ayrıca `location /xxx/` blokları — WebSocket kimi xüsusi
    başlıq tələb edən yollar üçün."""
    conf = NGINX_CONF.read_text(encoding="utf-8")
    return {segment for segment in re.findall(r"location\s+/([a-z]+)/\s*\{", conf)}


def _nginx_prefixes() -> set[str]:
    return _nginx_regex_prefixes() | _nginx_dedicated_prefixes()


def test_backend_prefixes_were_found():
    """Qoruyucu: regex sınıbsa aşağıdakı test sükutla 'keçər'."""
    assert len(_backend_prefixes()) >= 8


def test_every_backend_prefix_is_routed_by_nginx():
    missing = _backend_prefixes() - _nginx_prefixes()
    assert not missing, (
        f"nginx bu yolları backend-ə ötürmür, statik fayl kimi axtaracaq: {sorted(missing)}"
    )


def test_nginx_serves_the_static_site_root():
    conf = NGINX_CONF.read_text(encoding="utf-8")
    assert "root /opt/masterai-web;" in conf
    assert "try_files $uri $uri/ =404;" in conf


def test_websocket_block_has_a_long_timeout():
    """WebSocket bağlantısı adi 30 saniyəlik timeout-la kəsilərdi —
    canlı sessiya və çat ortasında qopardı."""
    conf = NGINX_CONF.read_text(encoding="utf-8")
    assert "proxy_read_timeout 3600s;" in conf
    assert "$connection_upgrade" in conf


def test_html_is_not_cached():
    """HTML keşlənsə istifadəçi yeni versiyanı görmək üçün sərt
    təzələmə etməli olur.

    QEYD: bu test əvvəl «CSS/JS isə keşlənməlidir» də tələb edirdi və
    `expires 7d;` axtarırdı - yəni SƏHV qaydanı qoruyurdu. Həmin keş
    deploy-ların qayıdan istifadəçiyə çatmamasına səbəb oldu (aşağıdakı
    keş testlərinin şərhinə bax)."""
    conf = NGINX_CONF.read_text(encoding="utf-8")
    assert re.search(r"\\\.html\$.*?\n\s*expires -1;", conf, re.DOTALL)


def test_upload_limit_leaves_headroom_over_the_backend_limit():
    """`client_max_body_size` backend-in 20 MB limitindən BÖYÜK olmalıdır
    — əks halda nginx sorğunu backend-ə çatmadan kəsir və istifadəçi
    aydın mesaj əvəzinə nginx-in xam 413 səhifəsini görür."""
    conf = NGINX_CONF.read_text(encoding="utf-8")
    sizes = {int(value) for value in re.findall(r"client_max_body_size (\d+)M;", conf)}
    assert sizes, "client_max_body_size təyin olunmayıb"
    assert min(sizes) > 20


def test_websocket_is_not_in_the_regex_block():
    """nginx-də REGEX `location` prefiks `location`-dan ÜSTÜNDÜR.

    `ws` regex siyahısına salınsa, `/ws/` bloku heç vaxt işə düşməz və
    `Upgrade`/`Connection` başlıqları ötürülməz — WebSocket handshake-i
    sükutla sınar (adi HTTP 200 kimi görünər). Ona görə `ws` QƏSDƏN
    ayrıca blokdadır və regex-də OLMAMALIDIR.
    """
    assert "ws" not in _nginx_regex_prefixes(), (
        "`ws` regex blokuna düşüb — WebSocket upgrade başlıqları itəcək"
    )
    assert "ws" in _nginx_dedicated_prefixes(), "`ws` üçün ayrıca location bloku yoxdur"


# ---- Keş başlıqları -------------------------------------------------------
# REAL HADİSƏ (2026-09-11): müəllim naviqasiyasına «Çatlar» əlavə olundu,
# deploy uğurlu keçdi, serverdəki `nav.js`-də dəyişiklik VAR idi — amma
# brauzerdə görünmürdü. Səbəb: `js`/`css` 7 gün keşlənirdi və HTML onlara
# VERSİYASIZ istinad edir (build addımı yoxdur, ona görə `nav.js?v=...`
# kimi cache-busting də yoxdur). Yəni HƏR deploy köhnə kodu qayıdan
# istifadəçilərdə 7 günə qədər canlı saxlayırdı.
#
# Şriftlər istisnadır: məzmunları dəyişmir, uzun keş onlarda düzgündür.

# Həm `\.(css|js)$`, həm də mötərizəsiz `\.woff2$` formasını tutur -
# ilk variantım yalnız mötərizəlini tuturdu və şrift blokunu SÜKUTLA
# buraxırdı.
_CACHE_BLOCK_RE = re.compile(
    r"location\s+~\*\s+\\\.\(?([^)$]+)\)?\$\s*\{([^}]*)\}", re.DOTALL
)


def _cache_blocks() -> dict[str, str]:
    """Uzantı qrupu → blokun gövdəsi."""
    conf = NGINX_CONF.read_text(encoding="utf-8")
    return {match.group(1): match.group(2) for match in _CACHE_BLOCK_RE.finditer(conf)}


def test_cache_blocks_were_found():
    """Qoruyucu: regex sınıbsa, aşağıdakı testlər sükutla 'keçər'."""
    assert _cache_blocks(), "nginx konfiqurasiyasında keş blokları tapılmadı"


def test_code_assets_are_revalidated_not_long_cached():
    """`js`/`css` uzun keşlənməməlidir - HTML onlara versiyasız istinad
    edir, yəni deploy-dan sonra köhnə kod qayıdan istifadəçidə qalar."""
    offenders = []
    for extensions, body in _cache_blocks().items():
        parts = set(extensions.split("|"))
        if not parts & {"js", "css"}:
            continue
        if "no-cache" not in body:
            offenders.append(f"{extensions}: 'no-cache' yoxdur")
        if re.search(r"expires\s+\d+[smhdy]", body):
            offenders.append(f"{extensions}: uzun `expires` var")
    assert not offenders, "; ".join(offenders)


def test_fonts_may_still_be_cached_long():
    """Şrift faylları məzmunca sabitdir - onları hər açılışda yenidən
    yoxlamaq mənasız trafikdir."""
    fonts = [body for ext, body in _cache_blocks().items() if "woff2" in ext.split("|")]
    assert fonts, "şrift üçün ayrıca keş bloku yoxdur"
    assert any(re.search(r"expires\s+\d+[smhdy]", body) for body in fonts), (
        "şriftlər uzun keşlənməlidir"
    )
