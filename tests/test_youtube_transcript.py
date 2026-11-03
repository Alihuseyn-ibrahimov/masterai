"""`pipeline.youtube_transcript` — video ID çıxarılması + altyazı xətaları.

`fetch_transcript`-in uğurlu yolu real `youtube_transcript_api`-yə şəbəkə
sorğusu tələb edir — onu server qatında `get_youtube_transcriber`
asılılığı ilə fake funksiya əvəz edir (bax `test_endpoints` faylı).
Burada YALNIZ bu modulun öz məntiqini (ID çıxarma, xəta çevirmə) sınayırıq.
"""

import pytest

from pipeline.youtube_transcript import YoutubeTranscriptError, extract_video_id, fetch_transcript


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30s",
    "https://youtu.be/dQw4w9WgXcQ",
    "https://www.youtube.com/shorts/dQw4w9WgXcQ",
    "https://www.youtube.com/embed/dQw4w9WgXcQ",
])
def test_extract_video_id_accepts_common_url_shapes(url):
    assert extract_video_id(url) == "dQw4w9WgXcQ"


def test_extract_video_id_rejects_non_youtube_url():
    with pytest.raises(YoutubeTranscriptError):
        extract_video_id("https://example.com/video")


def test_extract_video_id_rejects_empty_string():
    with pytest.raises(YoutubeTranscriptError):
        extract_video_id("")


def test_fetch_transcript_wraps_library_failure(monkeypatch):
    class _FakeApi:
        def fetch(self, video_id, languages):
            raise RuntimeError("altyazı bağlıdır")

    monkeypatch.setattr(
        "youtube_transcript_api.YouTubeTranscriptApi", lambda: _FakeApi(),
    )
    with pytest.raises(YoutubeTranscriptError, match="altyazı tapılmadı"):
        fetch_transcript("https://youtu.be/dQw4w9WgXcQ")


def test_fetch_transcript_rejects_blank_result(monkeypatch):
    class _FakeApi:
        def fetch(self, video_id, languages):
            return []

    monkeypatch.setattr(
        "youtube_transcript_api.YouTubeTranscriptApi", lambda: _FakeApi(),
    )
    with pytest.raises(YoutubeTranscriptError, match="boşdur"):
        fetch_transcript("https://youtu.be/dQw4w9WgXcQ")


def test_fetch_transcript_joins_snippets(monkeypatch):
    class _Snippet:
        def __init__(self, text):
            self.text = text

    class _FakeApi:
        def fetch(self, video_id, languages):
            assert video_id == "dQw4w9WgXcQ"
            return [_Snippet("Salam"), _Snippet("dünya.")]

    monkeypatch.setattr(
        "youtube_transcript_api.YouTubeTranscriptApi", lambda: _FakeApi(),
    )
    assert fetch_transcript("https://youtu.be/dQw4w9WgXcQ") == "Salam dünya."
