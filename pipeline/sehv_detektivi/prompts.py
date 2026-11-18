"""Modelə gedən prompt. Təlimdə də, inferensdə də EYNİ funksiyalar işlədilir.

Vacib: prompt təlim zamanı necədirsə, inferensdə də elə olmalıdır. Bir boşluq
fərqi belə adapterin keyfiyyətini aşağı sala bilər.

Səhv Detektivi reposundan (`sehv/prompts.py`, v3) DƏYİŞMƏDƏN köçürülüb.
`tests/test_sehv_detektivi.py` mətnin hash-ini orijinalla müqayisə edir.
"""
import json

from .taxonomy import DOMAINS, ERROR_TYPES


def _type_list() -> str:
    lines = []
    for dom in DOMAINS:
        lines.append(f"[{dom}]")
        for e in ERROR_TYPES:
            if e.domain == dom:
                lines.append(f"- {e.code}: {e.definition}")
    return "\n".join(lines)


SYSTEM_PROMPT = (
    "Sən 'Səhv Detektivi'sən: şagirdin addım-addım həllində İLK səhv addımı tapırsan.\n"
    "Yalnız JSON qaytar, başqa heç nə yazma. Format:\n"
    '{"wrong_step": <addımın nömrəsi və ya null>, "error_type": <kod və ya null>, '
    '"explanation": "<1-2 cümlə, Azərbaycan dilində>"}\n'
    "Həll tam düzgündürsə wrong_step və error_type null olur.\n"
    "error_type yalnız aşağıdakı kodlardan biri ola bilər və tapşırığın sahəsinə uyğun olmalıdır:\n"
    + _type_list()
)


# Qısa prompt: adapter təlimdə səhv növlərinin mənasını onsuz da öyrənir, ona görə
# təriflərə ehtiyac yoxdur. Uzun prompt ~900 token, qısa ~150 token: təlim ~4 dəfə sürətlənir.
# Base model (adaptersiz) isə tam tərifləri görməlidir, yoxsa kodların mənasını bilməz.
SYSTEM_PROMPT_SHORT = (
    "Sən 'Səhv Detektivi'sən: şagirdin həllində İLK səhv addımı tap. Yalnız JSON qaytar: "
    '{"wrong_step": <nömrə və ya null>, "error_type": <kod və ya null>, "explanation": "<1-2 cümlə>"}\n'
    "Kodlar: " + "; ".join(f"{d}: " + ", ".join(e.code for e in ERROR_TYPES if e.domain == d) for d in DOMAINS)
)


def format_user(domain: str, problem: str, steps: list[str]) -> str:
    numbered = "\n".join(f"{i}) {s}" for i, s in enumerate(steps, start=1))
    return f"Sahə: {domain}\nTapşırıq: {problem}\nŞagirdin həlli:\n{numbered}"


def target_json(rec: dict) -> str:
    """Modelin öyrənməli olduğu cavab (assistant mesajı)."""
    out = {
        "wrong_step": rec.get("wrong_step"),
        "error_type": rec.get("error_type"),
        "explanation": rec.get("explanation", ""),
    }
    return json.dumps(out, ensure_ascii=False)


def build_messages(rec: dict, with_answer: bool = True, short: bool = True) -> list[dict]:
    """short=True: təlim və adapter üçün; short=False: base model üçün (tam təriflərlə)."""
    msgs = [
        {"role": "system", "content": SYSTEM_PROMPT_SHORT if short else SYSTEM_PROMPT},
        {"role": "user", "content": format_user(rec["domain"], rec["problem"], rec["steps"])},
    ]
    if with_answer:
        msgs.append({"role": "assistant", "content": target_json(rec)})
    return msgs
