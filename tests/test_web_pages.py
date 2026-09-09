"""Statik veb səhifələrinin bütövlük testləri.

Build addımı olmayan saytda sınıq link və ya səhv asset yolu heç bir
xəta vermir — sadəcə 404 olur və istifadəçi qarşısında sınır. Burada
onlar avtomatik tutulur.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent / "web"
PAGES = sorted(WEB.glob("*.html"))


class _Collector(HTMLParser):
    """`href`/`src` dəyərlərini və `<label for>`/`id` cütlərini toplayır."""

    def __init__(self) -> None:
        super().__init__()
        self.refs: list[str] = []
        self.ids: set[str] = set()
        self.label_targets: list[str] = []
        self.has_lang = False
        self.has_viewport = False
        self.title_text = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: (value or "") for key, value in attrs}
        if tag == "html" and attributes.get("lang"):
            self.has_lang = attributes["lang"] == "az"
        if tag == "meta" and attributes.get("name") == "viewport":
            self.has_viewport = True
        if tag == "title":
            self._in_title = True
        if attributes.get("id"):
            self.ids.add(attributes["id"])
        if tag == "label" and attributes.get("for"):
            self.label_targets.append(attributes["for"])
        for attr in ("href", "src"):
            if attr in attributes:
                self.refs.append(attributes[attr])

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_text += data


def _parse(path: Path) -> _Collector:
    collector = _Collector()
    collector.feed(path.read_text(encoding="utf-8"))
    return collector


def _is_external(ref: str) -> bool:
    return ref.startswith(("http://", "https://", "#", "mailto:", "data:"))


def test_pages_were_found():
    """Qoruyucu: glob boş qalsa, aşağıdakı testlər sükutla 'keçər'."""
    assert PAGES, "web/ qovluğunda HTML səhifəsi tapılmadı"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
class TestPageIntegrity:
    def test_all_internal_links_and_assets_exist(self, page: Path):
        missing = []
        for ref in _parse(page).refs:
            if _is_external(ref) or not ref:
                continue
            target = (page.parent / ref.split("#")[0].split("?")[0]).resolve()
            if not target.exists():
                missing.append(ref)
        assert not missing, f"{page.name}: mövcud olmayan hədəf: {missing}"

    def test_page_declares_azerbaijani_language(self, page: Path):
        """`lang="az"` ekran oxuyucusunun düzgün tələffüzü və brauzerin
        tərcümə təklifi üçün lazımdır."""
        assert _parse(page).has_lang

    def test_page_is_mobile_ready(self, page: Path):
        assert _parse(page).has_viewport, f"{page.name}: viewport meta teqi yoxdur"

    def test_page_has_a_meaningful_title(self, page: Path):
        title = _parse(page).title_text.strip()
        assert title, f"{page.name}: <title> boşdur"
        assert "MasterAI" in title

    def test_every_label_points_to_an_existing_field(self, page: Path):
        """`<label for>` səhv id göstərsə, etiketə klikləmək sahəni
        fokuslamır və ekran oxuyucusu sahəni adsız oxuyur."""
        parsed = _parse(page)
        dangling = [target for target in parsed.label_targets if target not in parsed.ids]
        assert not dangling, f"{page.name}: boşda qalan label: {dangling}"


class TestSharedConventions:
    @pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
    def test_design_system_is_loaded_in_order(self, page: Path):
        """`tokens.css` HƏMİŞƏ birinci gəlməlidir — dəyişənlər onları
        işlədən qaydalardan əvvəl təyin olunmalıdır."""
        html = page.read_text(encoding="utf-8")
        positions = {
            name: html.find(f"assets/css/{name}.css")
            for name in ("tokens", "base", "components")
        }
        assert all(pos >= 0 for pos in positions.values()), f"{page.name}: {positions}"
        assert positions["tokens"] < positions["base"] < positions["components"]

    @pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
    def test_no_inline_hex_colors_in_markup(self, page: Path):
        """Səhifə daxilində birbaşa rəng yazmaq dizayn sistemini
        yan keçir. İstisna: `theme-color` meta teqi — brauzer ünvan
        zolağının rəngidir, CSS dəyişəni qəbul etmir."""
        offenders = [
            line.strip()
            for line in page.read_text(encoding="utf-8").splitlines()
            if re.search(r"#[0-9a-fA-F]{3,8}\b", line) and "theme-color" not in line
        ]
        assert not offenders, f"{page.name}: markup-da birbaşa rəng: {offenders}"
