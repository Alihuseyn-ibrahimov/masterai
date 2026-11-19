"""Şagirdin addım-addım həllində İLK səhv addımı və səhvin növünü tapmaq (model + sympy).

Qərar sırası:
1. Model (QLoRA adapteri, `backends.py`) varsa JSON diaqnoz verir.
2. Kalibrasiya eşiyi (`SEHV_NULL_THRESHOLD`) qoyulubsa VƏ backend «düzgündür» ehtimalını
   (`null_prob`) hesablaya bilirsə, `p_null >= eşik` olanda cavab «düzgündür» olur. Eşik
   `05_kalibrasiya.ipynb`-də YALNIZ val dəstində seçilir; hələ seçilməyib, defolt söndürülüdür.
3. sympy riyazi zənciri oxuya bilirsə onun qərarı üstündür (veto + düzəliş).
4. Model yoxdursa və ya sınıbsa: sympy oxuyursa cavab ondan, oxumursa `status="unknown"`.
   «Yoxlanmadı» heç vaxt «düzgündür» kimi qaytarılmır.

v3 golden: addım 0.69, var/yox 0.76, növ macro-F1 0.71, yalançı həyəcan 0.41. Yəni yalnız
modelin («sympy yoxlamadı») tapdığı səhv TƏKLİFDİR - `source` sahəsi bunu UI-yə deyir.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .explain import CORRECT_TEXT, GENERIC_ERROR, clean_model_text, template_for
from .schema import parse_model_output
from .sympy_check import check_math_steps
from .taxonomy import BY_CODE, DOMAINS

logger = logging.getLogger(__name__)

MAX_STEPS = 15
_SUFFIX = ["cu", "ci", "ci", "cü", "cü", "ci", "cı", "ci", "ci", "cu"]


def ordinal(n: int) -> str:
    """1 → «1-ci», 3 → «3-cü», 6 → «6-cı», 10 → «10-cu» (addım ≤ 15)."""
    return f"{n}-{_SUFFIX[n % 10]}"


@dataclass(frozen=True)
class Calibration:
    """Yalançı həyəcanı azaltmaq üçün qatlar. Yeni qat (məs. məntiq yoxlayıcısı) bura əlavə olunur."""

    null_threshold: float | None = None  # p_null >= bu → «düzgündür»
    sympy_veto: bool = True              # sympy zənciri düzgün tapırsa modelin «səhv var»ı ləğv olunur

    @classmethod
    def from_env(cls, env) -> "Calibration":
        raw = (env.get("SEHV_NULL_THRESHOLD", "") or "").strip()
        threshold = None
        if raw:
            try:
                threshold = float(raw)
            except ValueError:
                logger.warning("SEHV_NULL_THRESHOLD rəqəm deyil (%r), eşik söndürüldü", raw)
            else:
                if not 0.0 < threshold < 1.0:
                    logger.warning("SEHV_NULL_THRESHOLD 0..1 arasında olmalıdır (%s), eşik söndürüldü", raw)
                    threshold = None
        veto = (env.get("SEHV_SYMPY_VETO", "true") or "true").strip().lower() != "false"
        return cls(null_threshold=threshold, sympy_veto=veto)


def _merge(model_out: dict, sym: dict | None) -> dict:
    """Model və sympy nəticəsini birləşdirir (Səhv Detektivi `hybrid.merge`). sympy üstündür."""
    out = dict(model_out)
    out["sympy_checked"] = sym is not None
    out["agreement"] = None if sym is None else (sym["wrong_step"] == out.get("wrong_step"))
    if sym is not None and not out["agreement"]:
        out["model_wrong_step"] = out.get("wrong_step")
        out["wrong_step"] = sym["wrong_step"]
        if sym["wrong_step"] is None:
            out["error_type"] = None
            out["explanation"] = "Sympy yoxlaması bütün addımları düzgün tapdı."
        else:
            out["explanation"] = (f"Sympy yoxlaması: {ordinal(sym['wrong_step'])} addımın qiyməti əvvəlki "
                                  "addımlarla uyğun gəlmir.")
            if out["model_wrong_step"] is None:
                out["error_type"] = None  # növü sympy bilmir
    return out


def _explain(status: str, wrong: int | None, code: str | None, out: dict, source: str) -> tuple[str, str]:
    """İzah və onun mənbəyi: "template" (növə görə hazır mətn), "model" (yoxlanmış model mətni),
    "rule" (sympy / ümumi mətn). Modelin xam izahı heç vaxt yoxlanmadan qaytarılmır: canlı saytda
    (2026-11-19) addım və növ düz olanda belə izah qarışıq idi."""
    # sympy-nin öz mətni: yalnız-sympy nəticəsi və ya sympy modeli düzəldibsə. Qalan halda `out`
    # modelin xam mətnidir və birbaşa göstərilmir.
    sympy_text = out.get("explanation") if source == "sympy" or out.get("agreement") is False else None
    if status == "error_found":
        text = template_for(code)
        if text:
            return text, "template"
        if sympy_text is None and source.startswith("model"):
            text = clean_model_text(out.get("explanation"), wrong)
            if text:
                return text, "model"
        return sympy_text or GENERIC_ERROR, "rule"
    if status == "correct":
        return sympy_text or CORRECT_TEXT, "rule"
    return out.get("explanation") or "", "rule"


def diagnose(domain: str, problem: str, steps: list[str], backend=None,
             calibration: Calibration | None = None) -> dict:
    """Bir həllin diaqnozu. Qaytarır:

    status: "error_found" | "correct" | "unknown"
    wrong_step (1-dən), error_type (kod), error_name, explanation
    explanation_source: "template" | "model" | "rule" - izah haradan gəldi (bax `explain.py`)
    source: "model" | "model+sympy" | "sympy" | "none" - qərarı kim verdi
    sympy_checked, agreement (model ilə sympy razıdırmı; yoxlanmayıbsa None)
    p_null (eşik tətbiq olunubsa), model_error (backend sınıbsa qısa səbəb)
    """
    if domain not in DOMAINS:
        raise ValueError(f"naməlum sahə: {domain}")
    steps = [s.strip() for s in steps if s and s.strip()]
    if not steps:
        raise ValueError("həll boşdur")
    if len(steps) > MAX_STEPS:
        raise ValueError(f"ən çox {MAX_STEPS} addım")
    calibration = calibration or Calibration()

    parsed, model_error, p_null = None, None, None
    if backend is not None:
        try:
            parsed, model_error = parse_model_output(backend.generate(domain, problem, steps))
            if parsed is not None and parsed["wrong_step"] is not None and not 1 <= parsed["wrong_step"] <= len(steps):
                # Olmayan addım: bunu «düzgündür» saymaq zibildən nəticə çıxarmaq olardı.
                parsed, model_error = None, "model olmayan addım göstərdi"
            if parsed is not None and calibration.null_threshold is not None:
                p_null = backend.null_prob(domain, problem, steps)
                if p_null is not None and p_null >= calibration.null_threshold:
                    parsed = {"wrong_step": None, "error_type": None, "explanation": "Həll düzgündür."}
        except Exception as exc:  # şəbəkə, tunel düşüb, GPU yaddaşı - sympy ilə davam
            logger.warning("sehv_detektivi backend=%s xəta: %s", getattr(backend, "name", "?"),
                           type(exc).__name__)
            parsed, model_error = None, "model cavab vermədi"

    sym = check_math_steps(steps, domain)
    if parsed is not None:
        out = _merge(parsed, sym if calibration.sympy_veto else None)
        source = "model+sympy" if out["sympy_checked"] else "model"
    elif sym is not None:
        bad = sym["wrong_step"]
        out = {"wrong_step": bad, "error_type": None, "sympy_checked": True, "agreement": None,
               "explanation": (f"Sympy yoxlaması: {ordinal(bad)} addımın qiyməti əvvəlki addımlarla uyğun gəlmir."
                               if bad else "Bütün addımlar hesabla yoxlandı, səhv tapılmadı.")}
        source = "sympy"
    else:
        out = {"wrong_step": None, "error_type": None, "sympy_checked": False, "agreement": None,
               "explanation": ("Bu həlli avtomatik yoxlaya bilmədik." if backend is None
                               else "Model cavabı oxunmadı, həll yoxlanmadı.")}
        source = "none"

    wrong = out.get("wrong_step")
    wrong = wrong if isinstance(wrong, int) and 1 <= wrong <= len(steps) else None
    code = out.get("error_type") if wrong else None
    if code and BY_CODE[code].domain != domain:  # model başqa sahənin kodunu qaytarıbsa
        code = None
    if source == "none":
        status = "unknown"
    else:
        status = "error_found" if wrong else "correct"
    explanation, explanation_source = _explain(status, wrong, code, out, source)
    return {
        "status": status,
        "wrong_step": wrong,
        "error_type": code,
        "error_name": BY_CODE[code].name if code else None,
        "explanation": explanation,
        "explanation_source": explanation_source,
        "steps": [{"n": i, "text": s,
                   "status": "ok" if wrong is None or i < wrong else ("wrong" if i == wrong else "after_error")}
                  for i, s in enumerate(steps, 1)],
        "source": source,
        "sympy_checked": bool(out.get("sympy_checked")),
        "agreement": out.get("agreement"),
        "p_null": p_null,
        "model_error": model_error,
    }
