"""Səhvin izahı: növə görə HAZIR mətn, modelin öz mətni yalnız ehtiyatdır.

Niyə: canlı saytda (2026-11-19) məntiq testində model addımı və növü (`ters_netice`) düz tapdı,
amma `explanation` sahəsi qarışıq idi (1.5B model Azərbaycan dilində uzun cümlə qurmaqda
zəifdir). Addım və növ isə modelin ən etibarlı çıxışıdır - növü bildikdən sonra izahı
şablondan vermək həm aydın, həm də sabitdir. GPU və yenidən öyrətmə lazım deyil.

Qayda:
1. Növ məlumdursa → `TEMPLATES[kod]` (nə səhvdir + necə yoxlamaq).
2. Növ yoxdur, model səhv addımı göstərib → modelin mətni `clean_model_text`-dən keçirsə o,
   keçməsə ümumi mətn. Model mətni heç vaxt yoxlanmadan ekrana çıxmır.
"""

from __future__ import annotations

import re

from .taxonomy import CODES

# Hər növ üçün: səhvin nə olduğu + düzgün yol (qısa nümunə ilə). Başlıq addımı və növün adını
# onsuz da göstərir, ona görə mətn addım nömrəsini təkrarlamır.
TEMPLATES: dict[str, str] = {
    # ---------------- RİYAZİYYAT ----------------
    "mexrecleri_toplama": (
        "Kəsrləri toplayanda (çıxanda) məxrəclər də toplanıb. Əvvəlcə kəsrləri ortaq məxrəcə gətirin, "
        "sonra yalnız surətləri toplayın: 1/2 + 1/3 = 3/6 + 2/6 = 5/6."),
    "isare_sehvi": (
        "Mənfi ədədlə əməldə və ya mötərizəni açanda işarə səhv yazılıb. Hər həddin işarəsini ayrıca "
        "yoxlayın: mötərizənin qarşısında «−» varsa, içindəki bütün işarələr dəyişir."),
    "emel_ardicilligi": (
        "Əməllər soldan sağa ardıcıl hesablanıb. Vurma və bölmə toplama və çıxmadan əvvəl gəlir: "
        "2 + 3 · 4 = 2 + 12 = 14."),
    "faiz_bazasi": (
        "Faiz səhv ədəddən hesablanıb. Hər yeni faiz dəyişikliyi ondan əvvəlki qiymətə tətbiq olunur: "
        "200 10% artıb 220 olursa, sonrakı 10% endirim 220-dən (22) hesablanır, nəticə 198-dir."),
    "teref_kecirme": (
        "Hədd bərabərliyin o biri tərəfinə keçirilib, amma işarəsi dəyişməyib. Tərəf dəyişən hədd "
        "əks işarə ilə yazılır: 3x + 5 = 20 → 3x = 20 − 5."),
    "hesab_sehvi": (
        "Həll yolu düzgündür, amma bu addımda hesablama səhvi var. Bu addımdakı vurma, bölmə və ya "
        "toplamanı yenidən hesablayın."),
    "ixtisar_sehvi": (
        "Kəsr səhv ixtisar olunub. İxtisar edəndə surət də, məxrəc də BÜTÖVLÜKDƏ eyni ədədə bölünür: "
        "(x + 6)/3 = x/3 + 2, «x + 2» yox."),
    "paylama_sehvi": (
        "Mötərizə açılanda ədəd yalnız birinci həddə vurulub. Mötərizənin qarşısındakı ədəd içindəki "
        "hər həddə vurulur: 3(x + 2) = 3x + 6."),
    # ---------------- MƏNTİQ ----------------
    "qayda_sehvi": (
        "Ardıcıllığın qaydası səhv müəyyən edilib. Tapdığınız qaydanı verilmiş BÜTÜN hədlərdə yoxlayın, "
        "həm fərqə, həm nisbətə baxın: 2, 6, 18, 54-də hər dəfə 3-ə vurulur."),
    "bezi_hamisi": (
        "«Bəzi» sözü «hamısı» kimi işlədilib. «Bəzi B C-dir» yalnız ən azı bir B-nin C olduğunu deyir, "
        "bu B-lərin A ilə üst-üstə düşdüyü məlum deyil, ona görə qəti nəticə çıxmır."),
    "ters_netice": (
        "Şərt tərsinə çevrilib. «Əgər P, onda Q» doğrudursa, Q-nun doğru olması P-ni sübut etmir, "
        "P-nin yalan olması da Q-nun yalan olduğunu göstərmir. Buradan yalnız bu nəticə çıxır: "
        "Q yalandırsa, P də yalandır."),
    "inkar_sehvi": (
        "İnkar səhv qurulub. «Hamısı ...» fikrinin inkarı «heç biri ...» deyil, «ən azı biri ... deyil» "
        "fikridir. «A və B» fikrinin inkarı isə «A deyil və ya B deyil» fikridir."),
    "sert_unudulub": (
        "Verilmiş şərtlərdən biri nəzərə alınmayıb. Şərtləri bir-bir yazın və alınan düzülüşün "
        "hamısını ödədiyini yoxlayın."),
    "sayma_sehvi": (
        "Sayanda bir artıq və ya əskik sayılıb. Aralıqların sayı ilə nöqtələrin (dirəklərin, günlərin) "
        "sayı fərqlidir: 10 m hasarda hər 2 m-dən dirək qoyulsa, 5 aralıq və 6 dirək olur."),
}

