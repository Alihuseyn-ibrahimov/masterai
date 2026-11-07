"""Dərs videosunun yazılması (LiveKit Egress, Faza 4 PR 2, 2026-11-07)."""

import base64
import hashlib
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from server.app import (
    app,
    get_chat_store,
    get_egress_client_factory,
    get_egress_config,
    get_lesson_store,
    get_livekit_config,
    get_token_secret,
    get_user_store,
)
from server.auth import create_token
from server.chat_store import ChatStore
from server.egress import EgressConfig
from server.lesson_store import LessonStore
from server.user_store import UserStore
from server.video import LiveKitConfig

_SECRET = "test-secret-key-32-chars-minimum!!"
_LK = LiveKitConfig(url="wss://demo.livekit.cloud", api_key="APIkey", api_secret="s" * 40)
_EGRESS = EgressConfig(bucket="b", region="fra1", access_key="ak", secret="sk", endpoint="https://x", force_path_style=True)
_LESSON = {"title": "Konstitusiya: giriş", "description": "1-ci fəsil",
           "starts_at": "2026-11-03T10:00:00+04:00", "duration_min": 90, "mode": "online"}


class _FakeEgressService:
    def __init__(self, egress_id="EG_1", file_results=None):
        self.egress_id = egress_id
        self.started_with = None
        self.stopped_id = None

    async def start_room_composite_egress(self, req):
        self.started_with = req

        class _Info:
            egress_id = self.egress_id
        return _Info()

    async def stop_egress(self, req):
        self.stopped_id = req.egress_id

        class _Info:
            egress_id = req.egress_id
        return _Info()


class _FakeEgressClient:
    def __init__(self, egress_id="EG_1"):
        self.egress = _FakeEgressService(egress_id)
        self.closed = False

    async def aclose(self):
        self.closed = True


@pytest.fixture
def env():
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    lessons = LessonStore(":memory:")
    fake_client = _FakeEgressClient()
    for dep, value in {
        get_user_store: users, get_chat_store: chats, get_lesson_store: lessons,
        get_token_secret: _SECRET, get_livekit_config: _LK, get_egress_config: _EGRESS,
    }.items():
        app.dependency_overrides[dep] = (lambda v: (lambda: v))(value)
    app.dependency_overrides[get_egress_client_factory] = lambda: (lambda livekit: fake_client)

    course = users.courses.create("Kurs", "exam_prep", trial_days=30, seat_limit=30)

    def person(email, name, *, teacher=False):
        row = users.create(email, "h", name, course_id=course["id"])
        if teacher:
            users.set_teacher(row["id"], True)
        return users.get_by_id(row["id"])

    teacher = person("t@x.az", "Müəllim", teacher=True)
    ali = person("a@x.az", "Əli")
    chat = chats.create(kind="group", created_by=teacher["id"], name="Sinif 1", course_id=course["id"])
    for member in (teacher, ali):
        chats.add_member(chat["id"], member["id"])

    yield {"client": TestClient(app), "lessons": lessons, "teacher": teacher, "ali": ali,
           "chat": chat, "fake_client": fake_client}
    app.dependency_overrides.clear()


def _auth(user):
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


def _create(env, **overrides):
    r = env["client"].post(f"/chats/{env['chat']['id']}/lessons", json={**_LESSON, **overrides},
                           headers=_auth(env["teacher"]))
    assert r.status_code == 201, r.text
    return r.json()


def _live(env, **overrides):
    lesson = _create(env, **overrides)
    env["client"].post(f"/live/lessons/{lesson['id']}/start", headers=_auth(env["teacher"]))
    return lesson


def _webhook_token(body: str) -> str:
    body_hash = base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
    return jwt.encode(
        {"iss": _LK.api_key, "exp": int(time.time()) + 60, "sha256": body_hash},
        _LK.api_secret, algorithm="HS256",
    )


def test_start_without_egress_config_is_503(env):
    app.dependency_overrides[get_egress_config] = lambda: None
    lesson = _live(env)
    r = env["client"].post(f"/live/lessons/{lesson['id']}/recording/start", headers=_auth(env["teacher"]))
    assert r.status_code == 503


def test_start_requires_online_mode(env):
    lesson = _create(env, mode="offline")
    env["client"].post(f"/live/lessons/{lesson['id']}/start", headers=_auth(env["teacher"]))
    r = env["client"].post(f"/live/lessons/{lesson['id']}/recording/start", headers=_auth(env["teacher"]))
    assert r.status_code == 409


