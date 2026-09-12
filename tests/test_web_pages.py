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


class TestNavigationShell:
    """Naviqasiya bölmələri ilə fayl sistemi arasındakı əlaqə.

    `nav.js`-ə yeni bölmə əlavə edib səhifəni yaratmağı unutmaq çox
    asandır — nəticədə istifadəçi menyudan 404-ə düşür. Bu, brauzerdə
    yalnız klikləyəndə görünür.
    """

    NAV_JS = WEB / "assets" / "js" / "nav.js"
    _HREF_RE = re.compile(r"href:\s*'([^']+)'")
    _MATCH_RE = re.compile(r"matches:\s*\[([^\]]*)\]")

    def _destination_hrefs(self) -> set[str]:
        return set(self._HREF_RE.findall(self.NAV_JS.read_text(encoding="utf-8")))

    def _matched_pages(self) -> set[str]:
        pages: set[str] = set()
        for group in self._MATCH_RE.findall(self.NAV_JS.read_text(encoding="utf-8")):
            pages.update(re.findall(r"'([^']+)'", group))
        return pages

    def test_destinations_were_found(self):
        assert len(self._destination_hrefs()) >= 4, "nav.js oxunmadı — regex sınıb ola bilər"

    def test_every_navigation_destination_has_a_page(self):
        missing = [href for href in self._destination_hrefs() if not (WEB / href).exists()]
        assert not missing, f"naviqasiyada var, faylı yoxdur: {sorted(missing)}"

    def test_every_matched_page_exists(self):
        """`matches` siyahısındakı səhifələr də mövcud olmalıdır — orada
        detal səhifələri (məs. `chat.html`) sadalanır."""
        missing = [page for page in self._matched_pages() if not (WEB / page).exists()]
        assert not missing, f"`matches`-də var, faylı yoxdur: {sorted(missing)}"


PROTECTED_PAGES = [p for p in PAGES if "requireLogin" in p.read_text(encoding="utf-8")]


def test_protected_pages_were_found():
    assert PROTECTED_PAGES, "qorunan səhifə tapılmadı — testlər mənasız olardı"


@pytest.mark.parametrize("page", PROTECTED_PAGES, ids=lambda p: p.name)
class TestShellContainers:
    """Qabıq `#appBar` və `#bottomNav` elementlərini gözləyir. Biri
    yoxdursa naviqasiya SÜKUTLA göstərilmir (`mountShell` erkən qayıdır)
    — səhifə işləyir, amma istifadəçi heç yerə keçə bilmir."""

    def test_page_has_both_shell_containers(self, page: Path):
        ids = _parse(page).ids
        assert "appBar" in ids, f"{page.name}: #appBar yoxdur"
        assert "bottomNav" in ids, f"{page.name}: #bottomNav yoxdur"

    def test_page_mounts_the_shell(self, page: Path):
        assert "mountShell()" in page.read_text(encoding="utf-8"), (
            f"{page.name}: mountShell() çağırılmır"
        )


# JS-də hərfi yazılmış səhifə adları: `x.href = `suallar.html?id=...`` və
# `window.location.replace('giris.html')` kimi. Dəyişəndən gələn ünvanlar
# (məs. `node.href = destination.href`) burada tutula bilmir — onlar
# `nav.js` testləri ilə örtülür.
_JS_PAGE_REF_RE = re.compile(r"""(?:href\s*=\s*|location\.(?:replace|assign)\s*\(\s*)['"`]([A-Za-z0-9_\-]+\.html)""")


def _js_page_refs(path: Path) -> set[str]:
    return set(_JS_PAGE_REF_RE.findall(path.read_text(encoding="utf-8")))


SCRIPTED_FILES = PAGES + sorted((WEB / "assets" / "js").glob("*.js"))


def test_scripted_files_were_found():
    assert len(SCRIPTED_FILES) > len(PAGES), "JS faylları tapılmadı"


