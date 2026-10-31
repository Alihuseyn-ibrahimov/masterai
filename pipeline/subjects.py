"""Fənnə görə sual qaydası (2026-10-31, real sınaqda tapıldı).

Müəllim «Qanunvericilik» seçmişdi, AI isə Konstitusiya dərsindən «2 %
əlavə maddə olsa cəmi neçə olar?» kimi hesab sualı və «158 maddə olduğu
üçün çox mövzunu əhatə edir» kimi məntiq tapmacası düzəltdi. Səbəb:
fənn AI-a HEÇ ötürülmürdü - yalnız bazada saxlanırdı. Çətinlik
qaydasındakı «qaydanı konkret hala tətbiq et» isə modeli hesablamağa
itələyirdi.

Qeyd prompt-da «Material:» blokundan KƏNARDA durur (çətinlik qeydi kimi).
Fənn verilməyəndə boşdur - CLI və köhnə çağırışlar bayt-bayt eyni qalır.
"""

from __future__ import annotations

_NO_INVENTED_MATH = (
    "Materialda olmayan hesablama, faiz, tənlik və ya rəqəm tapmacası UYDURMA; "
    "rəqəm yalnız materialda yazılan fakt kimi soruşula bilər.\n"
)

_NOTES = {
    "qanunvericilik": (
        "Fənn: Qanunvericilik. Suallar hüquqi məzmunu yoxlasın: normanın nə "
        "dediyi, hüquq və vəzifələr, səlahiyyətli orqan, prosedur və müddətlər, "
        "anlayışların tərifi, normanın konkret həyati vəziyyətə tətbiqi. "
        + _NO_INVENTED_MATH
    ),
    "azerbaycan_dili": (
        "Fənn: Azərbaycan dili. Suallar dil qaydalarını, orfoqrafiya, "
        "qrammatika, leksika və mətnin anlaşılmasını yoxlasın. " + _NO_INVENTED_MATH
    ),
    "dunyagorusu": (
        "Fənn: Dünyagörüşü. Suallar tarix, coğrafiya, mədəniyyət və ictimai "
        "həyat faktlarını və onların əlaqəsini yoxlasın. " + _NO_INVENTED_MATH
    ),
    "xarici_dil": (
        "Fənn: Xarici dil. Suallar lüğət, qrammatika və mətnin anlaşılmasını "
        "yoxlasın. " + _NO_INVENTED_MATH
    ),
    "informatika": (
        "Fənn: İnformatika. Suallar materialdakı anlayışları, alqoritmləri və "
        "onların tətbiqini yoxlasın; hesablama yalnız materialın mövzusuna "
        "aiddirsə ola bilər.\n"
    ),
    "mentiq": (
        "Fənn: Məntiq. Suallar məntiqi nəticə, ardıcıllıq və mühakimə "
        "bacarığını yoxlasın, materialdakı məzmuna əsaslansın.\n"
    ),
}


def subject_note(subject: str | None) -> str:
    """Tanınmayan və ya boş fənn - boş qeyd (köhnə davranış)."""
    note = _NOTES.get(subject or "")
    return note + "\n" if note else ""
