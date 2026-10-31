"""AI tutor: axtarış və mənbəli cavab (gün 8)."""

from pipeline import rag
from pipeline.rag import BM25, Document, answer_question, split_documents, tokenize

KONST = Document("lesson:1", "Dərs: Konstitusiya",
                 "Azərbaycan Respublikasının Konstitusiyası 1995-ci il noyabrın 12-də referendumla qəbul "
                 "edilib. Dövlət hakimiyyəti qanunvericilik, icra və məhkəmə hakimiyyətlərinə bölünür.",
                 {"lesson_id": 1})
MULKI = Document("summary:2", "Konspekt: Dövlət qulluğu",
                 "Dövlət qulluqçusu vəzifəyə müsabiqə yolu ilə qəbul olunur. Sınaq müddəti 6 aydır.",
                 {"summary_id": 2})


def test_tokenize_handles_azerbaijani_case_and_suffixes():
    # «İ»/«I» düzgün kiçilir, şəkilçili formalar eyni köklə birləşir.
    assert tokenize("İCRA") == ["icra"]
    assert tokenize("IŞIQ")[0].startswith("ışıq")
    assert tokenize("Konstitusiyasının")[0] == tokenize("Konstitusiya")[0]
    assert "nədir" not in tokenize("Konstitusiya nədir")


def test_bm25_ranks_the_relevant_document_first():
    hits = BM25(split_documents([MULKI, KONST])).search("Konstitusiya hansı ildə qəbul edilib?")
    assert hits[0].doc is KONST
    assert BM25(split_documents([MULKI, KONST])).search("sınaq müddəti")[0].doc is MULKI


def test_no_overlap_means_no_llm_call():
    called = []
    result = answer_question("fotosintez xlorofil", [KONST], completers={"x": lambda s, u: called.append(1)},
                             order=["x"])
    assert result.found is False and called == []


def test_answer_cites_only_used_sources_and_prompt_contains_numbered_passages():
    seen = {}

    def llm(system, user):
        seen["system"], seen["user"] = system, user
        return "Konstitusiya 1995-ci ildə referendumla qəbul edilib [1]."

    result = answer_question("Konstitusiya nə vaxt qəbul edilib? Dövlət qulluğu?", [KONST, MULKI],
                             completers={"x": llm}, order=["x"])
    assert result.found
    assert "[1] (Dərs: Konstitusiya)" in seen["user"]
    assert "YALNIZ" in seen["system"]
    assert [d.key for d in result.sources] == ["lesson:1"]


def test_model_not_found_signal_is_reported_as_not_found():
    result = answer_question("Konstitusiya", [KONST], completers={"x": lambda s, u: rag.NOT_FOUND}, order=["x"])
    assert result.found is False and result.answer == "" and result.sources == []


def test_citation_out_of_range_falls_back_to_given_sources():
    sources = rag.cited_sources("Cavab [9].", BM25(split_documents([KONST])).search("Konstitusiya"))
    assert [d.key for d in sources] == ["lesson:1"]
