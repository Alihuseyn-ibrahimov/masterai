"""Səhv Detektivi marşrutu: giriş tələb olunur, həll mətni nömrələrdən təmizlənir, limit,
model qoşulmayanda sympy, model düşəndə məntiq həllinə 503 (uydurma «düzgündür» yox)."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from pipeline.sehv_detektivi import Calibration
from server.app import app, get_diagnose_rate_limiter, get_sehv_detector, get_token_secret, get_user_store
from server.auth import create_token
from server.rate_limit import RateLimiter
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


class FakeBackend:
    name = "fake"

    def __init__(self, text="", fail=False):
        self.text, self.fail, self.calls = text, fail, []

    def generate(self, domain, problem, steps):
        self.calls.append(steps)
        if self.fail:
            raise httpx.ConnectError("tunel düşüb")
        return self.text

    def null_prob(self, domain, problem, steps):
        return None


@pytest.fixture
def env():
    users = UserStore(":memory:")
    course = users.courses.create("Kurs", "exam_prep", trial_days=30, seat_limit=30)
    student = users.create("a@x.az", "h", "Əli", course_id=course["id"])
    detector = {"backend": None, "label": "model qoşulmayıb (yalnız sympy)", "calibration": Calibration()}
    limiter = RateLimiter(3, 600)
    for dep, value in {get_user_store: users, get_token_secret: _SECRET, get_sehv_detector: detector,
                       get_diagnose_rate_limiter: limiter}.items():
        app.dependency_overrides[dep] = (lambda v: lambda: v)(value)
    headers = {"Authorization": f"Bearer {create_token(student['id'], secret=_SECRET)}"}
    yield {"client": TestClient(app), "headers": headers, "detector": detector}
    app.dependency_overrides.clear()


def _post(env, **body):
    return env["client"].post("/me/diagnose", json=body, headers=env["headers"])


def test_requires_login(env):
    assert env["client"].post("/me/diagnose", json={}).status_code == 401
    assert env["client"].get("/me/diagnose").status_code == 401


def test_info_lists_types_and_model_state(env):
    body = env["client"].get("/me/diagnose", headers=env["headers"]).json()
    assert body["model_available"] is False and "sympy" in body["backend"]
    assert len(body["error_types"]) == 14


def test_solution_text_without_model_uses_sympy(env):
    r = _post(env, domain="riyaziyyat", problem="1/2 + 1/3 = ?", solution="1) 1/2 + 1/3\n2) = 2/5\n\n3) Cavab: 2/5")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "error_found" and body["wrong_step"] == 2 and body["source"] == "sympy"
    assert [s["text"] for s in body["steps"]] == ["1/2 + 1/3", "= 2/5", "Cavab: 2/5"]


def test_numbered_steps_are_cleaned(env):
    """Brauzer sətirləri olduğu kimi göndərir: «2) = 2/5» sympy üçün oxunmaz idi və nəticə «yoxlanmadı» çıxırdı."""
    body = _post(env, domain="riyaziyyat", problem="?", steps=["1) 1/2 + 1/3", "2. = 2/5", "3) Cavab: 2/5"]).json()
    assert body["status"] == "error_found" and body["wrong_step"] == 2
    assert body["steps"][1]["text"] == "= 2/5"
    decimal = _post(env, domain="riyaziyyat", problem="?", steps=["2.5 + 1", "= 3.5"]).json()
    assert decimal["steps"][0]["text"] == "2.5 + 1" and decimal["status"] == "correct"


def test_logic_without_model_is_unknown(env):
    body = _post(env, domain="mentiq", problem="?", steps=["Bütün A B-dir", "Deməli hamısı"]).json()
    assert body["status"] == "unknown" and body["source"] == "none"


def test_model_answer(env):
    env["detector"]["backend"] = FakeBackend(json.dumps(
        {"wrong_step": 2, "error_type": "ters_netice", "explanation": "Şərt tərsinə çevrilib."}, ensure_ascii=False))
    body = _post(env, domain="mentiq", problem="?", steps=["Yağış yağırsa yol yaşdır", "Yol yaşdır, deməli yağıb"]).json()
    assert body["status"] == "error_found" and body["error_type"] == "ters_netice" and body["source"] == "model"
    assert "p_null" not in body
    assert body["explanation_source"] == "template" and body["explanation"].startswith("Şərt tərsinə çevrilib.")


def test_backend_down(env):
    env["detector"]["backend"] = FakeBackend(fail=True)
    assert _post(env, domain="mentiq", problem="?", steps=["a", "b"]).status_code == 503
    math = _post(env, domain="riyaziyyat", problem="?", steps=["1/2 + 1/3", "= 5/6"]).json()
    assert math["status"] == "correct" and math["source"] == "sympy" and math["model_error"]


def test_validation(env):
    assert _post(env, domain="riyaziyyat", problem="?").status_code == 422
    assert _post(env, domain="tarix", problem="?", steps=["a"]).status_code == 422
    assert _post(env, domain="mentiq", problem="?", steps=[str(i) for i in range(16)]).status_code == 422


def test_rate_limit(env):
    for _ in range(3):
        assert _post(env, domain="riyaziyyat", problem="?", steps=["2 + 2", "= 4"]).status_code == 200
    assert _post(env, domain="riyaziyyat", problem="?", steps=["2 + 2", "= 4"]).status_code == 429
