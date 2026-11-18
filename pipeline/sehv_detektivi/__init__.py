"""Səhv Detektivi: şagirdin həllində ilk səhv addım + səhv növü (QLoRA Qwen2.5-1.5B + sympy).

Ayrı repoda öyrədilib (v3); burada yalnız inferens üçün lazım olan hissələr var:
taksonomiya, prompt (təlimlə bayt-bayt eyni), cavabın parse-ı, sympy yoxlaması, backend-lər.
Təlim, data generatorları və notebook-lar orada qalır. Ətraflı: `pipeline/sehv_detektivi/README.md`.
"""

from .backends import DEFAULT_BASE, LocalBackend, VllmBackend, backend_from_env
from .detector import MAX_STEPS, Calibration, diagnose
from .taxonomy import BY_CODE, DOMAINS, ERROR_TYPES

__all__ = ["BY_CODE", "DEFAULT_BASE", "DOMAINS", "ERROR_TYPES", "MAX_STEPS", "Calibration", "LocalBackend",
           "VllmBackend", "backend_from_env", "diagnose"]
