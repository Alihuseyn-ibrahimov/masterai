"""Bütün veb səhifələrini real Chromium-da açıb JS xətalarını yoxlayır.

Şəkil çəkmir — sürətli "hamısı yüklənirmi?" yoxlamasıdır. Görünüş
yoxlaması üçün `screenshot_pages.py`.

Niyə lazımdır: HTML və pytest testləri keçə-keçə səhifə brauzerdə
sınmış ola bilər (səhv import yolu, modul xətası, tanınmayan sintaksis).

TƏLƏB: lokal server + şəbəkə sorğularının kəsilməsi. Google Fonts və
canlı backend sorğuları qəsdən bloklanır ki, yoxlama sürətli olsun və
production-a toxunmasın.

İşlətmək:
    cd masterai
    .venv/bin/python -m http.server 8123 --bind 127.0.0.1 --directory web &
    .venv/bin/python deploy/diagnostics/check_pages_in_browser.py
"""

from pathlib import Path
from playwright.sync_api import sync_playwright

WEB = Path("/home/user/quantum-pr-monitor/masterai/web")
SEED = """
localStorage.setItem('masterai.token','t');
localStorage.setItem('masterai.user', JSON.stringify(
  {id:1,email:'a@b.az',display_name:'Əli',is_teacher:%s,is_admin:false}));
"""
pages = sorted(p.name for p in WEB.glob("*.html"))
teacher_pages = {"muellim.html", "suallar.html", "sessiyalar.html", "hesabatlar.html"}

failures = []
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    for name in pages:
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        ctx.add_init_script(SEED % ("true" if name in teacher_pages else "false"))
        ctx.route("**/masterai.prdostu.com/**", lambda route: route.abort())
        ctx.route("**fonts.googleapis.com**", lambda route: route.abort())
        ctx.route("**fonts.gstatic.com**", lambda route: route.abort())
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(f"PAGEERROR: {e}"))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        suffix = "?id=1" if name in {"suallar.html", "chat.html", "tapsiriq.html"} else ""
        page.goto(f"http://127.0.0.1:8123/{name}{suffix}", wait_until="domcontentloaded")
        page.wait_for_timeout(400)
        real = [e for e in errors if "prdostu.com" not in e and "Failed to load resource" not in e]
        status = "təmiz" if not real else f"XƏTA: {real[0][:140]}"
        if real:
            failures.append(name)
        print(f"{name:22s} {status}")
        ctx.close()
    browser.close()
print(f"\nYekun: {len(pages)} səhifə, {len(failures)} xətalı" + (f" -> {failures}" if failures else ""))
