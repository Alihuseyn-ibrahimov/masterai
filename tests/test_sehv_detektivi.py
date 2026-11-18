"""Səhv Detektivi inferens qatı: prompt təlimlə eynidir, sympy golden-ə zidd getmir, backend-siz
və sınmış backend-lə də dürüst nəticə verir (heç vaxt «yoxlanmadı»nı «düzgündür» demir)."""

import hashlib
import json
from pathlib import Path

import httpx
import pytest

from pipeline.sehv_detektivi import (
    BY_CODE,
    ERROR_TYPES,
    Calibration,
    LocalBackend,
    VllmBackend,
    backend_from_env,
    diagnose,
)
from pipeline.sehv_detektivi import backends as backends_module
from pipeline.sehv_detektivi.prompts import SYSTEM_PROMPT, SYSTEM_PROMPT_SHORT, format_user
from pipeline.sehv_detektivi.schema import parse_model_output
from pipeline.sehv_detektivi.sympy_check import check_math_steps

GOLDEN = Path(__file__).parent / "fixtures" / "sehv_golden_v2.jsonl"
MATH_BAD = ["1/2 + 1/3", "= 2/5", "Cavab: 2/5"]
MATH_OK = ["1/2 + 1/3", "= 3/6 + 2/6", "= 5/6"]
LOGIC = ["Bütün A B-dir", "Bəzi B C-dir", "Deməli bəzi A C-dir"]


class FakeBackend:
    name = "fake"

    def __init__(self, text='{"wrong_step": null, "error_type": null, "explanation": ""}', p_null=None,
                 fail=False):
        self.text, self.p, self.fail, self.calls = text, p_null, fail, []

    def generate(self, domain, problem, steps):
        self.calls.append((domain, problem, steps))
        if self.fail:
            raise httpx.ConnectError("tunel düşüb")
        return self.text

    def null_prob(self, domain, problem, steps):
        return self.p


def _answer(step, code, text="izah"):
    return json.dumps({"wrong_step": step, "error_type": code, "explanation": text}, ensure_ascii=False)


# ---- adapter ilə eyni prompt -------------------------------------------------------------


def test_prompt_is_byte_identical_to_training():
    """Adapter bu mətnlə öyrədilib (Səhv Detektivi v3, sehv/prompts.py). Bir boşluq fərqi keyfiyyəti salar."""
    assert hashlib.sha256(SYSTEM_PROMPT_SHORT.encode()).hexdigest() == \
        "717268320c71e0b4c712900430b78a049d9c7bb043151794a8fe95ce8f85d6e8"
    assert hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest() == \
        "1586b0a38a3975fa9a93dfa7fd012b48148e6d2d2dfe3efd0d2def15a7583072"
    assert format_user("riyaziyyat", "1/2 + 1/3 = ?", ["1/2 + 1/3", "= 2/5"]) == \
        "Sahə: riyaziyyat\nTapşırıq: 1/2 + 1/3 = ?\nŞagirdin həlli:\n1) 1/2 + 1/3\n2) = 2/5"


def test_taxonomy_has_14_types():
    assert len(ERROR_TYPES) == 14 == len(BY_CODE)
    assert sum(e.domain == "riyaziyyat" for e in ERROR_TYPES) == 8
    assert sum(e.domain == "mentiq" for e in ERROR_TYPES) == 6


# ---- cavabın parse-ı ---------------------------------------------------------------------


def test_parse_model_output():
    obj, err = parse_model_output('```json\n{"wrong_step": "2", "error_type": "hesab_sehvi", "explanation": "x"}\n```')
    assert err is None and obj["wrong_step"] == 2 and obj["error_type"] == "hesab_sehvi"
    obj, _ = parse_model_output('{"wrong_step": 0, "error_type": "uydurma", "explanation": null}')
    assert obj["wrong_step"] is None and obj["error_type"] is None and obj["explanation"] == ""
    assert parse_model_output("bilmirəm")[0] is None
    assert parse_model_output('{"wrong_step": 2,')[0] is None


# ---- sympy -------------------------------------------------------------------------------


