from pipeline.generation import _PROMPT, generate_for_chunks
from pipeline.subjects import subject_note


def test_law_note_forbids_invented_math():
    note = subject_note("qanunvericilik")
    assert "Qanunvericilik" in note and "hesablama" in note
    assert note.endswith("\n\n")


def test_unknown_or_missing_subject_is_empty():
    assert subject_note(None) == subject_note("") == subject_note("yox") == ""


def test_note_sits_outside_material_block():
    text = _PROMPT.format(chunk="MƏTN", n=3, subject_note="FƏNN\n\n", difficulty_note="",
                          retry_note="", format_instructions="F")
    assert text.rindex("---") < text.index("FƏNN")


def test_subject_note_reaches_model():
    seen = []

    def completer(system, user):
        seen.append(user)
        return '{"questions": []}'

    generate_for_chunks(["Konstitusiya 1995-ci ildə qəbul edilib."], {"groq": completer}, order=["groq"],
                        subject_note=subject_note("qanunvericilik"))
    assert "Fənn: Qanunvericilik" in seen[0]
