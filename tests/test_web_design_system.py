"""Dizayn sisteminin intizamını qoruyan testlər.

Flutter tətbiqində paylaşılan komponent qovluğu yox idi və hər ekran öz
rəngini/ölçüsünü birbaşa yazırdı — vizual uyğunsuzluğun kök səbəbi bu
idi (bax `.planning/2026-09-09-masterai-app-redesign/`). Veb tərəfdə
eyni səhvin qayıtmaması üçün qayda AVTOMATİK yoxlanılır:

    `tokens.css` yeganə rəng/ölçü mənbəyidir; digər CSS faylları
    yalnız `var(--...)` işlədir.

Bu naxış mediapulse.az-dan götürülüb (orada da bütün sayt CSS
dəyişənləri üzərində qurulub), amma orada yalnız konvensiya idi —
burada testlə möhkəmləndirilir.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CSS_DIR = Path(__file__).resolve().parent.parent / "web" / "assets" / "css"
TOKENS = CSS_DIR / "tokens.css"
# `tokens.css`-dən BAŞQA bütün stil faylları bu qaydalara tabedir.
DEPENDENT_CSS = [CSS_DIR / "base.css", CSS_DIR / "components.css"]

_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_FUNC_COLOR_RE = re.compile(r"\b(?:rgba?|hsla?)\s*\(", re.IGNORECASE)
_VAR_DEF_RE = re.compile(r"^\s*(--[a-z0-9-]+)\s*:", re.MULTILINE)
_VAR_USE_RE = re.compile(r"var\(\s*(--[a-z0-9-]+)")
# Kənar xətti/outline enləri (1-3px) istisnadır: bunlar dizayn qərarı
# yox, struktur detalıdır və tokenləşdirmək oxunaqlığı azaldar.
_PX_RE = re.compile(r"\b(\d+(?:\.\d+)?)px\b")
_MAX_INLINE_PX = 3


def _strip_comments(css: str) -> str:
    return _COMMENT_RE.sub("", css)


def _read(path: Path) -> str:
    return _strip_comments(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def token_names() -> set[str]:
    return set(_VAR_DEF_RE.findall(_read(TOKENS)))


class TestTokensAreTheSingleSource:
    @pytest.mark.parametrize("path", DEPENDENT_CSS, ids=lambda p: p.name)
    def test_no_literal_colors_outside_tokens(self, path: Path):
        css = _read(path)
        hex_colors = _HEX_COLOR_RE.findall(css)
        func_colors = _FUNC_COLOR_RE.findall(css)
        assert not hex_colors, f"{path.name}: birbaşa hex rəng tapıldı: {hex_colors}"
        assert not func_colors, f"{path.name}: birbaşa rgb/hsl rəngi tapıldı"

    @pytest.mark.parametrize("path", DEPENDENT_CSS, ids=lambda p: p.name)
    def test_no_hardcoded_sizes_outside_tokens(self, path: Path):
        """`@media` sətirləri istisnadır — CSS media sorğuları
        `var()` QƏBUL ETMİR (dilin məhdudiyyəti, bizim seçimimiz deyil)."""
        offenders = []
        for line in _read(path).splitlines():
            if line.lstrip().startswith("@media"):
                continue
            for value in _PX_RE.findall(line):
                if float(value) > _MAX_INLINE_PX:
                    offenders.append(line.strip())
        assert not offenders, f"{path.name}: tokenləşdirilməmiş ölçü: {offenders}"

    @pytest.mark.parametrize("path", DEPENDENT_CSS, ids=lambda p: p.name)
    def test_every_used_token_is_defined(self, path: Path, token_names: set[str]):
        """Yazı səhvini tutur: `var(--color-primry)` sükutla heç nə
        qaytarır və element rəngsiz qalır — brauzer xəta vermir."""
        used = set(_VAR_USE_RE.findall(_read(path)))
        # Yerli (inline `style` ilə ötürülən) dəyişənlər tokens.css-də
        # olmur — onlar komponentin parametrləridir, sabit deyil.
        local = {"--subject", "--progress"}
        undefined = used - token_names - local
        assert not undefined, f"{path.name}: təyin olunmamış token: {sorted(undefined)}"


class TestTokenCoverage:
    REQUIRED = [
        "--color-primary", "--color-bg", "--color-surface", "--color-border",
        "--color-text", "--color-text-muted",
        "--color-success", "--color-warning", "--color-danger", "--color-info",
        "--space-1", "--space-2", "--space-4", "--space-6",
        "--radius-md", "--radius-lg", "--radius-full",
        "--font-heading", "--font-body",
        "--text-sm", "--text-base", "--text-2xl",
        "--width-container", "--width-prose",
    ]

    @pytest.mark.parametrize("token", REQUIRED)
    def test_required_token_is_defined(self, token: str, token_names: set[str]):
        assert token in token_names

    def test_all_six_subject_colors_match_the_flutter_palette(self, token_names: set[str]):
        """Fənn rəngləri `app_subject_colors.dart`-dan köçürülüb —
        davamlılıq üçün altısı da olmalıdır."""
        for subject in (
            "mentiq", "informatika", "dunyagorusu",
            "azerbaycan-dili", "qanunvericilik", "xarici-dil",
        ):
            assert f"--subject-{subject}" in token_names


class TestDarkMode:
    """Tünd rejim işıqlı rejimin BÜTÜN rəng tokenlərini yenidən təyin
    etməlidir — biri unudulsa, tünd fonda tünd mətn kimi oxunmaz
    nəticə yaranır və bu, yalnız gözlə baxanda görünür."""

    def _block(self, marker: str) -> str:
        css = _read(TOKENS)
        start = css.index(marker)
        depth = 0
        for i, ch in enumerate(css[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return css[start : i + 1]
        raise AssertionError(f"{marker} bloku bağlanmayıb")

    def _color_tokens(self, block: str) -> set[str]:
        return {
            name
            for name in _VAR_DEF_RE.findall(block)
            if name.startswith(("--color-", "--subject-", "--shadow-"))
        }

    def test_explicit_dark_theme_covers_every_light_color_token(self):
        light = self._color_tokens(self._block(":root {"))
        dark = self._color_tokens(self._block('[data-theme="dark"] {'))
        assert not (light - dark), f"tünd rejimdə çatışmayan token: {sorted(light - dark)}"

    def test_system_dark_preference_is_supported(self):
        css = _read(TOKENS)
        assert "prefers-color-scheme: dark" in css
        # Əl ilə "işıqlı" seçimi sistem seçimini üstələməlidir.
        assert ':root:not([data-theme="light"])' in css


class TestHiddenAttribute:
    """Real render testində tapılan səhvin reqressiya qoruyucusu.

    `display` təyin edən hər komponent sinfi brauzerin `[hidden]`
    qaydasını sükutla üstələyir (spesifiklik eyni, sonrakı qalib gəlir).
    Nəticə: `hidden` elementlər GÖRÜNÜR — bizim halda boş qırmızı xəta
    zolaqları hər səhifədə. Testlə tutulmurdu, çünki HTML düzgün idi.
    """

    def test_base_css_forces_hidden_elements_to_stay_hidden(self):
        css = _read(CSS_DIR / "base.css")
        assert re.search(r"\[hidden\]\s*\{[^}]*display:\s*none\s*!important", css), (
            "base.css-də `[hidden] { display: none !important }` qaydası yoxdur"
        )

    def test_components_that_set_display_exist(self):
        """Qoruyucu: display təyin edən komponent qalmayıbsa yuxarıdakı
        test mənasızlaşır."""
        css = _read(CSS_DIR / "components.css")
        assert "display: flex" in css or "display: grid" in css
