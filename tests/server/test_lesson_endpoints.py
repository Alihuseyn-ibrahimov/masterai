"""Dərs cədvəli və davamiyyət (MasterAI Classroom, gün 1, 2026-10-31)."""

import jwt
import pytest
from fastapi.testclient import TestClient

from server.app import (
    app,
    get_chat_store,
    get_lesson_store,
    get_livekit_config,
    get_token_secret,
    get_user_store,
)
from server.auth import create_token
from server.chat_store import ChatStore
from server.lesson_store import LessonStore
from server.user_store import UserStore
from server.video import LiveKitConfig

_SECRET = "test-secret-key-32-chars-minimum!!"
_LESSON = {"title": "Konstitusiya: giriş", "description": "1-ci fəsil",
           "starts_at": "2026-11-03T10:00:00+04:00", "duration_min": 90, "mode": "online"}


@pytest.fixture
def env():
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    lessons = LessonStore(":memory:")
    for dep, value in {get_user_store: users, get_chat_store: chats,
                       get_lesson_store: lessons, get_token_secret: _SECRET}.items():
        app.dependency_overrides[dep] = (lambda v: lambda: v)(value)

    course = users.courses.create("Kurs", "exam_prep", trial_days=30, seat_limit=30)

    def person(email, name, *, teacher=False):
        row = users.create(email, "h", name, course_id=course["id"])
        if teacher:
            users.set_teacher(row["id"], True)
        return users.get_by_id(row["id"])

    teacher = person("t@x.az", "Müəllim", teacher=True)
    ali = person("a@x.az", "Əli")
    vali = person("v@x.az", "Vəli")
    outsider = person("o@x.az", "Kənar")
    chat = chats.create(kind="group", created_by=teacher["id"], name="Sinif 1", course_id=course["id"])
    for member in (teacher, ali, vali):
        chats.add_member(chat["id"], member["id"])

    yield {"client": TestClient(app), "lessons": lessons, "teacher": teacher, "ali": ali,
           "vali": vali, "outsider": outsider, "chat": chat}
    app.dependency_overrides.clear()


def _auth(user):
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


def _create(env, **overrides):
    r = env["client"].post(f"/chats/{env['chat']['id']}/lessons", json={**_LESSON, **overrides},
                           headers=_auth(env["teacher"]))
    assert r.status_code == 201, r.text
    return r.json()


def test_teacher_schedules_lesson_and_time_is_stored_in_utc(env):
    lesson = _create(env)
    assert lesson["status"] == "scheduled"
    assert lesson["chat_name"] == "Sinif 1"
    # Bakı 10:00 = UTC 06:00: brauzerlər fərqli qurşaqda olsa da eyni an.
    assert lesson["starts_at"].startswith("2026-11-03T06:00:00")


def test_student_cannot_schedule(env):
    r = env["client"].post(f"/chats/{env['chat']['id']}/lessons", json=_LESSON, headers=_auth(env["ali"]))
    assert r.status_code == 403


def test_lessons_are_listed_by_time_for_members_only(env):
    later = _create(env, title="İkinci", starts_at="2026-11-05T10:00:00+04:00")
    first = _create(env, title="Birinci", starts_at="2026-11-04T10:00:00+04:00")
    r = env["client"].get("/me/lessons", headers=_auth(env["ali"]))
    assert [x["id"] for x in r.json()] == [first["id"], later["id"]]
    assert env["client"].get("/me/lessons", headers=_auth(env["outsider"])).json() == []
    r = env["client"].get(f"/chats/{env['chat']['id']}/lessons", headers=_auth(env["outsider"]))
    assert r.status_code == 403
    r = env["client"].get(f"/me/lessons/{first['id']}", headers=_auth(env["outsider"]))
    assert r.status_code == 404


def test_attendance_only_while_live_and_only_once(env):
    lesson = _create(env)
    url = f"/me/lessons/{lesson['id']}/attend"
    assert env["client"].post(url, headers=_auth(env["ali"])).status_code == 409

    env["client"].post(f"/live/lessons/{lesson['id']}/start", headers=_auth(env["teacher"]))
    for _ in range(3):  # səhifəni yeniləyən tələbə təkrar sətir yaratmır
        assert env["client"].post(url, headers=_auth(env["ali"])).json()["attended"] is True
    assert len(env["lessons"].list_attendance(lesson["id"])) == 1

    r = env["client"].get(f"/live/lessons/{lesson['id']}/attendance", headers=_auth(env["teacher"]))
    rows = r.json()
    assert [(x["display_name"], x["present"]) for x in rows] == [("Əli", True), ("Vəli", False)]
    assert rows[0]["method"] == "online"

    env["client"].post(f"/live/lessons/{lesson['id']}/end", headers=_auth(env["teacher"]))
    assert env["client"].post(url, headers=_auth(env["vali"])).status_code == 409


