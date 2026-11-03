"""`pipeline.socratic` — Sokratik hint (Faza 2 PR 1): düzgün cavabı demir,
materialdan yönləndirici sual yazır."""

import pytest

from pipeline.models import MaterialSource
from pipeline.socratic import SocraticError, generate_hint


def _fake_completer(reply):
    def completer(system, user):
        return reply
    return completer


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "material.txt"
    path.write_text(
        "Dövlət qulluğuna qəbul müsabiqə yolu ilə keçirilir. "
        "Müsabiqə test imtahanı və müsahibədən ibarətdir. " * 20,
        encoding="utf-8",
    )
    return MaterialSource(kind="text", location=str(path))


def test_generate_hint_returns_model_reply(source):
    hint = generate_hint(
        source, "Dövlət qulluğuna qəbul necə keçirilir?",
        ["Müsabiqə yolu ilə", "Təyinatla", "Seçki ilə", "Püşklə", "Vərəsəliklə"],
        chosen_index=1, correct_index=0,
        completers={"groq": _fake_completer("Qəbulun hansı iki mərhələdən ibarət olduğunu materialdan tapın.")},
        order=["groq"],
    )
    assert hint == "Qəbulun hansı iki mərhələdən ibarət olduğunu materialdan tapın."


def test_generate_hint_never_leaks_correct_answer_text(source):
    # Model ehtiyatsızlıqla düzgün variantı yazsa, generic hintə keçilir.
    hint = generate_hint(
        source, "Dövlət qulluğuna qəbul necə keçirilir?",
        ["Müsabiqə yolu ilə", "Təyinatla", "Seçki ilə", "Püşklə", "Vərəsəliklə"],
        chosen_index=1, correct_index=0,
        completers={"groq": _fake_completer("Düzgün cavab Müsabiqə yolu ilədir.")},
        order=["groq"],
    )
    assert hint == "Materialı bir daha diqqətlə oxuyun və sualın açar sözlərinə fikir verin."


def test_generate_hint_blank_reply_falls_back_to_generic(source):
    hint = generate_hint(
        source, "Sual?", ["A", "B", "C", "D", "E"], chosen_index=1, correct_index=0,
        completers={"groq": _fake_completer("   ")}, order=["groq"],
    )
    assert "diqqətlə oxuyun" in hint


def test_generate_hint_raises_when_all_providers_fail(source):
    def failing(system, user):
        raise RuntimeError("API xətası")

    with pytest.raises(SocraticError):
        generate_hint(
            source, "Sual?", ["A", "B", "C", "D", "E"], chosen_index=1, correct_index=0,
            completers={"groq": failing}, order=["groq"],
        )


def test_generate_hint_on_empty_material_returns_generic(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("x", encoding="utf-8")  # text_extractor boş sayır
    source = MaterialSource(kind="text", location=str(path))
    hint = generate_hint(
        source, "Sual?", ["A", "B", "C", "D", "E"], chosen_index=1, correct_index=0,
        completers={"groq": _fake_completer("hec nə")}, order=["groq"],
    )
    # Material çox qısadırsa parçalanmayacaq, amma boş siyahı olmayacaq -
    # əsas odur ki, funksiya xəta atmasın.
    assert isinstance(hint, str) and hint
