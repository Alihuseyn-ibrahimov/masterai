"""Chrome-un başlaması: yaddaş bayraqları və təkrar cəhd.

REAL PRODUKSİYADA TAPILIB. `show_failures.py` göstərdi ki, 6 uğursuz
dəstin 4-ü eyni səbəbdəndir:

    session not created: DevToolsActivePort file doesn't exist

Bu, Chrome-un start zamanı ÖLMƏSİ deməkdir. Server 512 MB RAM-lıdır,
yaddaş istifadəsi 80%, swap 49% — və eyni URL bəzən işləyir (dəst 6, 8,
18), bəzən yox. Yəni nasazlıq DAİMİ deyil, yaddaş təzyiqindən asılıdır.

İki cavab: Chrome-un yaddaş iştahını azaltmaq və bir dəfə uğursuz
olanda təkrar cəhd etmək.
"""

from __future__ import annotations

import pytest

from pipeline.ingestion import web_extractor


class TestMemoryFlags:
    def test_images_are_disabled(self):
        """Qanun mətnindən sual qururuq — şəkillər heç vaxt lazım deyil,
        amma onların dekodlanması yaddaşın böyük hissəsini yeyir."""
        args = web_extractor._chrome_arguments()
        assert any("imagesEnabled=false" in arg for arg in args)

    def test_the_previously_known_flags_are_still_there(self):
        """Bunlar əvvəlki real nasazlıqdan qalıb — təsadüfən
        silinməməlidir."""
        args = web_extractor._chrome_arguments()
        assert "--no-sandbox" in args
        assert "--disable-dev-shm-usage" in args
        assert "--headless=new" in args

    def test_renderer_processes_are_limited(self):
        """Hər iframe üçün ayrıca proses 512 MB-lıq serverdə dözülməzdir."""
        args = web_extractor._chrome_arguments()
        assert any("renderer-process-limit" in arg for arg in args)


class TestStartupRetry:
    def test_a_driver_that_starts_on_the_first_try_is_returned(self):
        calls = []

        def factory(options=None):
            calls.append(1)
            return "sürücü"

        assert web_extractor._start_driver(factory, sleeper=lambda _: None) == "sürücü"
        assert len(calls) == 1

    def test_a_failed_start_is_retried(self):
        calls = []

        def factory(options=None):
            calls.append(1)
            if len(calls) < 2:
                raise RuntimeError("session not created: DevToolsActivePort file doesn't exist")
            return "sürücü"

        assert web_extractor._start_driver(factory, sleeper=lambda _: None) == "sürücü"
        assert len(calls) == 2, "ikinci cəhd edilməli idi"

    def test_the_last_error_is_raised_after_every_attempt_fails(self):
        def factory(options=None):
            raise RuntimeError("DevToolsActivePort file doesn't exist")

        with pytest.raises(RuntimeError, match="DevToolsActivePort"):
            web_extractor._start_driver(factory, sleeper=lambda _: None)

    def test_it_waits_between_attempts(self):
        """Dərhal təkrar cəhd mənasızdır — yaddaş təzyiqinin azalması
        üçün vaxt lazımdır."""
        waits = []

        def factory(options=None):
            raise RuntimeError("yenə uğursuz")

        with pytest.raises(RuntimeError):
            web_extractor._start_driver(factory, sleeper=waits.append)
        assert waits, "gözləmə olmalıdır"
        assert all(delay > 0 for delay in waits)

    def test_attempts_are_bounded(self):
        """Sonsuz təkrar emalı dondurar."""
        calls = []

        def factory(options=None):
            calls.append(1)
            raise RuntimeError("uğursuz")

        with pytest.raises(RuntimeError):
            web_extractor._start_driver(factory, sleeper=lambda _: None)
        assert len(calls) <= 4