def test_offline_lesson_needs_qr_code(env):
    # Gün 6: sinif dərsində kodsuz «gəldim» evdən də basıla bilərdi.
    lesson = _create(env, mode="offline")
    env["client"].post(f"/live/lessons/{lesson['id']}/start", headers=_auth(env["teacher"]))
    url = f"/me/lessons/{lesson['id']}/attend"
    assert env["client"].post(url, headers=_auth(env["vali"])).status_code == 403
    assert env["client"].post(url, json={"code": "YANLIS"}, headers=_auth(env["vali"])).status_code == 403
    code = env["client"].get(f"/live/lessons/{lesson['id']}/qr", headers=_auth(env["teacher"])).json()["code"]
    assert env["client"].post(url, json={"code": code.lower()}, headers=_auth(env["vali"])).status_code == 200
    assert env["lessons"].list_attendance(lesson["id"])[0]["method"] == "qr"


def test_restart_keeps_first_start_time(env):
    lesson = _create(env)
    first = env["client"].post(f"/live/lessons/{lesson['id']}/start", headers=_auth(env["teacher"])).json()
    env["client"].post(f"/live/lessons/{lesson['id']}/end", headers=_auth(env["teacher"]))
    again = env["client"].post(f"/live/lessons/{lesson['id']}/start", headers=_auth(env["teacher"])).json()
    assert again["started_at"] == first["started_at"]
    assert again["ended_at"] is None


def test_teacher_edits_notes_and_time(env):
    lesson = _create(env)
    r = env["client"].patch(f"/live/lessons/{lesson['id']}",
                            json={"notes": "Bu gün: 1-ci fəsil", "starts_at": "2026-11-03T12:00:00Z"},
                            headers=_auth(env["teacher"]))
    assert r.json()["notes"] == "Bu gün: 1-ci fəsil"
    assert r.json()["starts_at"].startswith("2026-11-03T12:00:00")
    assert r.json()["title"] == _LESSON["title"]
    r = env["client"].patch(f"/live/lessons/{lesson['id']}", json={"notes": "x"}, headers=_auth(env["ali"]))
    assert r.status_code == 403


def test_started_lesson_cannot_be_deleted(env):
    lesson = _create(env)
    env["client"].post(f"/live/lessons/{lesson['id']}/start", headers=_auth(env["teacher"]))
    r = env["client"].delete(f"/live/lessons/{lesson['id']}", headers=_auth(env["teacher"]))
    assert r.status_code == 409
    fresh = _create(env)
    assert env["client"].delete(f"/live/lessons/{fresh['id']}", headers=_auth(env["teacher"])).status_code == 204
    assert env["lessons"].get(fresh["id"]) is None


def test_invalid_duration_rejected(env):
    r = env["client"].post(f"/chats/{env['chat']['id']}/lessons", json={**_LESSON, "duration_min": 5},
                           headers=_auth(env["teacher"]))
    assert r.status_code == 422


# ---- Gün 2: video otağına giriş (LiveKit) --------------------------------

_LK = LiveKitConfig(url="wss://demo.livekit.cloud", api_key="APIkey", api_secret="s" * 40)


def _video(env, user, lesson_id):
    return env["client"].post(f"/me/lessons/{lesson_id}/video", headers=_auth(user))


@pytest.fixture
def lk():
    app.dependency_overrides[get_livekit_config] = lambda: _LK
    yield
    app.dependency_overrides.pop(get_livekit_config, None)


def test_video_token_for_student_marks_attendance(env, lk):
    lesson = _create(env)
    env["client"].post(f"/live/lessons/{lesson['id']}/start", headers=_auth(env["teacher"]))
    r = _video(env, env["ali"], lesson["id"])
    assert r.status_code == 200, r.text
    body = r.json()
    claims = jwt.decode(body["token"], _LK.api_secret, algorithms=["HS256"])
    assert claims["iss"] == "APIkey" and claims["sub"] == f"user-{env['ali']['id']}"
    assert claims["name"] == "Əli"
    assert claims["video"]["room"] == body["room"] == f"masterai-lesson-{lesson['id']}"
    assert claims["video"]["roomJoin"] is True and claims["video"]["roomAdmin"] is False
    assert body["is_host"] is False and body["url"] == _LK.url
    assert [a["user_id"] for a in env["lessons"].list_attendance(lesson["id"])] == [env["ali"]["id"]]


def test_teacher_is_room_admin_and_not_counted_as_present(env, lk):
    lesson = _create(env)
    env["client"].post(f"/live/lessons/{lesson['id']}/start", headers=_auth(env["teacher"]))
    body = _video(env, env["teacher"], lesson["id"]).json()
    claims = jwt.decode(body["token"], _LK.api_secret, algorithms=["HS256"])
    assert claims["video"]["roomAdmin"] is True and body["is_host"] is True
    assert env["lessons"].list_attendance(lesson["id"]) == []


