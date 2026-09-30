"""Canlı nginx faylının cərrahi düzəlişi (Faza 9) — certbot sətirləri qorunur."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy"))
import nginx_add_api_routes as edit  # noqa: E402

CERTBOT = "    listen 443 ssl; # managed by Certbot\n"


def _live_conf(tmp_path: Path) -> Path:
    """Repo faylı + certbot sətri, API siyahısı isə deploy-dan ƏVVƏLKİ halda."""
    repo = (ROOT / "deploy" / "nginx-masterai.conf").read_text(encoding="utf-8")
    assert edit.NEW in repo  # repo faylı artıq yeni siyahıdadır — skript onunla uzlaşmalıdır
    path = tmp_path / "masterai"
    path.write_text(repo.replace(edit.NEW, edit.OLD) + CERTBOT, encoding="utf-8")
    return path


def test_adds_routes_and_keeps_everything_else(tmp_path):
    path = _live_conf(tmp_path)
    before = path.read_text(encoding="utf-8")
    assert edit.main([str(path)]) == 0
    after = path.read_text(encoding="utf-8")
    assert after == before.replace(edit.OLD, edit.NEW)
    assert CERTBOT in after
    # api. bloku (location /) və digər sətirlər dəyişmədi — nəticə repo faylı + certbot
    assert after == (ROOT / "deploy" / "nginx-masterai.conf").read_text(encoding="utf-8") + CERTBOT


def test_second_run_is_noop(tmp_path):
    path = _live_conf(tmp_path)
    edit.main([str(path)])
    once = path.read_text(encoding="utf-8")
    assert edit.main([str(path)]) == 0
    assert path.read_text(encoding="utf-8") == once


def test_unexpected_file_untouched(tmp_path):
    path = tmp_path / "masterai"
    path.write_text("server { location / {} }\n", encoding="utf-8")
    assert edit.main([str(path)]) == 1
    assert path.read_text(encoding="utf-8") == "server { location / {} }\n"
