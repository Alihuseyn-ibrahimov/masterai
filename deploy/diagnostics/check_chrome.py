"""Chrome-un bu serverdə başlaya bilib-bilmədiyini SÜBUT EDİR.

NİYƏ: uğursuz dəstlərin 4-ü «DevToolsActivePort file doesn't exist»
xətası verir. Bu, Chrome-un start zamanı ölməsi deməkdir, amma SƏBƏBİNİ
demir. Yaddaş təzyiqi ehtimalı güclüdür (512 MB RAM, 80% dolu, swap
49%, eyni URL bəzən işləyir) — amma bu, hələ EHTİMALDIR.

Bu skript ehtimalı ölçüyə çevirir: hər cəhddən əvvəl və sonra boş
yaddaşı yazır, bir neçə dəfə Chrome açmağa çalışır və nəticəni göstərir.

    cd /opt/pr-agent/repo/masterai
    .venv/bin/python deploy/diagnostics/check_chrome.py

Servisə toxunmur, yalnız Chrome açıb bağlayır.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ATTEMPTS = 3


def _memory() -> dict[str, int]:
    """Boş yaddaş, MB ilə. `/proc/meminfo` hər Linux-da var, əlavə
    kitabxana tələb etmir."""
    values = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, _, rest = line.partition(":")
        if key in ("MemTotal", "MemFree", "MemAvailable", "SwapTotal", "SwapFree"):
            values[key] = int(rest.strip().split()[0]) // 1024
    return values


def _print_memory(label: str) -> None:
    m = _memory()
    print(
        f"  {label:<22} boş: {m.get('MemAvailable', 0):>4} MB / "
        f"{m.get('MemTotal', 0):>4} MB    "
        f"swap boş: {m.get('SwapFree', 0):>4} MB / {m.get('SwapTotal', 0):>4} MB"
    )


def main() -> int:
    from selenium import webdriver
    from pipeline.ingestion import web_extractor

    print("=" * 68)
    print("CHROME START YOXLAMASI")
    print("=" * 68)
    print("\nİşlədilən bayraqlar:")
    for argument in web_extractor._chrome_arguments():
        print(f"  {argument}")
    print()

    ok = 0
    for attempt in range(1, ATTEMPTS + 1):
        print(f"--- cəhd {attempt}/{ATTEMPTS} ---")
        _print_memory("başlamazdan əvvəl")
        started = time.monotonic()
        driver = None
        try:
            # Təkrar cəhd MƏNTİQİ QƏSDƏN yan keçilir — burada hər tək
            # cəhdin nəticəsini ayrıca görmək istəyirik.
            from selenium.webdriver.chrome.options import Options
            options = Options()
            for argument in web_extractor._chrome_arguments():
                options.add_argument(argument)
            driver = webdriver.Chrome(options=options)
            _print_memory("Chrome açıqkən")
            print(f"  NƏTİCƏ: uğurlu ({time.monotonic() - started:.1f} san)")
            ok += 1
        except Exception as exc:                                  # noqa: BLE001
            first_line = str(exc).splitlines()[0] if str(exc) else repr(exc)
            print(f"  NƏTİCƏ: UĞURSUZ ({time.monotonic() - started:.1f} san)")
            print(f"  səbəb: {first_line[:160]}")
        finally:
            if driver is not None:
                driver.quit()
        _print_memory("bağlandıqdan sonra")
        print()

    print("=" * 68)
    print(f"YEKUN: {ok}/{ATTEMPTS} cəhd uğurlu")
    print("=" * 68)
    if ok == ATTEMPTS:
        print("Chrome sabit işləyir. Uğursuzluq yaddaş təzyiqi ANINDA baş verir —")
        print("yeni bayraqlar və təkrar cəhd bunu azaltmalıdır.")
    elif ok == 0:
        print("Chrome heç açılmır. Bu, yaddaş dalğalanması DEYİL, daimi problemdir:")
        print("Chrome/chromedriver quraşdırması yoxlanmalıdır.")
    else:
        print("Chrome BƏZƏN açılır — bu, yaddaş təzyiqi diaqnozunu təsdiqləyir.")
        print("Yuxarıdakı «boş yaddaş» rəqəmlərini uğurlu və uğursuz cəhdlərdə")
        print("müqayisə edin.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
