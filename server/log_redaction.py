"""Jurnal sətirlərindən sirrlərin silinməsi.

NİYƏ: brauzerin WebSocket API-si custom header dəstəkləmir, ona görə JWT
query param-da göndərilir (`?token=...`). Real VPS jurnalında bu sətir
göründü (2026-09-10):

    WebSocket /ws/live/347489/host?token=eyJhbGciOiJIUzI1NiIs... 403

Jurnal DİSKDƏ qalır və `journalctl` ilə oxunur; oradan götürülmüş token
hesaba tam giriş verir (tokenlərimizin ömrü 90 gündür).

NƏ HƏLL ETMİR: token hələ də URL-dədir. Onu aradan qaldırmaq üçün
qısaömürlü WS «ticket» lazımdır (bax `CLAUDE.md`, «Bilinən risklər») —
ayrıca iş. Burada bağlanan, sirrin DİSKDƏ SAXLANMASIDIR.
"""

from __future__ import annotations

import logging
import re

# `?token=...`, `&ticket=...`, `api_key=...` — dəyər növbəti `&`, boşluq
# və ya sətir sonuna qədər.
_QUERY_SECRET_RE = re.compile(
    r"(?i)\b(token|ticket|api_key|apikey|access_token|secret|password)=[^&\s\"']+"
)
# `Authorization: Bearer <token>` və `X-Admin-Key: <key>`.
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[^\s\"']+")
_ADMIN_KEY_RE = re.compile(r"(?i)\b(X-Admin-Key)\s*:\s*[^\s\"']+")

_MASK = "***"


def redact_secrets(text):
    """Sətirdəki sirr dəyərlərini `***` ilə əvəz edir.

    Sətir olmayan dəyər (None, int, dict...) toxunulmadan qaytarılır —
    filtr jurnal sətrini heç vaxt sındırmamalıdır.
    """
    if not isinstance(text, str):
        return text
    text = _QUERY_SECRET_RE.sub(lambda m: f"{m.group(1)}={_MASK}", text)
    text = _BEARER_RE.sub(f"Bearer {_MASK}", text)
    text = _ADMIN_KEY_RE.sub(lambda m: f"{m.group(1)}: {_MASK}", text)
    return text


class RedactSecretsFilter(logging.Filter):
    """Hər jurnal sətrini yazılmazdan ƏVVƏL təmizləyir.

    HƏM `record.msg`, HƏM `record.args` təmizlənir: uvicorn-un access
    log-u mesajı `args` ilə qurur (`'%s - "%s %s HTTP/%s" %d'`), yəni
    yalnız `msg`-ə baxan filtr «işləyir» görünüb HEÇ NƏ etməzdi.

    Sətri HEÇ VAXT gizlətmir (həmişə `True` qaytarır) — jurnal sətirləri
    itməməlidir, yalnız təmizlənməlidir.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_secrets(record.msg)
        if isinstance(record.args, dict):
            record.args = {key: redact_secrets(value) for key, value in record.args.items()}
        elif isinstance(record.args, tuple):
            record.args = tuple(redact_secrets(value) for value in record.args)
        return True


# Sirr daşıyan sətirləri yazan logger-lər. Bunlar öz handler-lərini
# işlədir və `propagate = False`-dur, yəni root handler-inə HEÇ VAXT
# çatmır - bu, ilk cəhdimin real icrada sınmasının səbəbi oldu (bax
# `install_redaction` sənədi).
_SECRET_CARRYING_LOGGERS = (
    "uvicorn.access", "uvicorn.error", "gunicorn.access", "gunicorn.error",
)


def install_redaction() -> None:
    """Filtri LOGGER-lərə qoşur (handler-lərə yox).

    NİYƏ LOGGER: ilk versiyada filtr yalnız root HANDLER-inə qoşulmuşdu.
    Vahid testlər keçirdi, amma real icrada token jurnalda TAM göründü.
    Mənbədən yoxlandıqda səbəb aydın oldu:

      - `uvicorn.access` üçün `propagate = False` və öz handler-i var,
        yəni sətir root handler-inə heç vaxt çatmır;
      - `UvicornWorker` (production-da gunicorn ilə) həmin logger-in
        `handlers`-ini tamamilə ƏVƏZ EDİR, amma `filters`-ə toxunmur;
      - `dictConfig` da handler-ləri silir, filtrləri saxlayır.

    Ona görə logger-ə qoşulan filtr hər iki icra yolunda (plain uvicorn
    və gunicorn+UvicornWorker) sağ qalır.

    İdempotentdir - iki dəfə çağırılsa filtr təkrarlanmır.
    """
    targets = [logging.getLogger(name) for name in _SECRET_CARRYING_LOGGERS]
    targets.append(logging.getLogger())  # öz tətbiq sətirlərimiz üçün
    for target in targets:
        if not any(isinstance(f, RedactSecretsFilter) for f in target.filters):
            target.addFilter(RedactSecretsFilter())
