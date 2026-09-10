"""Düzəliş qeydlərinin mətndən çıxarılması.

NİYƏ: e-qanun səhifələrində hər dəyişdirilmiş bənddən sonra mötərizədə
düzəliş qeydi durur («... 504-IIIQD nömrəli Qanunla əlavə edilmişdir»).
Model oradan sual qurur — real dəstdə (18-ci dəst, 5-ci sual) belə
olub və sual sıfır dəyərli çıxıb.

ƏSAS RİSK: çox silmək. Qanun maddəsinin ÖZÜ heç vaxt itməməlidir —
mötərizə içindəki qeyd silinir, ətrafındakı hökm qalır. Aşağıdakı
testlərin yarısı məhz bunu qoruyur.
"""

from __future__ import annotations

from pipeline.ingestion.web_extractor import _strip_amendment_annotations


class TestAnnotationsAreRemoved:
    def test_a_parenthetical_amendment_note_is_removed(self):
        text = (
            "Dövlət qulluqçusunun sahibkarlıq fəaliyyəti qadağandır. "
            "(7 dekabr 2007-ci il tarixli 504-IIIQD nömrəli Azərbaycan "
            "Respublikası Qanunu ilə əlavə edilmişdir)"
        )
        result = _strip_amendment_annotations(text)
        assert "504" not in result
        assert "Dövlət qulluqçusunun sahibkarlıq fəaliyyəti qadağandır." in result

    def test_the_non_ascii_hyphen_form_is_also_removed(self):
        text = "Hökm qüvvədədir. (1 oktyabr 2007-ci il tarixli 420‑IIIQD nömrəli Qanun ilə)"
        result = _strip_amendment_annotations(text)
        assert "420" not in result
        assert "Hökm qüvvədədir." in result

    def test_several_notes_in_one_paragraph_are_all_removed(self):
        text = (
            "Birinci hökm. (504-IIIQD nömrəli Qanunla) Sonra ikinci hökm. "
            "(420-IIIQD nömrəli Qanunla)"
        )
        result = _strip_amendment_annotations(text)
        assert "504" not in result and "420" not in result
        assert "Birinci hökm." in result
        assert "Sonra ikinci hökm." in result

    def test_square_bracket_notes_are_removed_too(self):
        text = "Maddə qüvvədədir. [12 fevral 2008-ci il tarixli 546-IIIQD nömrəli Qanun]"
        result = _strip_amendment_annotations(text)
        assert "546" not in result
        assert "Maddə qüvvədədir." in result


class TestLawTextIsNeverLost:
    """Ən vacib qrup. Bu testlər sınsa, alət materialı korlayır."""

    def test_a_provision_without_any_note_is_untouched(self):
        text = "Dövlət qulluqçusu elmi və pedaqoji fəaliyyətlə məşğul ola bilər."
        assert _strip_amendment_annotations(text) == text

    def test_an_ordinary_parenthetical_is_kept(self):
        """Qanun mətnində normal mötərizələr var — onlara toxunulmur."""
        text = "Dövlət qulluqçusu (bundan sonra — qulluqçu) vəzifəsini icra edir."
        assert _strip_amendment_annotations(text) == text

    def test_an_article_number_is_not_mistaken_for_an_amendment(self):
        text = "Maddə 23.2-yə əsasən 15 il staj tələb olunur."
        assert _strip_amendment_annotations(text) == text

    def test_a_parenthetical_with_real_content_plus_a_number_is_kept(self):
        """Mötərizə əsl məzmun daşıyırsa, düzəliş nömrəsi olsa belə
        SAXLANILIR — hökmü itirməkdənsə bir qeydi buraxmaq yaxşıdır."""
        text = (
            "Qulluqçu (bu maddənin tələbləri pozulduqda intizam məsuliyyəti "
            "daşıyır, habelə 504-IIIQD nömrəli Qanunun tələbləri tətbiq edilir "
            "və vəzifədən azad edilə bilər) məsuliyyət daşıyır."
        )
        assert _strip_amendment_annotations(text) == text

    def test_empty_text_is_handled(self):
        assert _strip_amendment_annotations("") == ""


class TestSharedPattern:
    def test_the_audit_and_the_extractor_use_the_same_definition(self):
        """İki modul ayrı-ayrı naxış saxlasa, biri yenilənəndə digəri
        geridə qalar və nasazlıq sükutla qayıdar."""
        from pipeline import az_legal
        from pipeline import quality
        assert quality._AMENDMENT_RE is az_legal.AMENDMENT_NUMBER_RE


class TestWiredIntoExtraction:
    """Funksiya yazılıb, amma çağırılmasa heç nə dəyişmir — bu test
    onu qoruyur."""

    def test_extracted_text_has_amendment_notes_removed(self):
        from pipeline.ingestion.web_extractor import _extract_text

        html = (
            "<html><body><article>"
            "<p>Dövlət qulluqçusunun sahibkarlıq fəaliyyəti qadağandır. "
            "(7 dekabr 2007-ci il tarixli 504-IIIQD nömrəli Azərbaycan "
            "Respublikası Qanunu ilə əlavə edilmişdir)</p>"
            "</article></body></html>"
        )
        text = _extract_text(html)
        assert "504" not in text
        assert "sahibkarlıq fəaliyyəti qadağandır" in text
