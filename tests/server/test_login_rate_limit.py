"""Giriş sürət limiti — spec 2026-09-29 §4.2.

(e-poçt, IP) cütü üzrə 15 dəqiqədə 10 SƏHV cəhd → blok. Açar QƏSDƏN
cütdür: yalnız e-poçt üzrə olsaydı, tələbə müəllimin e-poçtuna səhv
şifrə göndərib MÜƏLLİMİ bloklaya bilərdi. Blok doğru şifrəni də
buraxmır — əks halda skript səhvlərdən sonra da təxmini davam etdirərdi.
"""

import pytest
from fastapi.testclient import TestClient

from server.app import app, get_login_rate_limiter, get_token_secret, get_user_store
from server.auth import hash_password
from server.rate_limit import RateLimiter
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"
_PASSWORD = "Doğru-şifrə-1"


@pytest.fixture
def env():
    users = UserStore(":memory:")
    limiter = RateLimiter(max_attempts=10, window_seconds=900)
    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_token_secret] = lambda: _SECRET
    app.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    users.create("muellim@x.az", hash_password(_PASSWORD), "Müəllim")
    yield TestClient(app)
    app.dependency_overrides.clear()


def _login(client, password, *, email="muellim@x.az", ip="1.1.1.1"):
    return client.post("/auth/login", json={"email": email, "password": password},
                       headers={"X-Real-IP": ip})


def test_ten_failures_then_even_correct_password_blocked(env):
    for _ in range(10):
        assert _login(env, "səhv").status_code == 401
    r = _login(env, _PASSWORD)
    assert r.status_code == 429
    assert "token" not in r.json()


def test_nine_failures_still_allow_correct_password(env):
    for _ in range(9):
        _login(env, "səhv")
    assert _login(env, _PASSWORD).status_code == 200


def test_attacker_ip_cannot_lock_out_real_owner(env):
    """Tələbə müəllimin e-poçtuna 10 səhv göndərir — müəllim öz
    cihazından (başqa IP) girə bilməlidir."""
    for _ in range(10):
        _login(env, "səhv", ip="6.6.6.6")
    assert _login(env, _PASSWORD, ip="2.2.2.2").status_code == 200


def test_successful_logins_do_not_count(env):
    for _ in range(25):
        assert _login(env, _PASSWORD).status_code == 200


def test_unknown_email_failures_count(env):
    """Naməlum e-poçt da səhv cəhddir — e-poçt siyahısı yoxlamaq limitsiz olmamalıdır."""
    for _ in range(10):
        _login(env, "x", email="yoxdur@x.az")
    assert _login(env, "x", email="yoxdur@x.az").status_code == 429


def test_email_case_does_not_bypass_limit(env):
    for i in range(10):
        _login(env, "səhv", email="MUELLIM@x.az" if i % 2 else "muellim@X.az")
    assert _login(env, _PASSWORD).status_code == 429
