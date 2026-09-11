"""Sürət limiti — dəvət kodu təxminini praktiki olaraq mümkünsüz edir.

Kodun özü 887 milyon variantlıdır, amma bu rəqəm TƏK BAŞINA müdafiə
deyil: limitsiz halda skript saniyədə minlərlə cəhd edə bilər. Limitlə
birlikdə orta axtarış ≈169 il olur (bax `test_invite_code.py`).

Saat İNYEKSİYA olunur — real `time.sleep` ilə test yazmaq həm yavaş,
həm də dayanıqsızdır.
"""

from __future__ import annotations

from server.rate_limit import RateLimiter


class _Clock:
    """Testin idarə etdiyi saat."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class TestWindow:
    def test_allows_up_to_the_limit(self):
        clock = _Clock()
        limiter = RateLimiter(max_attempts=5, window_seconds=60, clock=clock)
        assert [limiter.allow("ali") for _ in range(5)] == [True] * 5

    def test_blocks_the_next_attempt(self):
        clock = _Clock()
        limiter = RateLimiter(max_attempts=5, window_seconds=60, clock=clock)
        for _ in range(5):
            limiter.allow("ali")
        assert limiter.allow("ali") is False

    def test_window_slides(self):
        """Pəncərə keçəndən sonra cəhdlər yenidən açılır."""
        clock = _Clock()
        limiter = RateLimiter(max_attempts=2, window_seconds=60, clock=clock)
        assert limiter.allow("ali") is True
        assert limiter.allow("ali") is True
        assert limiter.allow("ali") is False

        clock.advance(61)
        assert limiter.allow("ali") is True

    def test_window_is_sliding_not_fixed(self):
        """Sabit pəncərə olsaydı, sərhəddə iki qat cəhd keçərdi."""
        clock = _Clock()
        limiter = RateLimiter(max_attempts=2, window_seconds=60, clock=clock)
        limiter.allow("ali")          # t=0
        clock.advance(59)
        limiter.allow("ali")          # t=59
        clock.advance(2)              # t=61 — yalnız BİRİNCİ cəhd düşdü
        assert limiter.allow("ali") is True    # yer açıldı
        assert limiter.allow("ali") is False   # t=59-dakı hələ pəncərədədir


class TestIsolation:
    def test_keys_do_not_share_a_budget(self):
        """Bir tələbənin cəhdləri digərini bloklamamalıdır."""
        clock = _Clock()
        limiter = RateLimiter(max_attempts=2, window_seconds=60, clock=clock)
        limiter.allow("ali")
        limiter.allow("ali")
        assert limiter.allow("ali") is False
        assert limiter.allow("vali") is True


class TestMemory:
    def test_old_entries_are_pruned(self):
        """Sayğac proses-daxilidir və aylarla işləyir — köhnə açarlar
        yığılıb yaddaşı yeməməlidir."""
        clock = _Clock()
        limiter = RateLimiter(max_attempts=5, window_seconds=60, clock=clock)
        for i in range(100):
            limiter.allow(f"istifadeci-{i}")
        assert limiter.tracked_keys() == 100

        clock.advance(120)
        limiter.allow("yeni")

        # Köhnələr təmizlənməlidir; yalnız yeni açar qalır.
        assert limiter.tracked_keys() == 1

    def test_pruning_does_not_lose_active_keys(self):
        clock = _Clock()
        limiter = RateLimiter(max_attempts=2, window_seconds=60, clock=clock)
        limiter.allow("kohne")
        clock.advance(120)
        limiter.allow("aktiv")
        limiter.allow("aktiv")

        assert limiter.allow("aktiv") is False, "aktiv açar təmizlənmə ilə itdi"


class TestConfiguration:
    def test_spec_defaults_are_five_per_minute(self):
        """Spec-də yazılan dəyər: dəqiqədə 5 cəhd."""
        limiter = RateLimiter()
        assert limiter.max_attempts == 5
        assert limiter.window_seconds == 60
