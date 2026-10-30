"""Çətinlik bölgüsü (2026-10-30, Faza 2).

Müəllim yükləmədə üç faiz seçir (asan/orta/çətin, cəmi 100). Bu modul
iki iş görür:

1. `prompt_note` — LLM-ə hər chunk üçün neçə asan/orta/çətin sual
   istədiyimizi və səviyyələrin nə demək olduğunu deyir.
2. `select_by_mix` — dedup-dan sonra suallar kvota üzrə seçilir. Bir
   səviyyədə sual çatmasa, qonşu səviyyədən tamamlanır: model çox vaxt
   «çətin» sualı az verir, amma müəllim yenə istədiyi SAYDA sual
   almalıdır. Fərq müəllimə suallar ekranında açıq göstərilir.
"""

from __future__ import annotations

from pipeline.models import DIFFICULTY_LEVELS, MCQQuestion

DEFAULT_MIX = (30, 50, 20)

# Səviyyə tükənəndə hansı səviyyədən götürülür. «orta» hər iki tərəfə
# ən yaxındır; uc səviyyələr bir-birinə ən uzaqdır.
_FALLBACK_ORDER = {
    "asan": ("orta", "çətin"),
    "orta": ("asan", "çətin"),
    "çətin": ("orta", "asan"),
}


def validate_mix(mix: tuple[int, int, int]) -> None:
    if len(mix) != 3 or any(not isinstance(p, int) or p < 0 or p > 100 for p in mix):
        raise ValueError("Hər faiz 0-100 arasında tam ədəd olmalıdır")
    if sum(mix) != 100:
        raise ValueError("Faizlərin cəmi 100 olmalıdır")


def quotas(total: int, mix: tuple[int, int, int]) -> dict[str, int]:
    """Ən böyük qalıq üsulu: 10 sual, 30/50/20 -> 3/5/2; 7 sual, 30/50/20
    -> 2/4/1 (cəm həmişə `total`-dır, yuvarlaqlaşdırma itki vermir)."""
    exact = [total * p / 100 for p in mix]
    counts = [int(x) for x in exact]
    remainders = sorted(range(3), key=lambda i: exact[i] - counts[i], reverse=True)
    for i in remainders[: total - sum(counts)]:
        counts[i] += 1
    return dict(zip(DIFFICULTY_LEVELS, counts))


def prompt_note(per_chunk: int, mix: tuple[int, int, int]) -> str:
    wanted = quotas(per_chunk, mix)
    parts = [f"{count} {level}" for level, count in wanted.items() if count]
    return (
        "Çətinlik bölgüsü: bu suallardan " + ", ".join(parts) + " olsun. "
        "Hər suala `difficulty` sahəsi yaz: \"asan\", \"orta\" və ya \"çətin\".\n"
        "- asan: mətndə birbaşa yazılan fakt, tərif, tarix, rəqəm; səhv variantlar "
        "açıq-aşkar fərqlidir.\n"
        "- orta: anlama və tətbiq — qaydanı konkret hala tətbiq etmək; səhv variantlar "
        "inandırıcıdır, bir əlamətlə fərqlənir.\n"
        "- çətin: təhlil — iki müddəanı müqayisə, istisna, nəticə çıxarma; səhv "
        "variantlar düzgün cavaba çox yaxındır.\n\n"
    )


def select_by_mix(
    questions: list[MCQQuestion], total: int, mix: tuple[int, int, int]
) -> list[MCQQuestion]:
    """Kvota üzrə seçim, sual sırası saxlanılır. Səviyyəsiz sual «orta»
    sayılır.

    İki mərhələ: əvvəlcə hər səviyyə ÖZ kvotasını öz hovuzundan alır,
    sonra çatışmayan yerlər qonşu səviyyələrin ARTIQ qalanlarından
    doldurulur. Tək mərhələdə «asan» çatmayanda «orta»nın öz kvotası
    üçün lazım olan sualları yeyə bilərdi.
    """
    wanted = quotas(total, mix)
    pools: dict[str, list[int]] = {level: [] for level in DIFFICULTY_LEVELS}
    for index, question in enumerate(questions):
        pools[question.difficulty or "orta"].append(index)

    chosen: set[int] = set()
    for level in DIFFICULTY_LEVELS:
        chosen.update(pools[level][: wanted[level]])

    for level in DIFFICULTY_LEVELS:
        shortfall = wanted[level] - min(wanted[level], len(pools[level]))
        for other in _FALLBACK_ORDER[level]:
            if shortfall <= 0:
                break
            spare = [i for i in pools[other] if i not in chosen][:shortfall]
            chosen.update(spare)
            shortfall -= len(spare)
    return [questions[i] for i in sorted(chosen)]


def breakdown(rows) -> list[dict]:
    """Hesabat üçün səviyyə üzrə nəticə (plan addımı 5): AI-nın «çətin»
    dediyi sualın real çətin olub-olmadığını tələbələrin cavabları göstərir.

    `rows` — hər sual üçün `difficulty`, `correct_count`, `total_answers`.
    Səviyyəsiz (köhnə) suallar `None` sətrində ayrıca sayılır, heç bir
    səviyyəyə qatılmır — yoxsa «orta» nəticəsi köhnə suallarla qarışar.
    Sualı olmayan səviyyə qaytarılmır."""
    order = [*DIFFICULTY_LEVELS, None]
    stats = {level: {"level": level, "question_count": 0, "correct_count": 0, "total_answers": 0}
             for level in order}
    for row in rows:
        level = row.get("difficulty")
        stat = stats[level if level in DIFFICULTY_LEVELS else None]
        stat["question_count"] += 1
        stat["correct_count"] += row.get("correct_count", 0)
        stat["total_answers"] += row.get("total_answers", 0)
    return [stats[level] for level in order if stats[level]["question_count"]]
