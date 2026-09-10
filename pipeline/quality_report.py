"""Auditin nəticəsini insanın oxuya biləcəyi vərəqə çevirir.

Vərəqin məqsədi: insan mənbə materialı yanında açıb hər sualı
«DÜZGÜN / SƏHV» kimi qeyd etsin. Yekun rəqəm buradan çıxır — avtomatik
yoxlamadan yox (bax `pipeline/quality.py` modul qeydi).
"""

from __future__ import annotations

from pipeline.models import MCQQuestion
from pipeline.quality import Finding, QualityReport

_LETTERS = "ABCDE"


def _findings_for(report: QualityReport, number: int) -> list[Finding]:
    return [f for f in report.findings if f.question_number == number]


def format_summary(report: QualityReport) -> str:
    lines = [
        "=" * 72,
        f"AVTOMATİK YOXLAMA — {report.question_count} sual",
        "=" * 72,
        "",
    ]

    set_level = [f for f in report.findings if f.question_number is None]
    per_question = [f for f in report.findings if f.question_number is not None]

    if set_level:
        lines.append("Dəstin bütününə aid:")
        for finding in set_level:
            lines.append(f"  [{finding.severity.value}] {finding.code}: {finding.message}")
        lines.append("")

    if per_question:
        lines.append(f"Ayrı-ayrı suallarda: {len(per_question)} tapıntı")
        for finding in per_question:
            lines.append(
                f"  sual {finding.question_number:>3} "
                f"[{finding.severity.value}] {finding.code}: {finding.message}"
            )
        lines.append("")
    else:
        lines.append("Ayrı-ayrı suallarda avtomatik tapıntı yoxdur.")
        lines.append("")

    if report.question_count:
        order = ", ".join(str(number) for number in report.review_order[:10])
        lines.append(f"Yoxlamağa bu sıra ilə başlayın (ən şübhəli əvvəl): {order}")
        lines.append("")

    lines.append(
        "DİQQƏT: yuxarıdakılar yalnız ŞÜBHƏ əlamətləridir. Cavabın doğru\n"
        "olub-olmadığını avtomatik yoxlamaq MÜMKÜN DEYİL — mənbə materialı\n"
        "oxumaq lazımdır. Yekun rəqəm aşağıdakı vərəqdən çıxır."
    )
    return "\n".join(lines)


def format_review_sheet(questions: list[MCQQuestion], report: QualityReport) -> str:
    if not questions:
        return "Bu dəstdə sual yoxdur."

    lines = [
        format_summary(report),
        "",
        "=" * 72,
        "YOXLAMA VƏRƏQİ",
        "=" * 72,
        "Hər sualı mənbə materialı ilə tutuşdurun və sonundakı sətri",
        "dairəyə alın. Şübhəliləri qeyd bölməsinə yazın.",
        "",
    ]

    for number, question in enumerate(questions, start=1):
        lines.append("-" * 72)
        lines.append(f"{number}. {question.question}")
        lines.append("")
        for index, option in enumerate(question.options):
            mark = "→" if index == question.correct_index else " "
            lines.append(f"   {mark} {_LETTERS[index]}) {option}")
        lines.append("")
        lines.append(f"   İzah: {question.explanation}")

        found = _findings_for(report, number)
        if found:
            lines.append("")
            for finding in found:
                lines.append(f"   ⚠ {finding.code}: {finding.message}")

        lines.append("")
        lines.append("   Qiymət:  DÜZGÜN / SƏHV        Qeyd: ______________________")
        lines.append("")

    lines.append("=" * 72)
    lines.append(f"CƏMİ: {len(questions)} sual")
    lines.append("Düzgün: ____    Səhv: ____    Faiz: ____%")
    lines.append("=" * 72)
    return "\n".join(lines)
