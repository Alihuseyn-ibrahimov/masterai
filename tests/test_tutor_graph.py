"""AI tutor agenti (gün 9): LangGraph marşrutlaşdırması saxta LLM ilə."""

import json

from pipeline.rag import Document
from pipeline.tutor_graph import OFFTOPIC_REPLY, classify_intent, contextual_query, parse_quiz, run_tutor

DOCS = [
    Document(key="lesson:1", title="Dərs: Konstitusiya",
             text="Azərbaycan Respublikasının Konstitusiyası 1995-ci il noyabrın 12-də referendumla qəbul edilib. "
                  "Konstitusiyaya əlavə və dəyişikliklər referendum yolu ilə edilir.", meta={"lesson_id": 1}),
    Document(key="summary:2", title="Konspekt: Milli Məclis",
             text="Milli Məclis 125 deputatdan ibarətdir. Deputatlar beş il müddətinə seçilir.",
             meta={"summary_id": 2}),
]

QUIZ_JSON = json.dumps({"question": "Konstitusiya nə vaxt qəbul edilib?",
                        "options": ["1991", "1993", "1995", "1998", "2002"], "correct_index": 2,
                        "explanation": "1995-ci ildə referendumla [1]."}, ensure_ascii=False)


def fake(reply):
    calls = []

    def complete(system, user):
        calls.append((system, user))
        return reply

    return {"fake": complete}, calls


def run(question, reply="Cavab [1].", history=None):
    completers, calls = fake(reply)
    return run_tutor(question, DOCS, history, completers=completers, order=["fake"]), calls


def test_classify_intent():
    assert classify_intent("Məni yoxla") == "quiz"
    assert classify_intent("Konstitusiyadan test ver") == "quiz"
    assert classify_intent("Salam") == "offtopic"
    assert classify_intent("çox sağ olun") == "offtopic"
    # eval dəstində tapıldı (gün 13)
    assert classify_intent("Təşəkkür edirəm") == "offtopic"
    assert classify_intent("Çox sağ ol") == "offtopic"
    assert classify_intent("Konstitusiya nə vaxt qəbul olunub?") == "explain"
    assert classify_intent("Konstitusiya nə vaxt qəbul edilib?") == "explain"


def test_explain_answers_with_cited_source():
    state, calls = run("Konstitusiya nə vaxt qəbul edilib?")
    assert state["kind"] == "answer" and state["answer"] == "Cavab [1]."
    assert len(calls) == 1 and "1995" in calls[0][1]
    assert state["sources"][0].key == "lesson:1"


def test_offtopic_skips_llm():
    state, calls = run("Salam")
    assert state["kind"] == "offtopic" and state["answer"] == OFFTOPIC_REPLY and calls == []


def test_no_matching_passage_skips_llm():
    state, calls = run("Fotosintez prosesi necə gedir?")
    assert state["kind"] == "not_found" and calls == []


def test_model_says_not_in_material():
    state, _ = run("Konstitusiya nə vaxt qəbul edilib?", reply="MATERIALDA_YOXDUR")
    assert state["kind"] == "not_found" and state["sources"] == []


def test_quiz_route_returns_mcq():
    state, calls = run("Konstitusiya üzrə məni yoxla", reply=f"Budur:\n{QUIZ_JSON}")
    assert state["kind"] == "quiz"
    assert state["quiz"].correct_index == 2 and state["quiz"].options[2] == "1995"
    assert "JSON" in calls[0][0]
    assert [d.key for d in state["sources"]] == ["lesson:1"]


def test_broken_quiz_json_is_not_found():
    state, _ = run("Konstitusiya üzrə məni yoxla", reply='{"question": "x", "options": ["a"]}')
    assert state["kind"] == "not_found"


def test_follow_up_uses_previous_question_for_retrieval():
    history = [{"role": "user", "text": "Milli Məclis neçə deputatdan ibarətdir?"},
               {"role": "tutor", "text": "125 deputatdan [1]."}]
    assert contextual_query("Bəs müddəti?", history).startswith("Milli Məclis")
    state, calls = run("Bəs müddəti?", history=history)
    assert state["kind"] == "answer" and "beş il" in calls[0][1]


def test_independent_question_ignores_history():
    history = [{"role": "user", "text": "Milli Məclis neçə deputatdan ibarətdir?"}]
    assert contextual_query("Konstitusiya referendumla qəbul edilib?", history) == \
        "Konstitusiya referendumla qəbul edilib?"


def test_parse_quiz_rejects_out_of_range_index():
    bad = QUIZ_JSON.replace('"correct_index": 2', '"correct_index": 7')
    assert parse_quiz(bad) is None


def test_quiz_topic_strips_command_words():
    from pipeline.tutor_graph import quiz_topic

    assert quiz_topic("Məni yoxla") == ""
    assert quiz_topic("Milli Məclis - məni yoxla") == "milli məclis"
    assert quiz_topic("Konstitusiya üzrə test ver") == "konstitusiya"


def test_quiz_without_topic_picks_material_passage():
    import random

    # Rəqəmsiz quiz: təsadüfi seçilən parça hansı olsa da rəqəm qaydası (gün 20) onu atmır.
    no_numbers = json.dumps({"question": "Konstitusiyaya dəyişiklik necə edilir?",
                             "options": ["Referendumla", "Fərmanla", "Qərarla", "Sərəncamla", "Əmrlə"],
                             "correct_index": 0, "explanation": "Referendum yolu ilə [1]."}, ensure_ascii=False)
    completers, calls = fake(no_numbers)
    state = run_tutor("Məni yoxla", DOCS, [], completers=completers, order=["fake"], rng=random.Random(0))
    assert state["kind"] == "quiz" and len(calls) == 1
    assert "Konstitusiya" in calls[0][1] or "Milli Məclis" in calls[0][1]


def test_short_unrelated_question_is_not_merged_with_history():
    history = [{"role": "user", "text": "Konstitusiya nə vaxt qəbul edilib?"}]
    assert contextual_query("Fotosintez nədir?", history) == "Fotosintez nədir?"
    state, calls = run("Fotosintez xlorofil nədir?", history=history)
    assert state["kind"] == "not_found" and calls == []

