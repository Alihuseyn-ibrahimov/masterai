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


class TestAmendmentHistoryBlock:
    """REAL SƏHİFƏDƏ ÖLÇÜLDÜ, əvvəlki qayda İŞLƏMƏDİ.

    e-qanun.az/framework/4481 üzərində nəticə:
        mətn                   : 304 958 simvol
        düzəliş nömrəsi, əvvəl : 561
        düzəliş nömrəsi, sonra : 561   ← SIFIR silindi

    Səbəb: qaydanı «düzəliş qeydi mötərizədədir» fərziyyəsi üzərində
    qurmuşdum. Real səhifədə isə sənədin sonunda NÖMRƏLƏNMİŞ SİYAHI var:

        1. 13 fevral 2001-ci il tarixli 74-IIQD nömrəli
        2. 2 iyul 2002-ci il tarixli 359-IIQD nömrəli
        3. 3 dekabr 2002-ci il tarixli 398-IIQD nömrəli

    561 belə sətir. Mötərizə yoxdur, ona görə köhnə qayda heç birinə
    toxunmurdu (silinən 423 simvol yalnız ikiqat boşluqların
    yığışdırılması idi).
    """

    HISTORY = "\n".join(
        f"{i}. {i} fevral 200{i % 9}-ci il tarixli {70 + i}-IIQD nömrəli Qanun"
        for i in range(1, 12)
    )

    def test_a_run_of_history_lines_is_removed(self):
        from pipeline.ingestion.web_extractor import _strip_amendment_history

        text = "Maddə 1. Qanunun məqsədi budur.\n" + self.HISTORY
        result = _strip_amendment_history(text)
        assert "Maddə 1. Qanunun məqsədi budur." in result
        assert "IIQD" not in result

    def test_the_law_body_before_the_block_is_untouched(self):
        from pipeline.ingestion.web_extractor import _strip_amendment_history

        body = (
            "Maddə 20. Dövlət qulluqçusunun vəzifələri.\n"
            "20.1. Sahibkarlıq fəaliyyəti qadağandır.\n"
            "20.2. Elmi fəaliyyət icazəlidir.\n"
        )
        result = _strip_amendment_history(body + self.HISTORY)
        for line in body.strip().splitlines():
            assert line in result

    def test_a_single_isolated_reference_is_kept(self):
        """Bir dənə istinad siyahı deyil — hüquqi mətnin içində ola
        bilər və silinməməlidir."""
        from pipeline.ingestion.web_extractor import _strip_amendment_history

        text = (
            "Maddə 5. Bu maddə 74-IIQD nömrəli Qanunla tənzimlənir.\n"
            "Maddə 6. Digər müddəa.\n"
        )
        assert _strip_amendment_history(text) == text

    def test_two_lines_are_not_enough_to_count_as_a_block(self):
        """Həddi aşağı salsaq təsadüfi iki sətir hüquqi mətni aparar."""
        from pipeline.ingestion.web_extractor import _strip_amendment_history

        text = (
            "1. 13 fevral 2001-ci il tarixli 74-IIQD nömrəli Qanun\n"
            "2. 2 iyul 2002-ci il tarixli 359-IIQD nömrəli Qanun\n"
        )
        assert _strip_amendment_history(text) == text

    def test_text_without_any_history_is_unchanged(self):
        from pipeline.ingestion.web_extractor import _strip_amendment_history

        text = "Maddə 1. Birinci.\nMaddə 2. İkinci.\n"
        assert _strip_amendment_history(text) == text

    def test_history_removal_is_wired_into_extraction(self):
        from pipeline.ingestion.web_extractor import _extract_text

        html = (
            "<html><body><article><p>Sahibkarlıq fəaliyyəti qadağandır.</p>"
            + "".join(
                f"<p>{i}. {i} fevral 200{i % 9}-ci il tarixli {70 + i}-IIQD nömrəli Qanun</p>"
                for i in range(1, 12)
            )
            + "</article></body></html>"
        )
        text = _extract_text(html)
        assert "Sahibkarlıq fəaliyyəti qadağandır." in text
        assert "IIQD" not in text


