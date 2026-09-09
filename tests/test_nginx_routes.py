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


def test_html_is_not_cached_but_assets_are():
    """HTML keşlənsə istifadəçi yeni versiyanı görmək üçün sərt
    təzələmə etməli olur; CSS/JS isə keşlənməlidir."""
    conf = NGINX_CONF.read_text(encoding="utf-8")
    assert re.search(r"\\\.html\$.*?\n\s*expires -1;", conf, re.DOTALL)
    assert "expires 7d;" in conf


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
