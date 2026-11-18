"""Səhv növlərinin vahid mənbəyi (single source of truth).

Səhv Detektivi reposundan (`sehv/taxonomy.py`, v3) DƏYİŞMƏDƏN köçürülüb: adapter bu
kodlarla öyrədilib, kod adını dəyişmək modelin cavabını tanınmaz edər.

Bütün digər fayllar (generator, prompt, validator, metrika, UI) səhv növlərini
buradan götürür. Yeni növ əlavə edəndə yalnız bu faylı dəyişirsən.
"""
from dataclasses import dataclass

DOMAINS = {
    "riyaziyyat": "Riyaziyyat (5–8-ci sinif: kəsrlər, faizlər, tənliklər)",
    "mentiq": "Məntiq testləri (ardıcıllıq, sillogizm, şərt, sıralama, sayma)",
}


@dataclass(frozen=True)
class ErrorType:
    code: str          # modelin qaytardığı qısa kod
    name: str          # UI-də görünən ad
    domain: str        # "riyaziyyat" | "mentiq"
    definition: str    # bir cümləlik tərif (prompta da gedir)
    example: str       # tipik yanlış addım


ERROR_TYPES: list[ErrorType] = [
    # ---------------- RİYAZİYYAT ----------------
    ErrorType("mexrecleri_toplama", "Məxrəcləri toplamaq", "riyaziyyat",
              "Kəsrləri toplayanda/çıxanda surətləri surətlə, məxrəcləri məxrəclə toplayır.",
              "1/2 + 1/3 = 2/5"),
    ErrorType("isare_sehvi", "İşarə səhvi", "riyaziyyat",
              "Mənfi ədədlərlə əməldə və ya mötərizə açanda işarəni səhv yazır.",
              "-3 - 5 = 2"),
    ErrorType("emel_ardicilligi", "Əməliyyat ardıcıllığı", "riyaziyyat",
              "Vurma/bölməni toplamadan əvvəl etmir, soldan sağa sadəcə ardıcıl hesablayır.",
              "2 + 3 · 4 = 20"),
    ErrorType("faiz_bazasi", "Faizi səhv bazadan hesablamaq", "riyaziyyat",
              "Faizi düzgün olmayan ədəddən götürür (məs. ikinci dəyişikliyi ilkin qiymətdən hesablayır).",
              "200 +10% → 220, sonra −10%: 220 − 20 = 200"),
    ErrorType("teref_kecirme", "Tərəf keçirəndə işarəni saxlamaq", "riyaziyyat",
              "Tənlikdə həddi bərabərliyin o biri tərəfinə keçirəndə işarəsini dəyişmir.",
              "3x + 5 = 20 → 3x = 20 + 5"),
    ErrorType("hesab_sehvi", "Hesablama səhvi", "riyaziyyat",
              "Metod düzgündür, amma sadə hesablamada (vurma, toplama, bölmə) səhv edir.",
              "7 · 8 = 54"),
    ErrorType("ixtisar_sehvi", "Səhv ixtisar", "riyaziyyat",
              "Kəsri ixtisar edəndə surəti və məxrəci eyni ədədə bölmür və ya cəmin bir həddini ixtisar edir.",
              "(x + 6)/3 = x + 2"),
    ErrorType("paylama_sehvi", "Mötərizəni açma (paylama) səhvi", "riyaziyyat",
              "Ədədi mötərizənin yalnız birinci həddinə vurur.",
              "3(x + 2) = 3x + 2"),
    # ---------------- MƏNTİQ ----------------
    ErrorType("qayda_sehvi", "Ardıcıllıq qaydasını səhv tapmaq", "mentiq",
              "Ardıcıllığın qaydasını yalnız bir neçə həddə baxıb səhv müəyyən edir (məs. vurma əvəzinə sabit toplama).",
              "2, 6, 18, 54 → 'hər dəfə +4'"),
    ErrorType("bezi_hamisi", "'Bəzi'ni 'hamısı' kimi qəbul etmək", "mentiq",
              "Sillogizmdə 'bəzi' sözünü 'hamısı' kimi işlədir və ya orta termini paylanmamış halda nəticə çıxarır.",
              "Bəzi B C-dir, bütün A B-dir → deməli bəzi A C-dir"),
    ErrorType("ters_netice", "Tərs nəticə (şərtin tərsinə çevrilməsi)", "mentiq",
              "'Əgər P olarsa, Q olar' və Q doğrudur → P də doğrudur deyir; və ya P yalandır → Q yalandır deyir.",
              "Yağış yağırsa yol yaşdır; yol yaşdır → deməli yağış yağıb"),
    ErrorType("inkar_sehvi", "İnkarı səhv qurmaq", "mentiq",
              "'Hamısı'nın inkarını 'heç biri' kimi, 'və'nin inkarını 'heç biri deyil' kimi səhv qurur.",
              "'Bütün şagirdlər gəlib' yalandır → 'heç bir şagird gəlməyib'"),
    ErrorType("sert_unudulub", "Şərti nəzərə almamaq", "mentiq",
              "Sıralama/yerləşdirmə tapşırığında verilmiş şərtlərdən birini nəzərə almır.",
              "'Ali Aydandan solda deyil' şərti unudulur"),
    ErrorType("sayma_sehvi", "Sayma səhvi (bir artıq/əskik)", "mentiq",
              "Aralıqları və ya günləri sayanda bir artıq/əskik sayır (hasar dirəyi səhvi).",
              "10 m hasar, hər 2 m-dən dirək → 5 dirək"),
]

CODES = [e.code for e in ERROR_TYPES]
BY_CODE = {e.code: e for e in ERROR_TYPES}


def codes_for(domain: str) -> list[str]:
    return [e.code for e in ERROR_TYPES if e.domain == domain]


def domain_of(code: str) -> str | None:
    e = BY_CODE.get(code)
    return e.domain if e else None