def test_sympy_chains():
    assert check_math_steps(MATH_BAD)["wrong_step"] == 2
    assert check_math_steps(MATH_OK)["wrong_step"] is None
    assert check_math_steps(["3x + 5 = 20", "3x = 20 + 5", "3x = 25", "x = 25/3"])["wrong_step"] == 2
    assert check_math_steps(["(8 + 4) : 2 · 3", "= 12 : 2 · 3", "= 12 : 6", "= 2"])["wrong_step"] == 3
    assert check_math_steps(["1/3 : 5/4", "= 1/3 · 4/5", "= 4/15"])["wrong_step"] is None
    assert check_math_steps(LOGIC, domain="mentiq") is None
    assert check_math_steps(["Əvvəl məxrəcləri tapaq", "Sonra toplayaq"]) is None


def test_sympy_never_contradicts_golden():
    """Sympy nə vaxt cavab verirsə, golden etiketi ilə üst-üstə düşməlidir (veto yalnız belə təhlükəsizdir)."""
    checked = 0
    for line in GOLDEN.read_text(encoding="utf-8").splitlines():
        g = json.loads(line)
        s = check_math_steps(g["steps"], g["domain"])
        if s is not None:
            checked += 1
            assert s["wrong_step"] == g["wrong_step"], g["id"]
    assert checked >= 40


# ---- diaqnoz: model + sympy --------------------------------------------------------------


def test_no_backend_math_uses_sympy():
    r = diagnose("riyaziyyat", "1/2 + 1/3 = ?", MATH_BAD)
    assert r["status"] == "error_found" and r["wrong_step"] == 2 and r["source"] == "sympy"
    assert r["error_type"] is None  # növü sympy bilmir
    assert [s["status"] for s in r["steps"]] == ["ok", "wrong", "after_error"]
    assert diagnose("riyaziyyat", "?", MATH_OK)["status"] == "correct"


def test_no_backend_logic_is_unknown_not_correct():
    r = diagnose("mentiq", "Sillogizm", LOGIC)
    assert r["status"] == "unknown" and r["source"] == "none" and r["wrong_step"] is None


def test_model_finds_logic_error():
    backend = FakeBackend(_answer(3, "bezi_hamisi", "Bəzi hamısı deyil."))
    r = diagnose("mentiq", "Sillogizm", LOGIC, backend)
    assert r["status"] == "error_found" and r["source"] == "model"
    assert r["error_type"] == "bezi_hamisi" and r["error_name"] == BY_CODE["bezi_hamisi"].name
    assert backend.calls == [("mentiq", "Sillogizm", LOGIC)]


def test_sympy_vetoes_false_alarm():
    r = diagnose("riyaziyyat", "?", MATH_OK, FakeBackend(_answer(2, "hesab_sehvi")))
    assert r["status"] == "correct" and r["source"] == "model+sympy" and r["agreement"] is False
    off = diagnose("riyaziyyat", "?", MATH_OK, FakeBackend(_answer(2, "hesab_sehvi")),
                   Calibration(sympy_veto=False))
    assert off["status"] == "error_found" and off["source"] == "model"


def test_model_and_sympy_agree_keeps_type():
    r = diagnose("riyaziyyat", "?", MATH_BAD, FakeBackend(_answer(2, "mexrecleri_toplama")))
    assert r["agreement"] is True and r["error_type"] == "mexrecleri_toplama"


def test_wrong_domain_code_is_dropped():
    r = diagnose("mentiq", "?", LOGIC, FakeBackend(_answer(2, "hesab_sehvi")))
    assert r["wrong_step"] == 2 and r["error_type"] is None


def test_out_of_range_step_is_not_correct():
    r = diagnose("mentiq", "?", LOGIC, FakeBackend(_answer(9, "bezi_hamisi")))
    assert r["status"] == "unknown" and r["model_error"]


def test_broken_backend_falls_back_to_sympy():
    r = diagnose("riyaziyyat", "?", MATH_BAD, FakeBackend(fail=True))
    assert r["source"] == "sympy" and r["wrong_step"] == 2 and r["model_error"] == "model cavab vermədi"
    logic = diagnose("mentiq", "?", LOGIC, FakeBackend(fail=True))
    assert logic["status"] == "unknown" and logic["model_error"] == "model cavab vermədi"


def test_garbage_model_output_is_unknown():
    r = diagnose("mentiq", "?", LOGIC, FakeBackend("Məncə hər şey qaydasındadır"))
    assert r["status"] == "unknown" and r["model_error"] == "JSON tapılmadı"


