"""Model cavabının parse edilməsi (Səhv Detektivi reposundan, `sehv/schema.py`, v3)."""

import json
import re

from .taxonomy import BY_CODE

_JSON_RE = re.compile(r"\{.*\}", re.S)


def parse_model_output(text: str) -> tuple[dict | None, str | None]:
    """Model mətnindən JSON çıxarır. (obj, None) və ya (None, xəta_mesajı) qaytarır.

    Model bəzən ```json ... ``` bloku və ya əlavə söz yazır, ona görə ilk '{' ilə son '}'
    arasını götürürük. Naməlum səhv kodu None olur (sual itmir, növü «naməlum» qalır).
    """
    m = _JSON_RE.search(text or "")
    if not m:
        return None, "JSON tapılmadı"
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return None, f"JSON pozuqdur: {e.msg}"
    if not isinstance(obj, dict):
        return None, "JSON obyekt deyil"
    ws = obj.get("wrong_step")
    if isinstance(ws, str) and ws.strip().isdigit():
        ws = int(ws)
    if ws in ("null", "", 0):
        ws = None
    obj["wrong_step"] = ws if isinstance(ws, int) and not isinstance(ws, bool) else None
    et = obj.get("error_type")
    obj["error_type"] = et if et in BY_CODE else None
    obj["explanation"] = str(obj.get("explanation") or "")
    return obj, None
