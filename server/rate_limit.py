"""Sürüşən pəncərəli sürət limiti — proses-daxili.

NİYƏ LAZIMDIR: dəvət kodu 887 milyon variantlıdır, amma bu rəqəm TƏK
BAŞINA müdafiə deyil — limitsiz halda skript saniyədə minlərlə cəhd edə
bilər. Limit ilə birlikdə orta axtarış ≈169 il olur
(bax `tests/server/test_invite_code.py`).

NİYƏ PROSES-DAXİLİ: servis `-w 1` ilə işləyir (bax `deploy/masterai.service`
və `ConnectionManager` modul qeydi) — yəni bir proses var, sayğacı paylaşmaq
üçün Redis kimi xarici asılılıq lazım deyil. Worker sayı artırılarsa BU
FƏRZİYYƏ SINIR və limit worker-lər arasında bölünər.

NİYƏ SAAT İNYEKSİYA OLUNUR: `time.sleep` ilə test həm yavaş, həm
dayanıqsızdır. `clock` parametri yalnız test üçündür.

NİYƏ `monotonic`: `time.time()` sistem saatı düzəlişində (NTP, əl ilə
dəyişmə) geri ata bilər və pəncərə səhv hesablanar.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

# Spec-dəki dəyər: dəqiqədə 5 cəhd. Real tələbə kodu bir-iki dəfə səhv
# yazır — 5 onu sıxmır, amma avtomatik təxmini praktiki olaraq öldürür.
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_WINDOW_SECONDS = 60


class RateLimiter:
    """Açar üzrə sürüşən pəncərə sayğacı.

    Sabit pəncərə DEYİL: sabit pəncərədə sərhəddə iki qat cəhd keçir
    (pəncərənin sonunda 5, təzəsinin əvvəlində daha 5). Burada hər
    cəhdin öz vaxt damğası saxlanılır və yalnız pəncərədən çıxanlar
    düşür.
    """

    def __init__(
        self,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._clock = clock
        # Hər açar üçün cəhd vaxtları; deque, çünki təmizləmə həmişə
        # ƏN KÖHNƏ ucdan gedir (`popleft` O(1), siyahıda `pop(0)` O(n)).
        self._attempts: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Cəhdi qeyd edir və icazə verilib-verilmədiyini qaytarır.

        Rədd edilən cəhd SAYILMIR — əks halda limitə çatan istifadəçi
        hər rədd cavabı ilə pəncərəni özü uzadar və heç vaxt çıxa
        bilməzdi.
        """
        now = self._clock()
        with self._lock:
            self._prune_locked(now)
            attempts = self._attempts.setdefault(key, deque())
            if len(attempts) >= self.max_attempts:
                return False
            attempts.append(now)
            return True

    def tracked_keys(self) -> int:
        """İzlənən açar sayı — yaddaş artımını yoxlamaq üçün."""
        with self._lock:
            return len(self._attempts)

    def _prune_locked(self, now: float) -> None:
        """Pəncərədən çıxmış cəhdləri və boşalan açarları atır.

        Sayğac proses-daxilidir və servis aylarla işləyir — təmizləmə
        olmasa hər səhv kod yazan istifadəçi üçün bir sətir əbədi
        qalardı.
        """
        cutoff = now - self.window_seconds
        empty: list[str] = []
        for key, attempts in self._attempts.items():
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if not attempts:
                empty.append(key)
        for key in empty:
            del self._attempts[key]
