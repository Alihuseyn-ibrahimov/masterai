"""Sual keyfiyyəti auditinin testləri.

VACİB SƏRHƏD: bu modul cavabın DOĞRU olub-olmadığını BİLMİR — bunu
yalnız mənbə materialı oxuyan insan deyə bilər. Modul yalnız obyektiv
şübhə əlamətlərini sayır və insana hansı sualdan başlamağı göstərir.
Bu sərhəd `test_audit_never_claims_an_answer_is_correct` ilə qorunur.
"""

from __future__ import annotations

from pipeline.models import MCQQuestion
from pipeline.quality import Severity, audit_questions


def q(
    question: str = "Sual mətni nədir?",
    options: list[str] | None = None,
    correct_index: int = 0,
    explanation: str = "Çünki qanunun 5-ci maddəsi bunu birbaşa göstərir.",
) -> MCQQuestion:
    return MCQQuestion(
        question=question,
        options=options or ["Birinci", "İkinci", "Üçüncü", "Dördüncü", "Beşinci"],
        correct_index=correct_index,
        explanation=explanation,
    )


class TestDuplicateOptions:
    def test_identical_options_are_flagged(self):
        report = audit_questions([q(options=["Bir", "Bir", "İki", "Üç", "Dörd"])])
        assert any(f.code == "tekrar_variant" for f in report.findings)

    def test_options_differing_only_by_case_and_spacing_are_flagged(self):
        """«Sahibkarlıq» və «sahibkarlıq  » eyni variantdır; tələbə
        üçün ikisi də eyni görünür."""
        report = audit_questions([q(options=["Sahibkarlıq", "sahibkarlıq  ", "İki", "Üç", "Dörd"])])
        assert any(f.code == "tekrar_variant" for f in report.findings)

    def test_distinct_options_are_not_flagged(self):
        report = audit_questions([q()])
        assert not any(f.code == "tekrar_variant" for f in report.findings)


class TestDuplicateQuestions:
    def test_the_same_question_twice_is_flagged(self):
        report = audit_questions([q(question="Nə vaxt qüvvəyə minir?"), q(question="Nə vaxt qüvvəyə minir?")])
        assert any(f.code == "tekrar_sual" for f in report.findings)

    def test_different_questions_are_not_flagged(self):
        report = audit_questions([q(question="Birinci sual?"), q(question="Tamam başqa ikinci sual?")])
        assert not any(f.code == "tekrar_sual" for f in report.findings)


class TestMetadataQuestions:
    """e-qanun səhifələrində sənədin ÖZÜ haqqında bloklar var
    (qüvvəyə minmə tarixi, versiyalar, dərc məlumatı). Onlardan sual
    qurmaq mənasızdır — imtahanda belə sual çıxmır."""

    def test_question_about_publication_metadata_is_flagged(self):
        report = audit_questions([q(question="Bu sənəd hansı tarixdə dərc edilmişdir?")])
        assert any(f.code == "metadata_sual" for f in report.findings)

    def test_question_about_document_content_is_not_flagged(self):
        report = audit_questions([q(question="Dövlət qulluqçusuna nə qadağandır?")])
        assert not any(f.code == "metadata_sual" for f in report.findings)


class TestLongestOptionGiveaway:
    """Klassik test səhvi: düzgün cavab həmişə ən uzun variantdır.
    Bir sualda təsadüf ola bilər, dəstin çoxunda isə model sızdırır."""

    def test_a_set_where_the_longest_option_is_always_correct_is_flagged(self):
        questions = [
            q(options=["Qısa", "Qısa da", "Bu variant hamısından xeyli uzundur və izahlıdır", "Yenə qısa", "Qısa"], correct_index=2)
            for _ in range(5)
        ]
        report = audit_questions(questions)
        assert any(f.code == "en_uzun_variant_duzgun" for f in report.findings)

    def test_a_balanced_set_is_not_flagged(self):
        questions = [q(options=["Bir", "İki", "Üç", "Dörd", "Beş"], correct_index=i % 5) for i in range(5)]
        report = audit_questions(questions)
        assert not any(f.code == "en_uzun_variant_duzgun" for f in report.findings)


