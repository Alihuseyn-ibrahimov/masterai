"""Veb səhifələrinin real brauzerdə render diaqnostikası.

Niyə lazımdır: HTML və testlər düzgün ola-ola səhifə brauzerdə SƏHV
görünə bilər. Real nümunə (2026-09-09): `hidden` xəta qutuları hər
səhifədə BOŞ QIRMIZI ZOLAQ kimi görünürdü, çünki `.notice
{ display: flex }` brauzerin `[hidden]` qaydasını üstələyirdi. Nə HTML,
nə CSS testləri bunu tuta bilməzdi — yalnız gözlə baxanda göründü.

TƏLƏB: səhifələr HTTP üzərindən verilməlidir. `file://` ilə ES modulları
brauzer tərəfindən CORS səbəbi ilə BLOKLANIR (bu skriptlə təsdiqləndi).

İşlətmək:
    cd masterai/web && python -m http.server 8123 --bind 127.0.0.1 &
    cd .. && .venv/bin/python deploy/diagnostics/screenshot_pages.py
    # şəkillər: /tmp/shots/
"""

from pathlib import Path
from playwright.sync_api import sync_playwright

WEB = Path("/home/user/quantum-pr-monitor/masterai/web").resolve()
OUT = Path("/tmp/shots")

# Saxta sessiya — səhifələr `requireLogin()` ilə qorunur.
SEED = """
localStorage.setItem('masterai.token', 'test-token');
localStorage.setItem('masterai.user', JSON.stringify(
  {id: 1, email: 'ali@numune.az', display_name: 'Əli Məmmədov', is_teacher: %s, is_admin: false}));
"""

VIEWPORTS = {"desktop": (1280, 900), "mobil": (390, 844)}

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    for label, (width, height) in VIEWPORTS.items():
        for page_name, is_teacher in [("chatlar.html", "false"), ("profil.html", "false"),
                                      ("muellim.html", "true"), ("tapsiriqlar.html", "false")]:
            context = browser.new_context(viewport={"width": width, "height": height})
            context.add_init_script(SEED % is_teacher)
            # Şəbəkə sorğularını kəs — canlı backend-ə toxunmuruq.
            context.route("**/masterai.prdostu.com/**", lambda route: route.abort())
            page = context.new_page()
            errors = []
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(f"PAGEERROR: {e}"))
            page.goto(f"http://127.0.0.1:8123/{page_name}")
            page.wait_for_timeout(900)
            name = f"{label}-{page_name.replace('.html','')}"
            page.screenshot(path=str(OUT / f"{name}.png"), full_page=(label == "desktop"))
            real = [e for e in errors if "prdostu.com" not in e and "Failed to load" not in e]
            print(f"{name}: {'XƏTA -> ' + str(real[:2]) if real else 'təmiz'}")
            context.close()
    browser.close()