def test_start_requires_live_status(env):
    lesson = _create(env)
    r = env["client"].post(f"/live/lessons/{lesson['id']}/recording/start", headers=_auth(env["teacher"]))
    assert r.status_code == 409


def test_student_cannot_start_recording(env):
    lesson = _live(env)
    r = env["client"].post(f"/live/lessons/{lesson['id']}/recording/start", headers=_auth(env["ali"]))
    assert r.status_code == 403


def test_start_sets_recording_status_and_cannot_double_start(env):
    lesson = _live(env)
    r = env["client"].post(f"/live/lessons/{lesson['id']}/recording/start", headers=_auth(env["teacher"]))
    assert r.status_code == 200, r.text
    assert r.json()["recording_status"] == "recording"
    assert env["fake_client"].egress.started_with is not None

    r2 = env["client"].post(f"/live/lessons/{lesson['id']}/recording/start", headers=_auth(env["teacher"]))
    assert r2.status_code == 409


def test_stop_without_recording_is_409(env):
    lesson = _live(env)
    r = env["client"].post(f"/live/lessons/{lesson['id']}/recording/stop", headers=_auth(env["teacher"]))
    assert r.status_code == 409


def test_stop_sets_processing_status(env):
    lesson = _live(env)
    env["client"].post(f"/live/lessons/{lesson['id']}/recording/start", headers=_auth(env["teacher"]))
    r = env["client"].post(f"/live/lessons/{lesson['id']}/recording/stop", headers=_auth(env["teacher"]))
    assert r.status_code == 200, r.text
    assert r.json()["recording_status"] == "processing"
    assert env["fake_client"].egress.stopped_id == "EG_1"


def test_webhook_rejects_bad_signature(env):
    lesson = _live(env)
    env["client"].post(f"/live/lessons/{lesson['id']}/recording/start", headers=_auth(env["teacher"]))
    body = '{"event": "egress_ended", "egressInfo": {"egressId": "EG_1"}}'
    r = env["client"].post("/live/egress/webhook", content=body,
                           headers={"Authorization": "not-a-valid-token"})
    assert r.status_code == 401


def test_webhook_marks_ready_with_file_url(env):
    lesson = _live(env)
    env["client"].post(f"/live/lessons/{lesson['id']}/recording/start", headers=_auth(env["teacher"]))
    body = (
        '{"event": "egress_ended", "egressInfo": {"egressId": "EG_1", '
        '"fileResults": [{"location": "https://b.fra1.digitaloceanspaces.com/lessons/1/x.mp4"}]}}'
    )
    r = env["client"].post("/live/egress/webhook", content=body,
                           headers={"Authorization": _webhook_token(body)})
    assert r.status_code == 200, r.text
    updated = env["lessons"].get(lesson["id"])
    assert updated["recording_status"] == "ready"
    assert updated["recording_url"] == "https://b.fra1.digitaloceanspaces.com/lessons/1/x.mp4"


def test_webhook_marks_failed_without_file_results(env):
    lesson = _live(env)
    env["client"].post(f"/live/lessons/{lesson['id']}/recording/start", headers=_auth(env["teacher"]))
    body = '{"event": "egress_ended", "egressInfo": {"egressId": "EG_1"}}'
    r = env["client"].post("/live/egress/webhook", content=body,
                           headers={"Authorization": _webhook_token(body)})
    assert r.status_code == 200, r.text
    assert env["lessons"].get(lesson["id"])["recording_status"] == "failed"


def test_webhook_ignores_unrelated_egress_id(env):
    _live(env)
    body = '{"event": "egress_ended", "egressInfo": {"egressId": "EG_OTHER"}}'
    r = env["client"].post("/live/egress/webhook", content=body,
                           headers={"Authorization": _webhook_token(body)})
    assert r.status_code == 200


def test_webhook_ignores_other_event_types(env):
    lesson = _live(env)
    env["client"].post(f"/live/lessons/{lesson['id']}/recording/start", headers=_auth(env["teacher"]))
    body = '{"event": "egress_started", "egressInfo": {"egressId": "EG_1"}}'
    r = env["client"].post("/live/egress/webhook", content=body,
                           headers={"Authorization": _webhook_token(body)})
    assert r.status_code == 200
    assert env["lessons"].get(lesson["id"])["recording_status"] == "recording"


def test_webhook_without_livekit_config_is_503(env):
    app.dependency_overrides[get_livekit_config] = lambda: None
    r = env["client"].post("/live/egress/webhook", content="{}", headers={"Authorization": "x"})
    assert r.status_code == 503
