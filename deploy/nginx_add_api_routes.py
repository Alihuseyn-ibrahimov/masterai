"""Canlı nginx konfiqurasiyasına `me` və `owner` API yollarını CƏRRAHİ əlavə edir.

NİYƏ `scp` İLƏ ÜSTÜNƏ YAZMAQ YOX: canlı fayla certbot HTTPS sətirlərini
(`listen 443 ssl`, sertifikat yolları, http->https yönləndirmə) özü yazıb.
Repo-dakı `nginx-masterai.conf`-da bunlar YOXDUR — üstünə yazmaq saytı
HTTPS-siz qoyardı. Bu skript yalnız bir sətri dəyişir, qalanına toxunmur.

    .venv/bin/python deploy/nginx_add_api_routes.py "$(readlink -f /etc/nginx/sites-enabled/masterai)"

Çıxış kodu: 0 — düzəldildi və ya artıq düzgündür; 1 — gözlənilən sətir
tapılmadı (heç nə dəyişmədi, əl ilə baxmaq lazımdır).
"""

from __future__ import annotations

import sys
from pathlib import Path

OLD = "|health|quiz)(/|$)"
NEW = "|health|quiz|me|owner)(/|$)"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("İstifadə: nginx_add_api_routes.py <canlı konfiqurasiya faylı>")
        return 1
    path = Path(args[0])
    text = path.read_text(encoding="utf-8")
    if NEW in text:
        print("artıq düzgündür - heç nə dəyişmədi")
        return 0
    if text.count(OLD) != 1:
        print(f"gözlənilən sətir {text.count(OLD)} dəfə tapıldı (1 olmalıdır) - "
              "heç nə dəyişmədi, ƏL İLƏ bax")
        return 1
    path.write_text(text.replace(OLD, NEW), encoding="utf-8")
    print("düzəldildi: " + next(line.strip() for line in text.replace(OLD, NEW).splitlines()
                                if NEW in line))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
