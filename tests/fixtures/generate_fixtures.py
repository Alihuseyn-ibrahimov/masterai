"""Test fixture-larını yaradan bir dəfəlik skript.

Yenidən işə salmaq (fixture-ları təzələmək) üçün:
    .venv/bin/python tests/fixtures/generate_fixtures.py

Qeyd: mətnlərdə AZ-spesifik hərflər (ə/ı/ş/ç/ö/ü) qəsdən işlədilmir —
reportlab/PIL-in defolt fontları bunları düzgün render etməyə bilər. Real
Azərbaycan mətni ilə OCR/scraping dəqiqliyi Faza 6-da real materiallarla
əl ilə yoxlanılacaq (bax spec, bölmə 7).
"""

from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

FIXTURES_DIR = Path(__file__).parent

SAMPLE_TEXT_LINES = [
    "Azerbaycan Respublikasinin Konstitusiyasi",
    "Azerbaycan Respublikasi demokratik huquqi dunyevi unitar dovletdir.",
    "Dovlet hakimiyyeti qanunvericilik icra ve mehkeme hakimiyyetlerine bolunur.",
    "Paytaxt Baki seheridir.",
]


def make_sample_pdf() -> Path:
    path = FIXTURES_DIR / "sample.pdf"
    c = canvas.Canvas(str(path), pagesize=A4)
    y = 800
    for line in SAMPLE_TEXT_LINES:
        c.drawString(50, y, line)
        y -= 20
    c.save()
    return path


def make_sample_html() -> Path:
    path = FIXTURES_DIR / "sample.html"
    body = "\n".join(f"<p>{line}</p>" for line in SAMPLE_TEXT_LINES)
    html = f"""<!doctype html>
<html><head><title>Numune ders materiali</title>
<script>console.log("bu skript ignorlanmalidir")</script>
</head>
<body>
<nav>Naviqasiya menyusu (ignorlanmalidir)</nav>
{body}
<footer>Footer metni (ignorlanmalidir)</footer>
</body></html>"""
    path.write_text(html, encoding="utf-8")
    return path


def make_sample_image() -> Path:
    path = FIXTURES_DIR / "sample_image.png"
    img = Image.new("RGB", (900, 200), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 20), "Paytaxt Baki seheridir", fill="black")
    draw.text((20, 80), "Konstitusiya", fill="black")
    img.save(path)
    return path


def make_corrupt_pdf() -> Path:
    path = FIXTURES_DIR / "corrupt.pdf"
    path.write_bytes(b"bu bir PDF deyil, sadece metndir")
    return path


if __name__ == "__main__":
    for maker in (make_sample_pdf, make_sample_html, make_sample_image, make_corrupt_pdf):
        created = maker()
        print(f"created {created}")
