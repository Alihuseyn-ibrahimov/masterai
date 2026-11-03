"""Material yükləmə: video fayl, YouTube linki, düz mətn yapışdırma
(Faza 1 «Müəllim AI asistenti», PR 4). Hər üçü eyni yerə gəlir: nəticə
mətn `kind="text"` kimi mövcud sual pipeline-ına verilir."""

import os

import pytest
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion, PipelineResult
from pipeline.transcribe import TranscriptionError
from pipeline.youtube_transcript import YoutubeTranscriptError
from server.app import (
    app,
    get_material_generator,
    get_question_set_store,
    get_token_secret,
    get_transcriber,
    get_upload_dir,
    get_user_store,
    get_youtube_transcriber,
)
from server.auth import create_token
from server.question_set_store import QuestionSetStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"
_LONG_TEXT = "Bu materialın mətnidir. " * 20  # > 300 simvol


def _fake_generator(source, question_count=10, **_options):
    assert source.kind == "text"
    return PipelineResult(
        questions=[
            MCQQuestion(question="?", options=list("abcde"), correct_index=0, explanation="i")
            for _ in range(3)
        ],
        source=source, chunks_processed=1, chunks_failed=0, requested_question_count=question_count,
    )


@pytest.fixture
def env(tmp_path):
    users = UserStore(":memory:")
    question_sets = QuestionSetStore(":memory:")
    seen = {}

    def fake_transcriber(path):
        seen["video_path"] = path
        seen["video_existed_during_call"] = os.path.exists(path)
        return seen.get("transcript_text", _LONG_TEXT)

    def fake_youtube_transcriber(url):
        seen["youtube_url"] = url
        return seen.get("transcript_text", _LONG_TEXT)

    for dep, value in {
        get_user_store: users, get_question_set_store: question_sets, get_token_secret: _SECRET,
        get_material_generator: _fake_generator, get_upload_dir: str(tmp_path),
        get_transcriber: fake_transcriber, get_youtube_transcriber: fake_youtube_transcriber,
    }.items():
        app.dependency_overrides[dep] = (lambda v: lambda: v)(value)

    client = TestClient(app)
    teacher = users.create("teacher@masternr1.az", "hash", "Müəllim")
    users.set_teacher(teacher["id"], True)
    teacher = users.get_by_id(teacher["id"])
    yield {"client": client, "question_sets": question_sets, "teacher": teacher, "seen": seen,
           "tmp_path": tmp_path}
    app.dependency_overrides.clear()


def _auth(user):
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


class TestVideoMaterial:
    def test_video_is_transcribed_and_stored_as_text(self, env):
        r = env["client"].post(
            "/live/question-sets",
            data={"subject": "mentiq", "title": "Video dərs", "kind": "video"},
            files={"file": ("clip.mp4", b"fake-video-bytes", "video/mp4")},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 202
        qs = env["question_sets"].get(r.json()["id"])
        assert qs["material_kind"] == "text"
        # Transkripsiya zamanı video faylı hələ diskdə idi, sonra silinib -
        # yalnız mətn faylı qalıb.
        assert env["seen"]["video_existed_during_call"] is True
        assert not os.path.exists(env["seen"]["video_path"])
        with open(qs["material_location"], encoding="utf-8") as f:
            assert f.read() == _LONG_TEXT

    def test_video_without_file_is_400(self, env):
        r = env["client"].post(
            "/live/question-sets",
            data={"subject": "mentiq", "title": "A", "kind": "video"},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 400

    def test_oversized_video_is_413(self, env, monkeypatch):
        monkeypatch.setattr("server.app.MAX_VIDEO_UPLOAD_BYTES", 10)
        r = env["client"].post(
            "/live/question-sets",
            data={"subject": "mentiq", "title": "A", "kind": "video"},
            files={"file": ("clip.mp4", b"x" * 1000, "video/mp4")},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 413

    def test_transcription_failure_is_400_and_cleans_up_file(self, env):
        def failing(path):
            raise TranscriptionError("GROQ_API_KEY yoxdur")
        app.dependency_overrides[get_transcriber] = lambda: failing
        r = env["client"].post(
            "/live/question-sets",
            data={"subject": "mentiq", "title": "A", "kind": "video"},
            files={"file": ("clip.mp4", b"x" * 100, "video/mp4")},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 400
        assert "GROQ_API_KEY" in r.json()["detail"]

    def test_too_short_transcript_is_400(self, env):
        env["seen"]["transcript_text"] = "Qısa."
        r = env["client"].post(
            "/live/question-sets",
            data={"subject": "mentiq", "title": "A", "kind": "video"},
            files={"file": ("clip.mp4", b"x" * 100, "video/mp4")},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 400


class TestYoutubeMaterial:
    def test_youtube_transcript_is_fetched_and_stored_as_text(self, env):
        r = env["client"].post(
            "/live/question-sets",
            data={
                "subject": "mentiq", "title": "YouTube dərs", "kind": "youtube",
                "location": "https://youtu.be/dQw4w9WgXcQ",
            },
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 202
        assert env["seen"]["youtube_url"] == "https://youtu.be/dQw4w9WgXcQ"
        qs = env["question_sets"].get(r.json()["id"])
        assert qs["material_kind"] == "text"

    def test_youtube_without_location_is_400(self, env):
        r = env["client"].post(
            "/live/question-sets",
            data={"subject": "mentiq", "title": "A", "kind": "youtube"},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 400

    def test_no_captions_is_400(self, env):
        def failing(url):
            raise YoutubeTranscriptError("Bu videoda altyazı tapılmadı")
        app.dependency_overrides[get_youtube_transcriber] = lambda: failing
        r = env["client"].post(
            "/live/question-sets",
            data={"subject": "mentiq", "title": "A", "kind": "youtube", "location": "https://youtu.be/x"},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 400
        assert "altyazı" in r.json()["detail"]


class TestTextMaterial:
    def test_pasted_text_is_stored(self, env):
        r = env["client"].post(
            "/live/question-sets",
            data={"subject": "mentiq", "title": "Mətn materialı", "kind": "text", "text_content": _LONG_TEXT},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 202
        qs = env["question_sets"].get(r.json()["id"])
        assert qs["material_kind"] == "text"
        with open(qs["material_location"], encoding="utf-8") as f:
            assert f.read() == _LONG_TEXT.strip()

    def test_too_short_pasted_text_is_400(self, env):
        r = env["client"].post(
            "/live/question-sets",
            data={"subject": "mentiq", "title": "A", "kind": "text", "text_content": "Çox qısa."},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 400

    def test_missing_text_content_is_400(self, env):
        r = env["client"].post(
            "/live/question-sets",
            data={"subject": "mentiq", "title": "A", "kind": "text"},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 400
