"""Sual dəstinin keyfiyyət auditi.

NƏ EDİR VƏ NƏ ETMİR — bu sərhəd vacibdir:

  EDİR:    obyektiv, yoxlanıla bilən şübhə əlamətlərini sayır (təkrar
           variant, metadata sualı, mövqe əyriliyi, sızdıran uzunluq
           naxışı, zəif izah).

  ETMİR:   cavabın FAKTİKİ olaraq doğru olduğunu deyə bilmir. Bunun
           üçün mənbə materialı oxumaq lazımdır. Üstündən xətt çəkilmiş
           qanun mətni hadisəsi məhz bunu göstərdi: model tam əmin,
           tam səhv cavab verə bilər və heç bir statistik əlamət bunu
           üzə çıxarmır.

Ona görə alətin məqsədi insanı ƏVƏZ ETMƏK deyil, insanın vaxtını
düzgün yerə yönəltməkdir: `review_order` ən şübhəli sualı birinci
qoyur ki, 30 sualdan hansını əvvəl oxumaq lazım olduğu bilinsin.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum

from pipeline.az_legal import AMENDMENT_NUMBER_RE
from pipeline.models import MCQQuestion


class Severity(Enum):
    HIGH = "yuksek"
    MEDIUM = "orta"
    LOW = "asagi"


@dataclass(frozen=True)
class Finding:
    code: str
    severity: Severity
    message: str
    # Dəstin BÜTÜNÜNƏ aid tapıntılarda (məs. mövqe əyriliyi) `None`.
    question_number: int | None = None


@dataclass
class QualityReport:
    question_count: int
    findings: list[Finding] = field(default_factory=list)
    # Sual nömrələri, ən şübhəlidən başlayaraq. İnsan yoxlamağa
    # buradan başlamalıdır.
    review_order: list[int] = field(default_factory=list)


# ---- Mətn normallaşdırma ----------------------------------------------------
# Azərbaycan hərfləri üçün `str.lower()` kifayətdir (İ/ı istisnaları
# müqayisədə problem yaratmır, çünki hər iki tərəf eyni qaydadan keçir).

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = _PUNCT_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip()


# ---- Metadata sualları ------------------------------------------------------
# e-qanun səhifələrində sənədin ÖZÜ haqqında bloklar var. Onlardan
# qurulan sual imtahana hazırlıq üçün dəyərsizdir.

_METADATA_PATTERNS = (
    "derc edil", "dərc edil",
    "qüvvəyə min", "quvveye min",
    "qüvvədədir", "quvvededir",
    "versiya",
    "redaksiya tarix",
    "əlavə edilmiş", "elave edilmis",
    "dəyişiklik tarix", "deyisiklik tarix",
    "sənədin nömrəsi", "senedin nomresi",
    "hansı tarixdə dərc", "hansi tarixde derc",
    "neçənci ildə qəbul", "necenci ilde qebul",
)


def _looks_like_metadata(text: str) -> bool:
    lowered = _normalize(text)
    return any(_normalize(pattern) in lowered for pattern in _METADATA_PATTERNS)


# ---- Ayrı-ayrı sualların yoxlanması ----------------------------------------

def _check_duplicate_options(question: MCQQuestion, number: int) -> list[Finding]:
    seen = [_normalize(option) for option in question.options]
    duplicates = [text for text, count in Counter(seen).items() if count > 1]
    if not duplicates:
        return []
    return [
        Finding(
            code="tekrar_variant",
            severity=Severity.HIGH,
            message="eyni variant iki dəfə verilib - tələbə üçün ikisi də eyni görünür",
            question_number=number,
        )
    ]


def _check_metadata(question: MCQQuestion, number: int) -> list[Finding]:
    if not _looks_like_metadata(question.question):
        return []
    return [
        Finding(
            code="metadata_sual",
            severity=Severity.HIGH,
            message="sual sənədin məzmunu haqqında yox, sənədin ÖZÜ haqqındadır",
            question_number=number,
        )
    ]


def _check_weak_explanation(question: MCQQuestion, number: int) -> list[Finding]:
    """İzah yalnız düzgün variantı təkrarlayırsa, tələbə SƏBƏBİ
    öyrənmir — cavabdan sonra göstərilən izahın bütün dəyəri budur."""
    answer = _normalize(question.options[question.correct_index])
    explanation = _normalize(question.explanation)
    if not explanation:
        remainder = ""
    else:
        remainder = explanation.replace(answer, "").strip()
    if len(remainder) >= 15:
        return []
    return [
        Finding(
            code="zeif_izah",
            severity=Severity.MEDIUM,
            message="izah düzgün variantı təkrarlamaqdan başqa heç nə demir",
            question_number=number,
        )
    ]


# ---- Mətnə istinad edən suallar ---------------------------------------------
# İmtahanda «material» yoxdur. «Materialda qeyd olunan...» sualı bilik
# yox, mətn oxuma yoxlayır — dəyəri sıfırdır.

_MATERIAL_REFERENCE_PATTERNS = (
    "materialda", "materialin", "materialın",
    "metnde qeyd", "mətndə qeyd",
    "verilmis metnde", "verilmiş mətndə",
    "yuxarida qeyd", "yuxarıda qeyd",
    "senedde qeyd", "sənəddə qeyd",
    "parcada", "parçada",
)


def _check_material_reference(question: MCQQuestion, number: int) -> list[Finding]:
    lowered = _normalize(question.question)
    if not any(_normalize(pattern) in lowered for pattern in _MATERIAL_REFERENCE_PATTERNS):
        return []
    return [
        Finding(
            code="materiala_istinad",
            severity=Severity.HIGH,
            message="sual «materialda yazılanı» soruşur - imtahanda material olmur",
            question_number=number,
        )
    ]


# ---- Düzəliş tarixçəsindən qurulan suallar ----------------------------------
# e-qanun səhifələrinin altında düzəliş siyahısı var: «504-IIIQD nömrəli
# Qanun». Model oradan sual qurur. DİQQƏT: e-qanun adi defis (-) YOX,
# U+2011 (non-breaking hyphen) işlədir — hər iki hal tutulmalıdır.

_AMENDMENT_RE = AMENDMENT_NUMBER_RE


def _check_amendment_reference(question: MCQQuestion, number: int) -> list[Finding]:
    haystack = " ".join([question.question, *question.options])
    if not _AMENDMENT_RE.search(haystack):
        return []
    return [
        Finding(
            code="duzelis_tarixcesi",
            severity=Severity.HIGH,
            message="sual qanunun düzəliş tarixçəsindən qurulub - imtahan mövzusu deyil",
            question_number=number,
        )
    ]


# ---- Öz cavabını daşıyan suallar --------------------------------------------

_SELF_ANSWER_MIN_OVERLAP = 0.5
_SELF_ANSWER_MIN_MARGIN = 0.2


def _overlap_with(stem_tokens: set[str], option: str) -> float:
    tokens = set(_normalize(option).split())
    if not tokens:
        return 0.0
    return len(tokens & stem_tokens) / len(tokens)


def _check_self_answering(question: MCQQuestion, number: int) -> list[Finding]:
    """Düzgün variant sualın öz sözlərini QALAN VARİANTLARDAN NƏZƏRƏ
    ÇARPACAQ DƏRƏCƏDƏ ÇOX təkrarlayırsa, cavab materialı bilmədən
    tapılır.

    Fərq vacibdir: normal sualda da açar sözlər təkrarlanır, amma orada
    BÜTÜN variantlar onları paylaşır. Buradakı ölçü mütləq oxşarlıq yox,
    düzgün variantın digərlərindən ÜSTÜNLÜYÜDÜR."""
    stem_tokens = set(_normalize(question.question).split())
    if not stem_tokens:
        return []
    correct = _overlap_with(stem_tokens, question.options[question.correct_index])
    others = [
        _overlap_with(stem_tokens, option)
        for index, option in enumerate(question.options)
        if index != question.correct_index
    ]
    if not others:
        return []
    if correct < _SELF_ANSWER_MIN_OVERLAP:
        return []
    if correct < max(others) + _SELF_ANSWER_MIN_MARGIN:
        return []
    return [
        Finding(
            code="sual_ozunu_cavablayir",
            severity=Severity.HIGH,
            message=(
                "düzgün variant sualın sözlərini təkrarlayır - cavab materialı "
                "bilmədən tapılır"
            ),
            question_number=number,
        )
    ]


_PER_QUESTION_CHECKS = (
    _check_duplicate_options,
    _check_metadata,
    _check_weak_explanation,
    _check_material_reference,
    _check_amendment_reference,
    _check_self_answering,
)


# ---- Dəstin bütününə aid naxışlar ------------------------------------------

_MIN_SET_SIZE_FOR_STATISTICS = 5
_LONGEST_OPTION_THRESHOLD = 0.7
_POSITION_BIAS_THRESHOLD = 0.6


def _check_longest_option_giveaway(questions: list[MCQQuestion]) -> list[Finding]:
    """Düzgün cavab həmişə ən uzun variantdırsa, tələbə materialı
    oxumadan da seçə bilər — sual mənasını itirir."""
    if len(questions) < _MIN_SET_SIZE_FOR_STATISTICS:
        return []
    hits = 0
    for question in questions:
        lengths = [len(option) for option in question.options]
        if lengths[question.correct_index] == max(lengths) and lengths.count(max(lengths)) == 1:
            hits += 1
    share = hits / len(questions)
    if share < _LONGEST_OPTION_THRESHOLD:
        return []
    return [
        Finding(
            code="en_uzun_variant_duzgun",
            severity=Severity.MEDIUM,
            message=(
                f"{hits}/{len(questions)} sualda düzgün cavab ən uzun variantdır - "
                "tələbə materialı oxumadan tapa bilər"
            ),
        )
    ]


def _check_position_bias(questions: list[MCQQuestion]) -> list[Finding]:
    if len(questions) < _MIN_SET_SIZE_FOR_STATISTICS:
        return []
    counts = Counter(question.correct_index for question in questions)
    position, hits = counts.most_common(1)[0]
    share = hits / len(questions)
    if share < _POSITION_BIAS_THRESHOLD:
        return []
    letter = "ABCDE"[position]
    return [
        Finding(
            code="movqe_eyriliyi",
            severity=Severity.MEDIUM,
            message=(
                f"{hits}/{len(questions)} sualda düzgün cavab «{letter}» mövqeyindədir - "
                "variantlar qarışdırılmalıdır"
            ),
        )
    ]


def _check_duplicate_questions(questions: list[MCQQuestion]) -> list[Finding]:
    seen: dict[str, int] = {}
    findings: list[Finding] = []
    for number, question in enumerate(questions, start=1):
        key = _normalize(question.question)
        if key in seen:
            findings.append(
                Finding(
                    code="tekrar_sual",
                    severity=Severity.HIGH,
                    message=f"{seen[key]}-ci sualın təkrarıdır",
                    question_number=number,
                )
            )
        else:
            seen[key] = number
    return findings


_SET_CHECKS = (_check_longest_option_giveaway, _check_position_bias, _check_duplicate_questions)

_SEVERITY_WEIGHT = {Severity.HIGH: 3, Severity.MEDIUM: 2, Severity.LOW: 1}


def audit_questions(questions: list[MCQQuestion]) -> QualityReport:
    findings: list[Finding] = []

    for number, question in enumerate(questions, start=1):
        for check in _PER_QUESTION_CHECKS:
            findings.extend(check(question, number))

    for set_check in _SET_CHECKS:
        findings.extend(set_check(questions))

    # Yoxlama sırası: ən çox şübhə toplayan sual birinci.
    scores: dict[int, int] = {number: 0 for number in range(1, len(questions) + 1)}
    for finding in findings:
        if finding.question_number is not None:
            scores[finding.question_number] += _SEVERITY_WEIGHT[finding.severity]
    review_order = sorted(scores, key=lambda number: (-scores[number], number))

    return QualityReport(
        question_count=len(questions),
        findings=findings,
        review_order=review_order,
    )


def aggregate_findings(reports: dict[int, QualityReport]) -> dict[str, int]:
    """Bir neçə dəstin tapıntılarını koda görə cəmləyir.

    Məqsəd: 94 sualın hamısında hansı problemin NEÇƏ dəfə təkrarlandığını
    görmək. Bir sualda təsadüf ola bilən naxış onlarla sualda sistemli
    problem deməkdir — düzəlişi pipeline-da etmək lazım olduğunu göstərir.
    """
    totals: Counter[str] = Counter()
    for report in reports.values():
        for finding in report.findings:
            totals[finding.code] += 1
    return dict(totals)