class TestCleaningChainIsSingleSource:
    """Diaqnostika zənciri əl ilə təkrar yazırdı və yeni addım ora
    düşmədi — ölçü «heç nə silinmir» dedi, halbuki qayda işləyirdi.
    İndi zəncir bir funksiyadadır."""

    def test_the_chain_applies_both_rules(self):
        from pipeline.ingestion.web_extractor import _clean_legal_text

        history = "\n".join(
            f"{i}. {i} fevral 2001-ci il tarixli {70 + i}-IIQD nömrəli"
            for i in range(1, 6)
        )
        text = (
            "Maddə 1. Hökm. (7 dekabr 2007-ci il tarixli 504-IIIQD nömrəli "
            "Qanunla əlavə edilmişdir)\n" + history
        )
        result = _clean_legal_text(text)
        assert "504" not in result, "mötərizəli qeyd silinmədi"
        assert "IIQD" not in result, "tarixçə bloku silinmədi"
        assert "Maddə 1. Hökm." in result

    def test_extraction_uses_the_chain(self):
        from pipeline.ingestion import web_extractor

        inspect_source = __import__("inspect").getsource(web_extractor._extract_text)
        assert "_clean_legal_text" in inspect_source, (
            "_extract_text zənciri birbaşa çağırmalıdır"
        )


class TestHistoryEntriesWithContinuationLines:
    """REAL SƏHİFƏDƏ TAPILDI (ikinci ölçü). Tarixçə yazıları bir sətirdə
    bitmir — hər yazıdan sonra davam sətri gəlir:

        1. 13 fevral 2001-ci il tarixli 74-IIQD nömrəli
        Azərbaycan Respublikasının Qanunu (Qanunvericilik Toplusu...)
        2. 2 iyul 2002-ci il tarixli 359-IIQD nömrəli
        Azərbaycan Respublikasının Qanunu

    «Ardıcıl üç sətir» tələbi ona görə heç vaxt ödənmirdi: ölçüldü,
    ən uzun seriya 1 idi. İndi qayda KLASTER üzrə işləyir.
    """

    ENTRY = "{i}. {i} fevral 2001-ci il tarixli {n}-IIQD nömrəli"
    CONT = "Azərbaycan Respublikasının Qanunu (Qanunvericilik Toplusu, 2001, № {i})"

    def _history(self, count: int) -> str:
        lines = []
        for i in range(1, count + 1):
            lines.append(self.ENTRY.format(i=i, n=70 + i))
            lines.append(self.CONT.format(i=i))
        return "\n".join(lines)

    def test_entries_separated_by_continuation_lines_are_removed(self):
        from pipeline.ingestion.web_extractor import _strip_amendment_history

        body = "Maddə 20. Sahibkarlıq fəaliyyəti qadağandır."
        result = _strip_amendment_history(body + "\n" + self._history(5))
        assert body in result
        assert "IIQD" not in result
        assert "Qanunvericilik Toplusu" not in result, "davam sətirləri də getməlidir"

    def test_two_entries_are_still_not_enough(self):
        from pipeline.ingestion.web_extractor import _strip_amendment_history

        text = "Maddə 1. Hökm.\n" + self._history(2)
        assert _strip_amendment_history(text) == text

    def test_far_apart_stray_references_are_not_joined_into_one_block(self):
        """ƏN TƏHLÜKƏLİ HAL. Sənədin əvvəlində və sonunda tək-tək
        istinadlar varsa, onların ARASINDAKI bütün qanun mətni
        silinməməlidir."""
        from pipeline.ingestion.web_extractor import _strip_amendment_history

        middle = "\n".join(f"Maddə {i}. Vacib hüquqi müddəa {i}." for i in range(1, 40))
        text = (
            "Maddə 0. Bu 74-IIQD nömrəli Qanunla tənzimlənir.\n"
            + middle
            + "\nSon qeyd: 359-IIQD nömrəli Qanun.\n"
        )
        result = _strip_amendment_history(text)
        for i in range(1, 40):
            assert f"Maddə {i}. Vacib hüquqi müddəa {i}." in result, (
                f"Maddə {i} silinib — aradakı mətn itirilir"
            )

    def test_the_block_is_removed_whole_including_its_tail(self):
        from pipeline.ingestion.web_extractor import _strip_amendment_history

        body = "Maddə 20. Hökm."
        text = body + "\n" + self._history(4)
        result = _strip_amendment_history(text)
        assert result.strip() == body
