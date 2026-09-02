from difflib import SequenceMatcher

from pipeline.models import MCQQuestion

_SIMILARITY_THRESHOLD = 0.85


def filter_duplicates(questions: list[MCQQuestion]) -> list[MCQQuestion]:
    """Sual mətni oxşarlığına görə yaxın-dublikatları süzür, ilkini saxlayır."""
    kept: list[MCQQuestion] = []
    for question in questions:
        is_duplicate = any(
            SequenceMatcher(None, question.question, existing.question).ratio()
            >= _SIMILARITY_THRESHOLD
            for existing in kept
        )
        if not is_duplicate:
            kept.append(question)
    return kept
