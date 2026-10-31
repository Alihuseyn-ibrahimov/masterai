"""Çox agentli sual yoxlaması (gün 10): saxta LLM ilə qraf məntiqi."""

import json
import threading

from pipeline.models import MCQQuestion
from pipeline.review_team import (
    EDITOR_SYSTEM_PROMPT,
    FACT_SYSTEM_PROMPT,
    PEDAGOGUE_SYSTEM_PROMPT,
    parse_suggestion,
    parse_verdicts,
    review_questions,
)

SOURCE = ("Azərbaycan Respublikasının Konstitusiyası 1995-ci il noyabrın 12-də referendumla qəbul edilib. "
          "Milli Məclis 125 deputatdan ibarətdir. Deputatlar beş il müddətinə seçilir.")


def q(text, options, correct):
    return MCQQuestion(question=text, options=options, correct_index=correct, explanation="İzah.")


GOOD = q("Konstitusiya nə vaxt qəbul edilib?", ["1991", "1993", "1995", "1998", "2002"], 2)
WRONG = q("Milli Məclis neçə deputatdan ibarətdir?", ["100", "101", "120", "125", "150"], 2)
FIXED = {"question": "Milli Məclis neçə deputatdan ibarətdir?", "options": ["100", "101", "120", "125", "150"],
         "correct_index": 3, "explanation": "Milli Məclis 125 deputatdandır."}


def team(fact, pedagogue, editor=json.dumps(FIXED, ensure_ascii=False)):
    calls = []
    lock = threading.Lock()

    def complete(system, user):
        with lock:
            calls.append((system, user))
        return {FACT_SYSTEM_PROMPT: fact, PEDAGOGUE_SYSTEM_PROMPT: pedagogue, EDITOR_SYSTEM_PROMPT: editor}[system]

    return {"x": complete}, calls


def test_wrong_answer_is_flagged_and_editor_suggests_fix():
    completers, calls = team(
        fact='[{"n": 1, "ok": true}, {"n": 2, "ok": false, "issue": "Materialda 125 deputat yazılıb."}]',
        pedagogue='[{"n": 1, "ok": true, "issue": ""}, {"n": 2, "ok": true, "issue": ""}]',
    )
    reviews = review_questions([GOOD, WRONG], SOURCE, completers=completers, order=["x"])
    assert [r.verdict for r in reviews] == ["ok", "fix"]
    assert reviews[1].issues[0].agent == "fact_checker"
    assert reviews[1].suggestion.correct_index == 3
    assert reviews[0].suggestion is None
    # Fakt yoxlayıcı materialdan parça görür, metodist görmür.
    fact_prompt = next(u for s, u in calls if s == FACT_SYSTEM_PROMPT)
    peda_prompt = next(u for s, u in calls if s == PEDAGOGUE_SYSTEM_PROMPT)
    assert "125 deputatdan" in fact_prompt and "Parça" not in peda_prompt
    # Redaktor yalnız problemli sual üçün çağırılır.
    assert sum(1 for s, _ in calls if s == EDITOR_SYSTEM_PROMPT) == 1


def test_all_ok_skips_editor():
    ok = '[{"n": 1, "ok": true}, {"n": 2, "ok": true}]'
    completers, calls = team(fact=ok, pedagogue=ok)
    reviews = review_questions([GOOD, WRONG], SOURCE, completers=completers, order=["x"])
    assert {r.verdict for r in reviews} == {"ok"}
    assert all(s != EDITOR_SYSTEM_PROMPT for s, _ in calls)


def test_missing_agent_answer_is_unchecked_not_ok():
    completers, _ = team(fact="bağışlayın, edə bilmədim", pedagogue='[{"n": 1, "ok": true}, {"n": 2, "ok": true}]')
    reviews = review_questions([GOOD, WRONG], SOURCE, completers=completers, order=["x"])
    assert [r.verdict for r in reviews] == ["unchecked", "unchecked"]


def test_issues_from_both_agents_are_kept():
    completers, _ = team(fact='[{"n": 1, "ok": false, "issue": "Fakt"}]',
                         pedagogue='[{"n": 1, "ok": false, "issue": "Forma"}]')
    review = review_questions([GOOD], SOURCE, completers=completers, order=["x"])[0]
    assert review.verdict == "fix"
    assert sorted(i.agent for i in review.issues) == ["fact_checker", "pedagogue"]


def test_batches_of_eight():
    questions = [GOOD] * 10
    ok = json.dumps([{"n": n, "ok": True} for n in range(1, 11)])
    completers, calls = team(fact=ok, pedagogue=ok)
    reviews = review_questions(questions, SOURCE, completers=completers, order=["x"])
    assert len(reviews) == 10 and all(r.verdict == "ok" for r in reviews)
    assert sum(1 for s, _ in calls if s == FACT_SYSTEM_PROMPT) == 2


def test_parse_verdicts_ignores_unknown_numbers_and_bad_items():
    text = 'Nəticə: [{"n": 1, "ok": false}, {"n": 9, "ok": true}, {"n": "2", "ok": true}, "x"]'
    assert parse_verdicts(text, {1, 2}) == {1: (False, "Problem qeyd olundu, izah verilmədi.")}
    assert parse_verdicts("[pozuq", {1}) == {}


def test_parse_suggestion_rejects_invalid_and_identical():
    assert parse_suggestion('{"question": "x", "options": ["a"], "correct_index": 0}', WRONG) is None
    same = json.dumps({**WRONG.model_dump(exclude={"difficulty"})}, ensure_ascii=False)
    assert parse_suggestion(same, WRONG) is None
    assert parse_suggestion(json.dumps(FIXED, ensure_ascii=False), WRONG).correct_index == 3


def test_empty_bank():
    assert review_questions([], SOURCE, completers={}, order=[]) == []