class TestAnswerPositionBias:
    def test_every_answer_in_the_same_position_is_flagged(self):
        report = audit_questions([q(correct_index=1) for _ in range(10)])
        assert any(f.code == "movqe_eyriliyi" for f in report.findings)

    def test_spread_answers_are_not_flagged(self):
        report = audit_questions([q(correct_index=i % 5) for i in range(10)])
        assert not any(f.code == "movqe_eyriliyi" for f in report.findings)

    def test_bias_is_not_reported_for_a_tiny_set(self):
        """Üç sualda hamısı «B» olsa bu, statistika deyil, təsadüfdür —
        yalan həyəcan siqnalı verməmək üçün minimum həcm tələb olunur."""
        report = audit_questions([q(correct_index=1) for _ in range(3)])
        assert not any(f.code == "movqe_eyriliyi" for f in report.findings)


class TestWeakExplanation:
    def test_an_explanation_that_only_repeats_the_answer_is_flagged(self):
        report = audit_questions([
            q(options=["Sahibkarlıq fəaliyyəti", "Bir", "İki", "Üç", "Dörd"],
              correct_index=0,
              explanation="Sahibkarlıq fəaliyyəti."),
        ])
        assert any(f.code == "zeif_izah" for f in report.findings)

    def test_a_substantive_explanation_is_not_flagged(self):
        report = audit_questions([q()])
        assert not any(f.code == "zeif_izah" for f in report.findings)


class TestReportShape:
    def test_empty_set_produces_no_findings_and_says_so(self):
        report = audit_questions([])
        assert report.question_count == 0
        assert report.findings == []

    def test_findings_carry_the_question_number_a_human_can_look_up(self):
        report = audit_questions([q(), q(options=["Bir", "Bir", "İki", "Üç", "Dörd"])])
        finding = next(f for f in report.findings if f.code == "tekrar_variant")
        # İnsan çap olunmuş vərəqdə «2» nömrəli sualı axtaracaq.
        assert finding.question_number == 2

    def test_set_level_findings_have_no_question_number(self):
        report = audit_questions([q(correct_index=1) for _ in range(10)])
        finding = next(f for f in report.findings if f.code == "movqe_eyriliyi")
        assert finding.question_number is None

    def test_review_order_puts_the_most_suspicious_question_first(self):
        clean = q(question="Tamamilə qaydasında olan sual?")
        dirty = q(question="Bu sənəd hansı tarixdə dərc edilmişdir?",
                  options=["Bir", "Bir", "İki", "Üç", "Dörd"])
        report = audit_questions([clean, dirty])
        assert report.review_order[0] == 2

    def test_audit_never_claims_an_answer_is_correct(self):
        """Sərhəd qoruyucusu. Modul faktiki doğruluğu ölçə BİLMİR;
        belə bir iddia sonradan əlavə olunsa, bu test onu tutmalıdır."""
        report = audit_questions([q()])
        assert not hasattr(report, "accuracy")
        assert not hasattr(report, "correct_count")


class TestSeverity:
    def test_structural_problems_outrank_stylistic_ones(self):
        report = audit_questions([q(options=["Bir", "Bir", "İki", "Üç", "Dörd"])])
        finding = next(f for f in report.findings if f.code == "tekrar_variant")
        assert finding.severity is Severity.HIGH


class TestAggregateAcrossSets:
    """`--all` rejimi: bir çağırışda bütün hazır dəstləri yoxlayır.
    İnsan vaxtı sərf etmədən ümumi mənzərəni verir."""

    def test_counts_are_summed_across_sets(self):
        from pipeline.quality import aggregate_findings
        set_a = audit_questions([q(question="Bu sənəd hansı tarixdə dərc edilmişdir?")])
        set_b = audit_questions([q(question="Neçənci ildə qəbul edilmişdir?")])
        totals = aggregate_findings({1: set_a, 2: set_b})
        assert totals["metadata_sual"] == 2

    def test_sets_without_findings_do_not_appear(self):
        from pipeline.quality import aggregate_findings
        totals = aggregate_findings({1: audit_questions([q()])})
        assert totals == {}

    def test_empty_input_gives_empty_totals(self):
        from pipeline.quality import aggregate_findings
        assert aggregate_findings({}) == {}


