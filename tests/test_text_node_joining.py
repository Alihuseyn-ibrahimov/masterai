"""Mətn düyünlərinin birləşdirilməsi.

REAL SƏHİFƏDƏ ÖLÇÜLDÜ. e-qanun PDF-dən çevrilmiş HTML-dir və hər xüsusi
Azərbaycan hərfi AYRICA teqdədir:

    <span>Az</span><span>ə</span><span>rbaycan</span>

`get_text(" ", strip=True)` (bizim indiki kod) hər teqin arasına boşluq
qoyur və nəticə pozulur — 40 min sözdən 1613-də:

    "Bu Qanun Az ə rbaycan Respublikas ı Konstitusiyas ı n ı n"

Model belə mətni oxuyur. Ayırıcını silmək isə (get_text("", strip=True))
başqa səhv verir: əsl söz araları da itir və 10 min söz bir-birinə
yapışır («QanunAzərbaycan»).

Düzgün variant `get_text("", strip=False)`-dir: ayırıcı əlavə edilmir,
mənbədəki əsl boşluqlar isə saxlanılır.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from pipeline.ingestion.web_extractor import _block_text, _extract_text


def _block(html: str):
    return BeautifulSoup(html, "html.parser").find("p")


class TestSplitLettersAreRejoined:
    def test_a_word_split_across_tags_is_joined(self):
        assert _block_text(_block("<p><span>Az</span><span>ə</span><span>rbaycan</span></p>")) == "Azərbaycan"

    def test_the_real_space_between_words_survives(self):
        block = _block(
            "<p><span>Az</span><span>ə</span><span>rbaycan</span> "
            "<span>Respublikas</span><span>ı</span></p>"
        )
        assert _block_text(block) == "Azərbaycan Respublikası"

    def test_a_longer_realistic_line(self):
        block = _block(
            "<p><span>Bu Qanun </span><span>Az</span><span>ə</span><span>rbaycan</span> "
            "<span>Respublikas</span><span>ı</span> "
            "<span>Konstitusiyas</span><span>ı</span><span>n</span><span>ı</span><span>n</span> "
            "<span>94-c</span><span>ü</span> <span>madd</span><span>ə</span><span>sinin</span></p>"
        )
        assert _block_text(block) == (
            "Bu Qanun Azərbaycan Respublikası Konstitusiyasının 94-cü maddəsinin"
        )


class TestOrdinaryMarkupIsUnharmed:
    def test_plain_text_is_unchanged(self):
        assert _block_text(_block("<p>Sadə mətn burada.</p>")) == "Sadə mətn burada."

    def test_nested_formatting_keeps_word_boundaries(self):
        assert _block_text(_block("<p>Bu <b>vacib</b> qaydadır.</p>")) == "Bu vacib qaydadır."

    def test_line_breaks_and_extra_whitespace_collapse_to_one_space(self):
        assert _block_text(_block("<p>Birinci\n\n   ikinci\tüçüncü</p>")) == "Birinci ikinci üçüncü"

    def test_empty_block_is_empty(self):
        assert _block_text(_block("<p>   </p>")) == ""


class TestWiredIntoExtraction:
    SPLIT = (
        "<p><span>D</span><span>ö</span><span>vl</span><span>ə</span><span>t</span> "
        "<span>qulluq</span><span>ç</span><span>usu</span></p>"
    )

    def test_the_main_path_no_longer_splits_letters(self):
        """Əsas yol: semantik teqlərdən kifayət qədər mətn toplanır."""
        filler = "<p>" + ("Uzun hüquqi mətn burada davam edir. " * 6) + "</p>"
        html = f"<html><body><article>{self.SPLIT}{filler}</article></body></html>"
        assert "Dövlət qulluqçusu" in _extract_text(html)

    def test_the_fallback_path_no_longer_splits_letters(self):
        """Ehtiyat yolu: mətn qısadır, semantik teqlərdən kifayət
        etmir. Orada da eyni nasazlıq var idi."""
        html = f"<html><body><article>{self.SPLIT}</article></body></html>"
        assert "Dövlət qulluqçusu" in _extract_text(html)
