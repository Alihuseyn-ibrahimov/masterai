import time

import pytest

from server.auth import (
    InvalidToken,
    create_token,
    hash_password,
    verify_password,
    verify_token,
)

_SECRET = "test-secret-key-32-chars-minimum!!"


class TestPasswordHashing:
    def test_hash_differs_from_plaintext(self):
        assert hash_password("Parol123") != "Parol123"

    def test_verify_accepts_correct_password(self):
        assert verify_password("Parol123", hash_password("Parol123"))

    def test_verify_rejects_wrong_password(self):
        assert not verify_password("Səhv", hash_password("Parol123"))

    def test_same_password_hashes_differently(self):
        # Duz (salt) — eyni şifrə iki fərqli hash verməlidir.
        assert hash_password("Parol123") != hash_password("Parol123")

    def test_handles_non_ascii_password(self):
        # AZ hərfləri olan şifrə (UTF-8) sınmamalıdır.
        h = hash_password("Şifrəm123ə")
        assert verify_password("Şifrəm123ə", h)

    def test_verify_rejects_malformed_hash(self):
        assert not verify_password("Parol123", "bu-hash-deyil")


class TestTokens:
    def test_roundtrip_returns_user_id(self):
        token = create_token(42, secret=_SECRET)
        assert verify_token(token, secret=_SECRET) == 42

    def test_wrong_secret_rejected(self):
        token = create_token(42, secret=_SECRET)
        with pytest.raises(InvalidToken):
            verify_token(token, secret="basqa-secret-key-32-chars-min!!!!")

    def test_garbage_token_rejected(self):
        with pytest.raises(InvalidToken):
            verify_token("bu.token.deyil", secret=_SECRET)

    def test_empty_token_rejected(self):
        with pytest.raises(InvalidToken):
            verify_token("", secret=_SECRET)

    def test_expired_token_rejected(self):
        token = create_token(42, secret=_SECRET, expires_in_seconds=1)
        time.sleep(1.1)
        with pytest.raises(InvalidToken):
            verify_token(token, secret=_SECRET)

    def test_token_without_subject_rejected(self):
        import jwt

        bad = jwt.encode({"foo": "bar"}, _SECRET, algorithm="HS256")
        with pytest.raises(InvalidToken):
            verify_token(bad, secret=_SECRET)

    def test_algorithm_confusion_rejected(self):
        # "alg": "none" ilə imzasız token qəbul edilməməlidir.
        import jwt

        bad = jwt.encode({"sub": "42"}, key="", algorithm="none")
        with pytest.raises(InvalidToken):
            verify_token(bad, secret=_SECRET)


class TestTokenSecret:
    def test_raises_when_env_missing(self, monkeypatch):
        from server.auth import token_secret

        monkeypatch.delenv("JWT_SECRET", raising=False)
        with pytest.raises(RuntimeError):
            token_secret()

    def test_raises_when_env_too_short(self, monkeypatch):
        from server.auth import token_secret

        monkeypatch.setenv("JWT_SECRET", "qisa")
        with pytest.raises(RuntimeError):
            token_secret()

    def test_returns_env_value_when_valid(self, monkeypatch):
        from server.auth import token_secret

        monkeypatch.setenv("JWT_SECRET", _SECRET)
        assert token_secret() == _SECRET
