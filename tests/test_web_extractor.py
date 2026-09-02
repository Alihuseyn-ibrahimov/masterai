from pathlib import Path

import pytest

from pipeline.ingestion import web_extractor
from pipeline.ingestion.errors import IngestionError
from pipeline.models import MaterialSource

FIXTURES = Path(__file__).parent / "fixtures"


def test_extracts_text_and_strips_script_nav_footer(monkeypatch):
    html = (FIXTURES / "sample.html").read_text(encoding="utf-8")
    monkeypatch.setattr(web_extractor, "_download_static", lambda url: html)

    source = MaterialSource(kind="link", location="https://example.az/ders")
    raw = web_extractor.extract(source)

    assert "Konstitusiya" in raw.text
    assert "Baki seheridir" in raw.text
    assert "ignorlanmalidir" not in raw.text


def test_falls_back_to_js_rendering_when_static_text_too_short(monkeypatch):
    monkeypatch.setattr(web_extractor, "_download_static", lambda url: "<html><body></body></html>")
    monkeypatch.setattr(
        web_extractor,
        "_download_js_rendered",
        lambda url: "<html><body><p>" + "JS ile render olunan metn. " * 20 + "</p></body></html>",
    )

    source = MaterialSource(kind="link", location="https://example.az/js-ders")
    raw = web_extractor.extract(source)

    assert "JS ile render olunan metn" in raw.text


def test_raises_when_static_fetch_fails(monkeypatch):
    def boom(url):
        raise ConnectionError("saxta şəbəkə xətası")

    monkeypatch.setattr(web_extractor, "_download_static", boom)

    source = MaterialSource(kind="link", location="https://example.az/olu-link")
    with pytest.raises(IngestionError):
        web_extractor.extract(source)


def test_raises_when_both_static_and_js_yield_no_text(monkeypatch):
    monkeypatch.setattr(web_extractor, "_download_static", lambda url: "<html><body></body></html>")
    monkeypatch.setattr(web_extractor, "_download_js_rendered", lambda url: "<html><body></body></html>")

    source = MaterialSource(kind="link", location="https://example.az/bos-sehife")
    with pytest.raises(IngestionError):
        web_extractor.extract(source)