@pytest.mark.parametrize("path", SCRIPTED_FILES, ids=lambda p: p.name)
def test_pages_referenced_from_javascript_exist(path: Path):
    """Real boşluq idi: `muellim.html` JS ilə `suallar.html`-a link
    yaradırdı, HTML atributu olmadığı üçün link testi onu GÖRMÜRDÜ.
    Belə link brauzerdə yalnız klikləyəndə 404 verir."""
    missing = [ref for ref in _js_page_refs(path) if not (WEB / ref).exists()]
    assert not missing, f"{path.name}: JS-də göstərilən səhifə yoxdur: {sorted(missing)}"


# Axtarış motoruna açıq səhifələr: `noindex` daşımayanlar. Giriş və
# qeydiyyat ictimaidir, amma qəsdən `noindex`-dədir — onların axtarışda
# görünməsinin mənası yoxdur.
INDEXABLE_PAGES = [
    p for p in PAGES if 'content="noindex"' not in p.read_text(encoding="utf-8")
]


def test_indexable_pages_were_found():
    assert INDEXABLE_PAGES, "indeksləşdiriləcək səhifə tapılmadı"


class TestSeoAndSharing:
    """MediaPulse-da hazır olan, MasterAI-də tamamilə YOX olan qat.
    Xüsusilə Open Graph: müəllimlər sessiya/qoşulma linkini qrup
    çatlarında paylaşır — önizləməsiz çılpaq link etibarsız görünür."""

    def test_landing_declares_canonical_and_description(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        assert 'rel="canonical"' in html
        assert 'name="description"' in html

    def test_landing_has_open_graph_and_twitter_cards(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        for tag in ('og:title', 'og:description', 'og:image', 'og:url', 'og:type'):
            assert f'property="{tag}"' in html, f"{tag} yoxdur"
        assert 'name="twitter:card"' in html

    def test_landing_has_structured_data(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        assert 'application/ld+json' in html
        assert '"EducationalApplication"' in html

    def test_landing_links_the_pwa_manifest(self):
        assert 'rel="manifest"' in (WEB / "index.html").read_text(encoding="utf-8")

    def test_manifest_is_valid_json_with_required_fields(self):
        import json

        manifest = json.loads((WEB / "manifest.json").read_text(encoding="utf-8"))
        for key in ("name", "short_name", "start_url", "display", "theme_color", "icons"):
            assert key in manifest, f"manifest.json-da {key} yoxdur"
        assert manifest["icons"], "ikon siyahısı boşdur"
        for icon in manifest["icons"]:
            assert (WEB / icon["src"]).exists(), f"ikon faylı yoxdur: {icon['src']}"

    def test_manifest_start_url_exists(self):
        import json

        manifest = json.loads((WEB / "manifest.json").read_text(encoding="utf-8"))
        start = manifest["start_url"].lstrip("./")
        assert (WEB / start).exists(), f"start_url mövcud deyil: {start}"

    def test_og_image_file_exists(self):
        assert (WEB / "assets" / "og-banner.svg").exists()

    @pytest.mark.parametrize("page", INDEXABLE_PAGES, ids=lambda p: p.name)
    def test_indexable_pages_carry_search_metadata(self, page: Path):
        """Axtarışa açıq hər səhifədə təsvir və kanonik ünvan olmalıdır —
        onsuz Google nəticədə təsadüfi mətn parçası göstərir və eyni
        səhifənin bir neçə variantını ayrı sayır.

        Qeyd: giriş/qeydiyyat səhifələri ictimaidir, amma QƏSDƏN
        `noindex` daşıyır — onlar bura düşmür."""
        html = page.read_text(encoding="utf-8")
        assert 'name="description"' in html, f"{page.name}: description yoxdur"
        assert 'rel="canonical"' in html, f"{page.name}: canonical yoxdur"

    def test_robots_txt_blocks_every_private_page(self):
        robots = (WEB / "robots.txt").read_text(encoding="utf-8")
        private = [p.name for p in PAGES if 'content="noindex"' in p.read_text(encoding="utf-8")]
        missing = [name for name in private if f"Disallow: /{name}" not in robots]
        assert not missing, f"robots.txt-də bağlanmayan şəxsi səhifə: {sorted(missing)}"

    def test_sitemap_lists_only_existing_public_pages(self):
        sitemap = (WEB / "sitemap.xml").read_text(encoding="utf-8")
        listed = re.findall(r"<loc>https://masterai\.prdostu\.com/([^<]*)</loc>", sitemap)
        missing = [name for name in listed if name and not (WEB / name).exists()]
        assert not missing, f"sitemap-də olmayan səhifə: {missing}"
        # Şəxsi səhifə sitemap-ə düşməməlidir.
        private = {p.name for p in PAGES if 'content="noindex"' in p.read_text(encoding="utf-8")}
        leaked = [name for name in listed if name in private]
        assert not leaked, f"sitemap-də şəxsi səhifə: {leaked}"


# Bu iki qayda `design-taste-frontend` skill-inin auditindən gəlir.
# Auditdə real vəziyyət: 130 em-dash və 23 emoji tapıldı. Hər ikisi
# "AI tərəfindən yazılmış" təəssüratının ən çox təkrarlanan
# göstəricisidir və hər ikisi sükutla geri qayıdır, ona görə testlə
# bağlanır.

SCRIPTED_SOURCES = PAGES + sorted((WEB / "assets" / "js").glob("*.js"))


class TestTypographicDiscipline:
    @pytest.mark.parametrize("path", SCRIPTED_SOURCES, ids=lambda p: p.name)
    def test_no_em_or_en_dash(self, path: Path):
        """Em-dash (—) və en-dash (–) qadağandır.

        Səbəb üslub deyil: bu simvol modelin ən tanınan imzasıdır və
        Azərbaycan mətnində iki nöqtə, vergül və ya adi defis hər
        halda daha düzgün oxunur. İcazə verilən yeganə tire adi
        defisdir.
        """
        text = path.read_text(encoding="utf-8")
        offenders = [
            line.strip()[:100]
            for line in text.splitlines()
            if "—" in line or "–" in line
        ]
        assert not offenders, f"{path.name}: em/en-dash tapıldı: {offenders[:3]}"

    @pytest.mark.parametrize("path", SCRIPTED_SOURCES, ids=lambda p: p.name)
    def test_no_emoji_used_as_icon(self, path: Path):
        """Emoji ikon kimi işlədilmir.

        Hər platformada fərqli görünür, rəngi `currentColor` ilə idarə
        olunmur və ekran oxuyucusu onu mətn kimi oxuyur. Əvəzinə
        `assets/icons.svg` sprite-ı (Tabler Icons, MIT) işlədilir.

        DİQQƏT: bu test əvvəl YALNIZ HTML-ə baxırdı və JS faylları
        kənarda qalırdı. Nəticədə tətbiqin bütün naviqasiyası, nişanları
        və xəta ekranları emoji ilə qalmışdı — brauzerdə baxanda
        göründü. İndi HTML və JS birlikdə yoxlanılır.
        """
        import unicodedata

        text = path.read_text(encoding="utf-8")
        found = {
            ch for ch in text if ord(ch) > 0x2000 and unicodedata.category(ch) == "So"
        }
        assert not found, f"{path.name}: emoji tapıldı: {sorted(found)}"


class TestIconSprite:
    SPRITE = WEB / "assets" / "icons.svg"
    _USE_RE = re.compile(r'href="assets/icons\.svg#(i-[a-z0-9-]+)"')

    def test_sprite_exists_and_has_symbols(self):
        assert self.SPRITE.exists(), "assets/icons.svg yoxdur"
        assert self.SPRITE.read_text(encoding="utf-8").count("<symbol") >= 20

    @pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
    def test_every_referenced_icon_exists_in_the_sprite(self, page: Path):
        """Səhv ikon adı brauzerdə SÜKUTLA heç nə göstərmir: xəta yoxdur,
        sadəcə boşluq qalır."""
        sprite = self.SPRITE.read_text(encoding="utf-8")
        used = set(self._USE_RE.findall(page.read_text(encoding="utf-8")))
        missing = [name for name in used if f'id="{name}"' not in sprite]
        assert not missing, f"{page.name}: sprite-da olmayan ikon: {sorted(missing)}"


class TestCallToActionDiscipline:
    """Bir niyyət, bir etiket. Auditdə açılış səhifəsində qeydiyyat
    niyyəti üç fərqli sözlə yazılmışdı (Qeydiyyat / Pulsuz başla /
    Hesab yarat) — ziyarətçi bunları fərqli hərəkət sanır."""

    INTENTS = {
        "qeydiyyat.html": "qeydiyyat",
        "qosul.html": "PIN qoşulması",
        "giris.html": "giriş",
    }

    def test_each_intent_uses_exactly_one_label_on_the_landing_page(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        for href, intent in self.INTENTS.items():
            labels = set(re.findall(rf'href="{re.escape(href)}"[^>]*>([^<]+)<', html))
            labels = {label.strip() for label in labels if label.strip()}
            assert len(labels) <= 1, (
                f"«{intent}» niyyəti üçün {len(labels)} fərqli etiket: {sorted(labels)}"
            )


class TestLandingLayoutVariety:
    """Ardıcıl bölmələrin eyni formada olması səhifəni bir bölmənin
    beş dəfə təkrarına çevirir. Auditdə üç ardıcıl `.grid` kart
    şəbəkəsi var idi."""

    def test_landing_uses_at_least_four_layout_families(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        families = {
            "hero + trace": 'class="trace"' in html,
            "xətli iddia siyahısı": 'class="claims"' in html,
            "kənar nömrəli addımlar": 'class="steps"' in html,
            "asimmetrik iki sütun": 'class="audience"' in html,
            "açılan siyahı": "<details" in html,
            "mərkəzləşmiş bağlanış": 'class="closing' in html,
        }
        present = [name for name, ok in families.items() if ok]
        assert len(present) >= 4, f"yalnız {len(present)} layout ailəsi: {present}"

    def test_card_grid_is_not_used_three_times_in_a_row(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        sections = re.findall(r"<section.*?</section>", html, re.DOTALL)
        streak = longest = 0
        for section in sections:
            streak = streak + 1 if 'class="grid"' in section else 0
            longest = max(longest, streak)
        assert longest < 3, f"{longest} ardıcıl kart şəbəkəsi bölməsi"


class TestSelfHostedFonts:
    """Şriftlər öz serverimizdədir, Google-dan yüklənmir.

    İki səbəb: üçüncü tərəf sorğusu render-i bloklayır (brauzer testində
    məhz o sorğu ERR_CONNECTION_RESET verirdi) və sayt Google-a çıxış
    olmadan da düzgün görünməlidir. Link geri qayıtsa bu test tutur.
    """

    CSS = WEB / "assets" / "css" / "tokens.css"
    _SRC_RE = re.compile(r"src:\s*url\('([^']+)'\)")

    def test_no_page_loads_fonts_from_google(self):
        offenders = [
            page.name
            for page in sorted(WEB.rglob("*.html"))
            if "fonts.googleapis.com" in page.read_text(encoding="utf-8")
            or "fonts.gstatic.com" in page.read_text(encoding="utf-8")
        ]
        assert not offenders, f"Google Fonts linki qayıdıb: {offenders}"

    def test_font_faces_were_found(self):
        """Qoruyucu: `@font-face` blokları silinsə aşağıdakı test
        sükutla 'keçər'."""
        assert len(self._SRC_RE.findall(self.CSS.read_text(encoding="utf-8"))) >= 4

    def test_every_font_file_referenced_by_css_exists(self):
        """Yoxsa hərflər sükutla fallback şriftlə çəkilir; brauzer xəta
        vermir, sadəcə sayt başqa görünür."""
        missing = [
            ref
            for ref in self._SRC_RE.findall(self.CSS.read_text(encoding="utf-8"))
            if not (self.CSS.parent / ref).resolve().exists()
        ]
        assert not missing, f"mövcud olmayan şrift faylı: {missing}"

    def test_latin_ext_subset_is_present_for_every_family(self):
        """Azərbaycan hərfləri (Ə U+018F, ə U+0259, Ğ, İ, Ş) məhz
        `latin-ext` alt-dəstindədir. Yalnız `latin` qalsa, başlıqlarda
        Ə hərfi fallback şriftdən gələr və söz alabəzək görünər."""
        refs = self._SRC_RE.findall(self.CSS.read_text(encoding="utf-8"))
        families = {Path(ref).name.rsplit("-", 1)[0] for ref in refs}
        for family in families:
            assert any(f"{family}-ext" in ref or "latin-ext" in ref for ref in refs), (
                f"{family}: latin-ext alt-dəsti yoxdur"
            )


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_page_declares_a_favicon(page: Path):
    """Nişan linki olmasa brauzer `/favicon.ico` istəyir və hər səhifə
    yüklənişində 404 yaranır. Konsolda görünür, statik testdə yox."""
    assert 'rel="icon"' in page.read_text(encoding="utf-8"), (
        f"{page.name}: <link rel=\"icon\"> yoxdur"
    )


class TestMobileWidthDiscipline:
    """Sabit `width` telefon ekranında üfüqi sürüşmə yaradır.

    REAL BUG İDİ: `giris`/`qeydiyyat`/`qosul` səhifələri
    `style="width: var(--width-form)"` (SABİT 420px) yazırdı. 390px-lik
    telefonda səhifə üfüqi sürüşürdü - PIN ilə qoşulma ekranı isə məhz
    telefonda işlədilir. Brauzer render-i tapdı; HTML testi tuta
    bilməzdi, ona görə indi bu qayda yazılıb.
    """

    @pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
    def test_no_fixed_width_in_inline_style(self, page: Path):
        offenders = [
            line.strip()[:120]
            for line in page.read_text(encoding="utf-8").splitlines()
            if re.search(r'style="[^"]*(?<!max-)width:\s*var\(--width-', line)
        ]
        assert not offenders, (
            f"{page.name}: sabit en tapıldı (`max-width` işlədin): {offenders}"
        )


class TestAssetCacheBusting:
    """CSS/JS ünvanları VERSİYA daşımalıdır və versiya HƏR SƏHİFƏDƏ EYNİ.

    REAL HADİSƏ (2026-09-12, İKİ dəfə): dizayn deploy olundu, brauzer
    isə köhnə faylı göstərdi. Səbəb: fayl adı dəyişmirsə, artıq
    keşlənmiş nüsxə keşdə qalır - `Cache-Control: no-cache` YALNIZ
    gələcək sorğulara təsir edir, əvvəl `expires 7d` ilə keşlənmiş
    fayla YOX. Birinci dəfə `live.js` faylın adını dəyişməklə həll
    edildi; ikinci dəfə (bütün palitra) versiya parametri ilə.

    Test versiyanın MÖVCUDLUĞUNU və eyniliyini yoxlayır, dəyərini yox -
    deploy zamanı bumb etmək istifadəçinin işidir. Yarımçıq bumb isə
    (bəzi səhifə köhnə, bəzisi yeni) məhz burada tutulur.
    """

    def test_every_css_link_carries_a_version(self):
        offenders = []
        for path in PAGES:
            for match in re.finditer(r'href="(assets/css/[^"]+)"', path.read_text(encoding='utf-8')):
                if "?v=" not in match.group(1):
                    offenders.append(f"{path.name}: {match.group(1)}")
        assert not offenders, f"versiyasız CSS: {offenders}"

    def test_all_pages_use_the_same_version(self):
        versions = set()
        for path in PAGES:
            versions.update(re.findall(r'assets/css/[^"?]+\?v=([^"]+)', path.read_text(encoding='utf-8')))
        assert len(versions) == 1, (
            f"səhifələr FƏRQLİ versiya işlədir: {sorted(versions)} - "
            "yarımçıq bumb, bəzi istifadəçilər qarışıq dəst alacaq"
        )