def test_video_only_for_live_online_lessons(env, lk):
    lesson = _create(env)
    assert _video(env, env["ali"], lesson["id"]).status_code == 409
    offline = _create(env, mode="offline")
    env["client"].post(f"/live/lessons/{offline['id']}/start", headers=_auth(env["teacher"]))
    assert _video(env, env["ali"], offline["id"]).status_code == 409
    assert _video(env, env["outsider"], lesson["id"]).status_code == 404


def test_video_without_livekit_keys_is_503(env):
    app.dependency_overrides[get_livekit_config] = lambda: None
    lesson = _create(env)
    env["client"].post(f"/live/lessons/{lesson['id']}/start", headers=_auth(env["teacher"]))
    r = _video(env, env["ali"], lesson["id"])
    assert r.status_code == 503 and "LiveKit" in r.json()["detail"]


def _system_texts(chat_id):
    return [m["content"] for m in app.state.message_store.list_by_chat(chat_id) if m["kind"] == "system"]


def test_start_announces_in_class_chat_once_per_start(env):
    """Tələbə dərsin başladığını yalnız səhifəni açanda görürdü."""
    lesson = _create(env)
    url = f"/live/lessons/{lesson['id']}/start"
    for _ in range(2):  # artıq canlı dərsə təkrar «başlat» ikinci mesaj yazmır
        assert env["client"].post(url, headers=_auth(env["teacher"])).status_code == 200
    texts = _system_texts(env["chat"]["id"])[1:]  # [0] = «Yeni dərs»
    assert texts == ["Dərs başladı: «Konstitusiya: giriş». Qoşulmaq üçün: Bu gün → Qoşul."]

    env["client"].post(f"/live/lessons/{lesson['id']}/end", headers=_auth(env["teacher"]))
    env["client"].post(url, headers=_auth(env["teacher"]))
    assert len(_system_texts(env["chat"]["id"])) == 3


def test_offline_start_message_points_to_qr(env):
    lesson = _create(env, mode="offline", title="Sinif dərsi")
    env["client"].post(f"/live/lessons/{lesson['id']}/start", headers=_auth(env["teacher"]))
    assert "QR" in _system_texts(env["chat"]["id"])[-1]


def test_student_start_writes_nothing(env):
    lesson = _create(env)
    r = env["client"].post(f"/live/lessons/{lesson['id']}/start", headers=_auth(env["ali"]))
    assert r.status_code == 403
    assert len(_system_texts(env["chat"]["id"])) == 1  # yalnız «Yeni dərs»


def test_new_lesson_is_announced_with_baku_time(env):
    """Tələbə yeni dərsi yalnız «Dərslər»i açanda görürdü. Vaxt UTC saxlanır,
    çat mesajı isə düz mətndir: Bakı vaxtı (UTC+4) yazılır."""
    _create(env, starts_at="2026-11-05T06:00:00Z", mode="offline")
    assert _system_texts(env["chat"]["id"]) == [
        "Yeni dərs: «Konstitusiya: giriş», 05.11.2026, 10:00 (Bakı vaxtı), sinifdə. Ətraflı: Dərslər."
    ]


def test_only_time_or_mode_change_of_upcoming_lesson_is_announced(env):
    lesson = _create(env, starts_at="2026-11-05T06:00:00Z")
    url = f"/live/lessons/{lesson['id']}"
    env["client"].patch(url, json={"notes": "plan", "title": "Konstitusiya"}, headers=_auth(env["teacher"]))
    assert len(_system_texts(env["chat"]["id"])) == 1
    env["client"].patch(url, json={"starts_at": "2026-11-06T08:30:00Z"}, headers=_auth(env["teacher"]))
    assert _system_texts(env["chat"]["id"])[-1] == (
        "Dərs dəyişdi: «Konstitusiya» indi 06.11.2026, 12:30 (Bakı vaxtı), onlayn."
    )
    env["client"].post(f"{url}/start", headers=_auth(env["teacher"]))
    env["client"].post(f"{url}/end", headers=_auth(env["teacher"]))
    count = len(_system_texts(env["chat"]["id"]))
    env["client"].patch(url, json={"starts_at": "2026-11-07T08:30:00Z"}, headers=_auth(env["teacher"]))
    assert len(_system_texts(env["chat"]["id"])) == count  # bitmiş dərsin vaxtı tarixdir


def test_cancelled_lesson_is_announced_and_refused_delete_is_not(env):
    lesson = _create(env, starts_at="2026-11-05T06:00:00Z")
    url = f"/live/lessons/{lesson['id']}"
    assert env["client"].delete(url, headers=_auth(env["ali"])).status_code == 403
    assert len(_system_texts(env["chat"]["id"])) == 1
    assert env["client"].delete(url, headers=_auth(env["teacher"])).status_code == 204
    assert _system_texts(env["chat"]["id"])[-1] == (
        "Dərs ləğv olundu: «Konstitusiya: giriş» (05.11.2026, 10:00, Bakı vaxtı)."
    )
