"""Kassa demosunun serverə qoyulması (deploy/DEPLOY_KASSA.md).

Demo produksiya ilə EYNİ 2 GB-lıq maşındadır. Bu testlər produksiyanı sındıra
biləcək səhvləri tutur: nginx faylında ikinci `map` (`nginx -t` sınar və reload
masterai-ni də aparar), eyni port, yaddaş limitsiz ikinci proses, API-də basic auth
(tətbiqin Bearer başlığı ilə toqquşur, hər sorğu 401 olar).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / "deploy"
KASSA_CONF = (DEPLOY / "nginx-kassa-demo.conf").read_text(encoding="utf-8")
PROD_CONF = (DEPLOY / "nginx-masterai.conf").read_text(encoding="utf-8")
KASSA_UNIT = (DEPLOY / "kassa-demo.service").read_text(encoding="utf-8")
PROD_UNIT = (DEPLOY / "masterai.service").read_text(encoding="utf-8")
GUIDE = (DEPLOY / "DEPLOY_KASSA.md").read_text(encoding="utf-8")

_API_RE = re.compile(r"location\s+~\s+\^/\(([^)]+)\)")


def _code(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def _blocks(conf: str) -> dict[str, str]:
    """`location ... {` başlığı → blokun içi (iç-içə blok yoxdur)."""
    return {m.group(1).strip(): m.group(2) for m in re.finditer(r"location\s+([^{]+)\{([^}]*)\}", _code(conf))}


def test_api_prefixes_match_production():
    assert set(_API_RE.search(KASSA_CONF).group(1).split("|")) == set(_API_RE.search(PROD_CONF).group(1).split("|"))


def test_no_second_map_block():
    assert "map $http_upgrade" in PROD_CONF
    assert not re.search(r"^\s*map\s", _code(KASSA_CONF), flags=re.M)


def test_basic_auth_on_pages_but_not_on_api():
    code = _code(KASSA_CONF)
    assert "auth_basic_user_file /etc/nginx/kassa-demo.htpasswd;" in code
    blocks = _blocks(KASSA_CONF)
    api = next(v for k, v in blocks.items() if k.startswith("~ ^/("))
    assert "auth_basic off;" in api and "proxy_pass http://127.0.0.1:8111;" in api
    assert "auth_basic off;" in blocks["/ws/"]
    assert "auth_basic off" not in blocks["/"]


def test_registration_is_closed():
    assert "return 403;" in _blocks(KASSA_CONF)["= /auth/register"]


def test_demo_backend_is_separate_and_memory_capped():
    assert "127.0.0.1:8110" in PROD_UNIT
    assert "-b 127.0.0.1:8111" in KASSA_UNIT
    assert "-w 1" in KASSA_UNIT
    assert "MemoryMax=" in KASSA_UNIT
    assert "EnvironmentFile=/opt/kassa-demo/data/demo.env" in KASSA_UNIT
    assert "/opt/masterai" not in _code(KASSA_UNIT)
    assert "root /opt/kassa-demo/web;" in KASSA_CONF


def test_guide_uses_these_files_and_module_eval():
    for name in ("kassa-demo.service", "nginx-kassa-demo.conf", "deploy/kassa_demo.py"):
        assert name in GUIDE
    assert "python3 -m evals.kassa --live" in GUIDE
    assert "certbot --nginx -d kassa.prdostu.com" in GUIDE   # yalnız demo domeni
