"""Statik analiz qapısı.

NİYƏ: diaqnostika skriptləri serverdə çökdü —

    UnboundLocalError: cannot access local variable 'shown'

Səbəb: kodu redaktə edərkən dəyişənin təyini silindi, istifadəsi qaldı.
Sintaksis düzgün olduğu üçün `ast.parse()` bunu görmür, testlər isə
diaqnostikaları çağırmır (onlar şəbəkə tələb edir). Nəticədə səhv yalnız
REAL SERVERDƏ, ölçünün ortasında üzə çıxdı və vaxt itkisinə səbəb oldu.

pyflakes məhz bu sinfi tutur: təyin olunmamış ad, işlədilməyən idxal,
istifadə edilməyən yerli dəyişən. Sürətlidir (bütün layihə bir saniyədən
az) və heç nə icra etmir.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CHECKED = ("pipeline", "server", "deploy", "tests")


def _pyflakes_available() -> bool:
    result = subprocess.run(
        [sys.executable, "-m", "pyflakes", "--version"],
        capture_output=True,
    )
    return result.returncode == 0


@pytest.mark.skipif(not _pyflakes_available(), reason="pyflakes quraşdırılmayıb")
def test_no_undefined_names_or_unused_imports():
    result = subprocess.run(
        [sys.executable, "-m", "pyflakes", *CHECKED],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    findings = [line for line in result.stdout.splitlines() if line.strip()]
    assert not findings, "pyflakes tapıntıları:\n" + "\n".join(findings)


@pytest.mark.skipif(not _pyflakes_available(), reason="pyflakes quraşdırılmayıb")
def test_the_gate_actually_detects_a_broken_file(tmp_path: Path):
    """Qoruyucu: pyflakes səssizcə işləməsə yuxarıdakı test həmişə
    «keçər» və heç nə yoxlamaz. Qəsdən sınıq fayl ilə yoxlanılır —
    serverdə baş verən səhvin eynisi."""
    broken = tmp_path / "sinq.py"
    broken.write_text(
        "def main():\n"
        "    for x in [1]:\n"
        "        print(x)\n"
        "    if shown == 0:\n"
        "        print('cokur')\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "pyflakes", str(broken)],
        capture_output=True,
        text=True,
    )
    assert "undefined name" in result.stdout, (
        "pyflakes sınıq faylı tutmadı — qapı mənasızdır"
    )