def test_threshold_hook():
    says_error = _answer(2, "bezi_hamisi")
    sure = diagnose("mentiq", "?", LOGIC, FakeBackend(says_error, p_null=0.8), Calibration(null_threshold=0.6))
    assert sure["status"] == "correct" and sure["p_null"] == 0.8
    unsure = diagnose("mentiq", "?", LOGIC, FakeBackend(says_error, p_null=0.3), Calibration(null_threshold=0.6))
    assert unsure["status"] == "error_found"
    # vLLM null_prob vermir: eşik qoyulsa da model cavabı dəyişmir
    nop = diagnose("mentiq", "?", LOGIC, FakeBackend(says_error, p_null=None), Calibration(null_threshold=0.6))
    assert nop["status"] == "error_found" and nop["p_null"] is None


def test_input_validation():
    with pytest.raises(ValueError):
        diagnose("tarix", "?", ["a"])
    with pytest.raises(ValueError):
        diagnose("mentiq", "?", ["  "])
    with pytest.raises(ValueError):
        diagnose("mentiq", "?", [str(i) for i in range(16)])


def test_calibration_from_env():
    assert Calibration.from_env({}) == Calibration(None, True)
    assert Calibration.from_env({"SEHV_NULL_THRESHOLD": "0.55"}).null_threshold == 0.55
    assert Calibration.from_env({"SEHV_NULL_THRESHOLD": "abc"}).null_threshold is None
    assert Calibration.from_env({"SEHV_NULL_THRESHOLD": "1.5"}).null_threshold is None
    assert Calibration.from_env({"SEHV_SYMPY_VETO": "false"}).sympy_veto is False


# ---- backend konfiqurasiyası -------------------------------------------------------------


def test_backend_from_env_defaults_to_none():
    backend, label = backend_from_env({})
    assert backend is None and "sympy" in label
    assert backend_from_env({"SEHV_BACKEND": "off", "SEHV_VLLM_MODEL": "sehv",
                             "VLLM_BASE_URL": "http://x"})[0] is None
    assert backend_from_env({"SEHV_BACKEND": "vllm"})[0] is None
    assert backend_from_env({"SEHV_BACKEND": "nəsə"})[0] is None


def test_backend_from_env_vllm_reuses_base_url():
    backend, label = backend_from_env({"VLLM_BASE_URL": "http://gpu:8000/", "SEHV_VLLM_MODEL": "sehv"})
    assert isinstance(backend, VllmBackend) and label == "vllm (sehv)"
    # yalnız VLLM_BASE_URL (MCQ modeli üçün) Səhv Detektivini AÇMIR: adapter adı lazımdır
    assert backend_from_env({"VLLM_BASE_URL": "http://gpu:8000"})[0] is None


def test_backend_from_env_local(monkeypatch, tmp_path):
    monkeypatch.setattr(backends_module.importlib.util, "find_spec", lambda name: None)
    backend, label = backend_from_env({"SEHV_ADAPTER_PATH": str(tmp_path)})
    assert backend is None and "torch" in label

    monkeypatch.setattr(backends_module.importlib.util, "find_spec", lambda name: object())
    backend, label = backend_from_env({"SEHV_ADAPTER_PATH": str(tmp_path / "yoxdur")})
    assert backend is None and "tapılmadı" in label
    backend, _ = backend_from_env({"SEHV_ADAPTER_PATH": str(tmp_path)})
    assert isinstance(backend, LocalBackend) and backend.adapter == str(tmp_path) and backend._model is None
    hub, _ = backend_from_env({"SEHV_ADAPTER_PATH": "istifadeci/sehv-lora-v3"})
    assert isinstance(hub, LocalBackend) and hub.adapter == "istifadeci/sehv-lora-v3"


def test_vllm_backend_sends_training_prompt():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
            "content": _answer(2, "mexrecleri_toplama")}}]})

    backend = VllmBackend("http://gpu", "sehv", transport=httpx.MockTransport(handler))
    r = diagnose("riyaziyyat", "1/2 + 1/3 = ?", MATH_BAD, backend)
    body = seen[0]
    assert body["model"] == "sehv" and body["temperature"] == 0.0 and body["max_tokens"] == 200
    assert body["messages"][0]["content"] == SYSTEM_PROMPT_SHORT
    assert body["messages"][1]["content"] == format_user("riyaziyyat", "1/2 + 1/3 = ?", MATH_BAD)
    assert r["status"] == "error_found" and r["agreement"] is True