assert set(TEMPLATES) == set(CODES), "hər səhv növünün şablonu olmalıdır"

GENERIC_ERROR = ("Bu addım əvvəlki addımlardan düzgün çıxmır, amma səhvin növünü dəqiq deyə bilmədik. "
                 "Addımı əvvəlki addımla müqayisə edin.")
CORRECT_TEXT = "Hər addım əvvəlkindən düzgün çıxır."

_MIN_LEN, _MAX_LEN = 15, 300
_FORBIDDEN = re.compile(r"[{}\[\]<>`|\\]|\bnull\b|\bwrong_step\b|\berror_type\b|\w+_\w+")
_STEP_REF = re.compile(r"(\d+)\s*-?\s*(?:c[iıuü])?\s+addım", re.I)
_AZ_ONLY = set("əƏğĞıİöÖüÜşŞçÇ")
_WORD = re.compile(r"[^\W\d_]+")


def template_for(code: str | None) -> str | None:
    return TEMPLATES.get(code) if code else None


def clean_model_text(text: str | None, wrong_step: int | None) -> str | None:
    """Modelin izahını yalnız oxunaqlıdırsa qaytarır, yoxsa None.

    Rədd səbəbləri: çox qısa/uzun; JSON, kod, `snake_case` qalığı; başqa addım nömrəsi;
    Azərbaycan hərfi olmayan (ingiliscə və ya zibil) mətn; söz təkrarı dövrəsi; hərf azdır.
    """
    if not text:
        return None
    text = re.sub(r"\s+", " ", str(text)).strip()
    if not _MIN_LEN <= len(text) <= _MAX_LEN or _FORBIDDEN.search(text):
        return None
    for m in _STEP_REF.finditer(text):
        if wrong_step is None or int(m.group(1)) != wrong_step:
            return None
    words = [w.lower() for w in _WORD.findall(text)]
    if len(words) < 3 or not any(ch in _AZ_ONLY for ch in text):
        return None
    if sum(len(w) for w in words) < 0.6 * len(text.replace(" ", "")):
        return None  # rəqəm/simvol qarışığı
    if any(words[i] == words[i + 1] == words[i + 2] for i in range(len(words) - 2)):
        return None  # «səhv səhv səhv» kimi dövrə
    if len(words) >= 8 and len(set(words)) / len(words) < 0.5:
        return None
    if text[-1] not in ".!?»":
        text += "."
    return text
