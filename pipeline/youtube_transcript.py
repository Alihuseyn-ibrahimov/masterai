"""YouTube linkindən altyazı mətni (Faza 1 «Müəllim AI asistenti», PR 4).

Video ENDİRİLMİR — YouTube-un öz altyazı (transcript) məlumatı oxunur.
Avtomatik yaradılmış altyazı da qəbul edilir (əl ilə yazılmış altyazı
yoxdursa). Altyazı tamamilə bağlıdırsa və ya video tapılmadısa, aydın
Azərbaycanca xəta veririk — material emalı pipeline-ı bunu "uğursuz"
kimi göstərəcək (mövcud `_notify_admin_webhook` bildirişi işə düşür).
"""

from __future__ import annotations

import re

_ID_PATTERNS = (
    re.compile(r"(?:youtube\.com/watch\?v=|youtube\.com/shorts/|youtube\.com/embed/)([A-Za-z0-9_-]{11})"),
    re.compile(r"youtu\.be/([A-Za-z0-9_-]{11})"),
)

# Altyazı dillərinin cəhd sırası: Azərbaycan, sonra ingilis (əksər dərs
# materialı ingiliscə altyazı ilə yüklənir), sonra rus (bölgədə geniş yayılıb).
DEFAULT_LANGUAGES = ("az", "en", "ru")


class YoutubeTranscriptError(RuntimeError):
    """Video ID çıxarıla bilmədi, ya da altyazı tapılmadı/boşdur."""


def extract_video_id(url: str) -> str:
    for pattern in _ID_PATTERNS:
        match = pattern.search(url or "")
        if match:
            return match.group(1)
    raise YoutubeTranscriptError("YouTube linki tanınmadı")


def fetch_transcript(url: str, *, languages: tuple[str, ...] = DEFAULT_LANGUAGES) -> str:
    """Verilən YouTube linkinin altyazı mətnini qaytarır.

    `client` parametri yoxdur qəsdən — çağıran test/server tərəfdə bu
    funksiyanın özünü (`get_youtube_transcriber` asılılığı ilə) fake
    funksiya ilə əvəz edir, `youtube_transcript_api`-nin daxili obyektini
    deyil (mövcud `get_transcriber`/`generate_quiz` naxışı ilə eynidir)."""
    video_id = extract_video_id(url)
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        fetched = YouTubeTranscriptApi().fetch(video_id, languages=list(languages))
    except YoutubeTranscriptError:
        raise
    except Exception as exc:  # noqa: BLE001 - kitabxananın xəta iyerarxiyası genişdir
        raise YoutubeTranscriptError(f"Bu videoda altyazı tapılmadı: {exc}") from exc

    text = " ".join(snippet.text for snippet in fetched).strip()
    if not text:
        raise YoutubeTranscriptError("Altyazı boşdur")
    return text
