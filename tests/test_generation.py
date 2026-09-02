import json

from pipeline.generation import generate_for_chunks

_VALID_QUESTION = {
    "question": "Azərbaycanın paytaxtı hansıdır?",
    "options": ["Bakı", "Gəncə", "Sumqayıt", "Şəki", "Naxçıvan"],
    "correct_index": 0,
    "explanation": "Bakı Azərbaycanın paytaxtıdır.",
}


def _valid_batch_json(n: int = 1) -> str:
    return json.dumps({"questions": [_VALID_QUESTION] * n})


def _completers_always_valid(n_per_call: int = 2):
    def completer(system: str, user: str) -> str:
        return _valid_batch_json(n_per_call)

    return {"groq": completer}


def test_generates_questions_for_each_chunk():
    completers = _completers_always_valid(n_per_call=2)
    chunks = ["chunk mətni 1", "chunk mətni 2", "chunk mətni 3"]

    questions, failed = generate_for_chunks(chunks, completers, order=["groq"], questions_per_chunk=2)

    assert len(questions) == 6  # 3 chunk * 2 sual
    assert failed == 0
    assert all(q.question == _VALID_QUESTION["question"] for q in questions)


def test_retries_once_on_malformed_json_then_succeeds():
    call_count = {"n": 0}

    def completer(system: str, user: str) -> str:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return "bu json deyil, sxemə uyğun olmayan sərbəst mətn"
        return _valid_batch_json(1)

    completers = {"groq": completer}
    questions, failed = generate_for_chunks(["tək chunk"], completers, order=["groq"], questions_per_chunk=1)

    assert call_count["n"] == 2  # ilk cəhd + 1 retry
    assert len(questions) == 1
    assert failed == 0


def test_chunk_fails_after_retry_still_exhausted_others_continue():
    def always_broken(system: str, user: str) -> str:
        return "hər zaman sxemə uyğun olmayan cavab"

    def always_valid(system: str, user: str) -> str:
        return _valid_batch_json(1)

    calls = {"broken": 0, "valid": 0}

    def broken_completer(system: str, user: str) -> str:
        calls["broken"] += 1
        return always_broken(system, user)

    def valid_completer(system: str, user: str) -> str:
        calls["valid"] += 1
        return always_valid(system, user)

    # broken_chunk hər iki cəhddə də sxemə uyğun olmayan cavab alacaq,
    # valid_chunk isə ilk cəhddə uğurlu olacaq — completer seçimini chunk
    # mətninə görə edirik ki, hər ikisini eyni sınaqda fərqləndirə bilək.
    def routing_completer(system: str, user: str) -> str:
        if "broken_chunk" in user:
            return broken_completer(system, user)
        return valid_completer(system, user)

    completers = {"groq": routing_completer}
    questions, failed = generate_for_chunks(
        ["broken_chunk mətni", "valid_chunk mətni"],
        completers,
        order=["groq"],
        questions_per_chunk=1,
    )

    assert failed == 1
    assert len(questions) == 1
    assert calls["broken"] == 2  # ilk cəhd + retry, ikisi də uğursuz
    assert calls["valid"] == 1  # ilk cəhddə uğurlu, retry-a ehtiyac yoxdur


def test_empty_chunk_list_returns_empty_result():
    questions, failed = generate_for_chunks([], _completers_always_valid(), order=["groq"])
    assert questions == []
    assert failed == 0