class TestSelfAnsweringQuestion:
    """Real dəstdə tapılıb (dəst 18, sual 5): sual öz cavabını içində
    daşıyırdı. «hansının tarixi 7 dekabr 2007 və nömrəsi 504-IIIQD-dir?»
    → cavab: «7 dekabr 2007-ci il tarixli 504-IIIQD nömrəli...».
    Dili bilməyən adam da tapar. Alət bunu görmürdü."""

    def test_an_option_that_repeats_the_stem_is_flagged(self):
        report = audit_questions([
            q(
                question="Aşağıdakı qanunlardan hansının qəbul tarixi 7 dekabr 2007-ci il və nömrəsi 504-IIIQD-dir?",
                options=[
                    "7 dekabr 2007-ci il tarixli 504-IIIQD nömrəli Azərbaycan Respublikası Qanunu",
                    "1 oktyabr 2007-ci il tarixli 420-IIIQD nömrəli Azərbaycan Respublikası Qanunu",
                    "31 may 2007-ci il tarixli 356-IIIQD nömrəli Azərbaycan Respublikası Qanunu",
                    "19 oktyabr 2007-ci il tarixli 458-IIIQD nömrəli Azərbaycan Respublikası Qanunu",
                    "12 fevral 2008-ci il tarixli 546-IIIQD nömrəli Azərbaycan Respublikası Qanunu",
                ],
                correct_index=0,
            )
        ])
        assert any(f.code == "sual_ozunu_cavablayir" for f in report.findings)

    def test_a_normal_question_sharing_topic_words_is_not_flagged(self):
        """Yalan həyəcan qoruyucusu: normal sualda da açar sözlər
        təkrarlanır. Fərq odur ki, orada BÜTÜN variantlar eyni sözləri
        paylaşır, düzgün olan seçilmir."""
        report = audit_questions([
            q(
                question="Dövlət qulluqçusunun rotasiyası nə deməkdir?",
                options=[
                    "Dövlət qulluqçusunun eyni vəzifədə qalması",
                    "Dövlət qulluqçusunun başqa vəzifəyə köçürülməsi",
                    "Dövlət qulluqçusunun təqaüdə çıxması",
                    "Dövlət qulluqçusunun məvacibinin artırılması",
                    "Dövlət qulluqçusunun təlimə göndərilməsi",
                ],
                correct_index=1,
            )
        ])
        assert not any(f.code == "sual_ozunu_cavablayir" for f in report.findings)


class TestMaterialReference:
    """Real dəstdə tapılıb (dəst 18, sual 2): «Materialda qeyd olunan...».
    İmtahanda «material» yoxdur — bu, bilik sualı deyil, mətn oxuma
    sualıdır."""

    def test_a_question_referring_to_the_material_is_flagged(self):
        report = audit_questions([q(question="Materialda qeyd olunan dördüncü təsnifat hansıdır?")])
        assert any(f.code == "materiala_istinad" for f in report.findings)

    def test_reference_to_the_law_itself_is_not_flagged(self):
        report = audit_questions([q(question="Qanunun 20.1-ci maddəsinə əsasən nə qadağandır?")])
        assert not any(f.code == "materiala_istinad" for f in report.findings)


class TestAmendmentReference:
    """e-qanun səhifələrinin altındakı düzəliş siyahısı («504-IIIQD
    nömrəli Qanun») modelə gedir və oradan sual qurulur. İmtahanda belə
    sual çıxmır."""

    def test_a_law_amendment_number_is_flagged(self):
        report = audit_questions([q(question="504-IIIQD nömrəli qanun nə vaxt qəbul edilib?")])
        assert any(f.code == "duzelis_tarixcesi" for f in report.findings)

    def test_the_non_ascii_hyphen_used_by_e_qanun_is_also_caught(self):
        """e-qanun mətnində adi defis YOX, U+2011 işlədilir. Bunu
        nəzərə almasaq naxış sükutla keçib gedir."""
        report = audit_questions([q(question="504‑IIIQD nömrəli qanun nə vaxt qəbul edilib?")])
        assert any(f.code == "duzelis_tarixcesi" for f in report.findings)

    def test_an_ordinary_article_reference_is_not_flagged(self):
        report = audit_questions([q(question="Qanunun 23.2-ci maddəsi nəyi tənzimləyir?")])
        assert not any(f.code == "duzelis_tarixcesi" for f in report.findings)
