"""Lisenziya qapısı — bağlı kurs heç bir HTTP/WS yolu ilə data almır.

Spec 2026-09-29 §2:
  - HTTP: bağlı kurs → 402; `is_active=0` → 401; platforma sahibi azad
  - Giriş: kurs yalnız ŞİFRƏ DOĞRU olandan sonra yoxlanır (sızma yoxdur)
  - WS: accept + səbəb + close(4402) — accept-siz close brauzerdə 1006 olur
  - Çat WS: hər mesajda yoxlanır (kurs söhbət ortasında bağlana bilər)
  - Canlı sessiya: BAŞLAMIŞ sessiya sonuna qədər gedir, başlamamışa
    qoşulmaq olmur
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion
from server.app import (
    app,
    get_chat_store,
    get_friendship_store,
    get_live_connection_manager,
    get_live_session_store,
    get_message_store,
    get_question_set_store,
    get_token_secret,
    get_user_store,
)
from server.auth import create_token, hash_password
from server.chat_store import ChatStore
from server.course_store import DEFAULT_COURSE_ID
from server.friendship_store import FriendshipStore
from server.live_connection_manager import LiveConnectionManager
from server.live_session_store import LiveSessionStore
from server.message_store import MessageStore
from server.question_set_store import QuestionSetStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"
_PASSWORD = "doğru-şifrə-123"


@pytest.fixture
def env():
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    messages = MessageStore(":memory:")
    question_sets = QuestionSetStore(":memory:")
    live_sessions = LiveSessionStore(":memory:")
    overrides = {
        get_user_store: users,
        get_chat_store: chats,
        get_message_store: messages,
        get_friendship_store: FriendshipStore(":memory:"),
        get_question_set_store: question_sets,
        get_live_session_store: live_sessions,
        get_live_connection_manager: LiveConnectionManager(),
    }
    # `lambda v=value: v` İŞLƏMİR: FastAPI `v`-ni sorğu parametri sayıb
    # default-u (sqlite bağlantısını) kopyalamağa çalışır.
    def _const(value):
        return lambda: value

    for dep, value in overrides.items():
        app.dependency_overrides[dep] = _const(value)
    app.dependency_overrides[get_token_secret] = lambda: _SECRET

    courses = users.courses
    open_course = courses.create("Açıq", "english", trial_days=30, seat_limit=30)
    expired = courses.create("Bitmiş sınaq", "english", trial_days=-1, seat_limit=30)
    suspended = courses.create("Dayandırılmış", "english", trial_days=30, seat_limit=30)
    courses.set_status(suspended["id"], "suspended")
    unpaid = courses.create("Ödənişi bitmiş", "english", trial_days=-40, seat_limit=30)
    courses.set_paid_until(unpaid["id"], datetime.now(timezone.utc) - timedelta(minutes=1))

    def _user(email, course, *, teacher=False):
        row = users.create(email, hash_password(_PASSWORD), email.split("@")[0],
                           course_id=course["id"])
        if teacher:
            users.set_teacher(row["id"], True)
        return users.get_by_id(row["id"])

    yield {
        "client": TestClient(app),
        "users": users, "courses": courses, "chats": chats, "messages": messages,
        "question_sets": question_sets, "live_sessions": live_sessions,
        "open": open_course, "expired": expired, "suspended": suspended, "unpaid": unpaid,
        "owner_course": courses.get(DEFAULT_COURSE_ID),
        "make_user": _user,
    }
    app.dependency_overrides.clear()


def _auth(user):
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


def _token(user):
    return create_token(user["id"], secret=_SECRET)


def _ws_reason(client, url):
    with client.websocket_connect(url) as ws:
        payload = ws.receive_json()
        closing = ws.receive()
    return payload, closing.get("code")


# ---- HTTP -----------------------------------------------------------------


class TestHttpGate:
    def test_open_course_passes(self, env):
        user = env["make_user"]("a@x.az", env["open"])
        assert env["client"].get("/friends", headers=_auth(user)).status_code == 200

    @pytest.mark.parametrize("course_key", ["expired", "suspended", "unpaid"])
    def test_closed_course_gets_402(self, env, course_key):
        user = env["make_user"]("a@x.az", env[course_key])
        r = env["client"].get("/friends", headers=_auth(user))
        assert r.status_code == 402
        assert "abunə" in r.json()["detail"].lower()

    def test_closed_course_blocks_teacher_endpoints(self, env):
        teacher = env["make_user"]("t@x.az", env["expired"], teacher=True)
        r = env["client"].get("/live/question-sets", headers=_auth(teacher))
        assert r.status_code == 402

    def test_owner_course_never_closes(self, env):
        user = env["make_user"]("a@x.az", env["owner_course"])
        assert env["client"].get("/friends", headers=_auth(user)).status_code == 200

    def test_platform_owner_passes_closed_course(self, env):
        user = env["make_user"]("sahib@x.az", env["suspended"])
        env["users"].set_platform_owner(user["id"], True)
        assert env["client"].get("/friends", headers=_auth(user)).status_code == 200

    def test_inactive_user_token_stops_working(self, env):
        """Kursdan çıxarılan tələbənin 90 günlük tokeni NÖVBƏTİ sorğuda ölür."""
        user = env["make_user"]("a@x.az", env["open"])
        env["users"].set_active(user["id"], False)
        assert env["client"].get("/friends", headers=_auth(user)).status_code == 401

    def test_reactivation_is_immediate(self, env):
        """Ödənişdən sonra data silinməyib, giriş dərhal açılır."""
        user = env["make_user"]("a@x.az", env["suspended"])
        assert env["client"].get("/friends", headers=_auth(user)).status_code == 402
        env["courses"].set_status(env["suspended"]["id"], "trial")
        assert env["client"].get("/friends", headers=_auth(user)).status_code == 200


class TestLogin:
    def _login(self, env, email, password=_PASSWORD):
        return env["client"].post("/auth/login", json={"email": email, "password": password})

    def test_closed_course_correct_password_gets_402(self, env):
        env["make_user"]("a@x.az", env["expired"])
        r = self._login(env, "a@x.az")
        assert r.status_code == 402
        assert "token" not in r.json()

    def test_closed_course_wrong_password_gets_401_not_402(self, env):
        """402 yalnız doğru şifrədən sonra — əks halda şifrəsiz «bu e-poçt
        bağlı kursdadır» öyrənmək olardı."""
        env["make_user"]("a@x.az", env["expired"])
        r = self._login(env, "a@x.az", "səhv-şifrə")
        assert r.status_code == 401

    def test_inactive_user_gets_generic_401(self, env):
        user = env["make_user"]("a@x.az", env["open"])
        env["users"].set_active(user["id"], False)
        r = self._login(env, "a@x.az")
        assert r.status_code == 401
        wrong = self._login(env, "yoxdur@x.az")
        assert r.json()["detail"] == wrong.json()["detail"]

    def test_platform_owner_logs_in_to_closed_course(self, env):
        user = env["make_user"]("sahib@x.az", env["suspended"])
        env["users"].set_platform_owner(user["id"], True)
        assert self._login(env, "sahib@x.az").status_code == 200

    def test_open_course_logs_in(self, env):
        env["make_user"]("a@x.az", env["open"])
        assert self._login(env, "a@x.az").status_code == 200


class TestMeCourse:
    def test_trial_course_info(self, env):
        user = env["make_user"]("a@x.az", env["open"])
        r = env["client"].get("/me/course", headers=_auth(user))
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "Açıq"
        assert body["status"] == "trial"
        assert body["days_left"] == 30
        assert body["is_open"] is True

    def test_owner_course_has_no_days_left(self, env):
        user = env["make_user"]("a@x.az", env["owner_course"])
        body = env["client"].get("/me/course", headers=_auth(user)).json()
        assert body["status"] == "owner"
        assert body["days_left"] is None

    def test_requires_auth(self, env):
        assert env["client"].get("/me/course").status_code == 401

    def test_closed_course_gets_402(self, env):
        user = env["make_user"]("a@x.az", env["expired"])
        assert env["client"].get("/me/course", headers=_auth(user)).status_code == 402


# ---- WebSocket: çat -------------------------------------------------------


class TestChatWebsocket:
    def _chat_for(self, env, user):
        chat = env["chats"].create(kind="group", created_by=user["id"], name="Sinif",
                                   course_id=user["course_id"])
        env["chats"].add_member(chat["id"], user["id"])
        return chat

    def test_closed_course_rejected_with_4402(self, env):
        user = env["make_user"]("a@x.az", env["expired"])
        chat = self._chat_for(env, user)
        payload, code = _ws_reason(env["client"], f"/ws/chat/{chat['id']}?token={_token(user)}")
        assert code == 4402
        assert payload["type"] == "error"
        assert "abunə" in payload["detail"].lower()

    def test_inactive_user_rejected_with_4401(self, env):
        user = env["make_user"]("a@x.az", env["open"])
        chat = self._chat_for(env, user)
        env["users"].set_active(user["id"], False)
        _, code = _ws_reason(env["client"], f"/ws/chat/{chat['id']}?token={_token(user)}")
        assert code == 4401

    def test_course_closing_mid_conversation_stops_messages(self, env):
        """Açıq bağlantı qapını keçib — kurs bağlanandan sonra göndərilən
        mesaj yazılmamalı və bağlantı 4402 ilə bağlanmalıdır."""
        user = env["make_user"]("a@x.az", env["open"])
        chat = self._chat_for(env, user)
        with env["client"].websocket_connect(f"/ws/chat/{chat['id']}?token={_token(user)}") as ws:
            assert ws.receive_json()["type"] == "history"
            env["courses"].set_status(env["open"]["id"], "suspended")
            ws.send_json({"type": "text", "content": "salam"})
            payload = ws.receive_json()
            closing = ws.receive()
        assert payload["type"] == "error"
        assert closing.get("code") == 4402
        assert env["messages"].list_by_chat(chat["id"]) == []


# ---- WebSocket: canlı sessiya ---------------------------------------------


def _live_setup(env, course):
    teacher = env["make_user"]("t@x.az", course, teacher=True)
    student = env["make_user"]("s@x.az", course)
    chat = env["chats"].create(kind="group", created_by=teacher["id"], name="Sinif",
                               course_id=course["id"])
    for member in (teacher, student):
        env["chats"].add_member(chat["id"], member["id"])
    qs = env["question_sets"].create(
        subject="mentiq", title="Unit", material_kind="link",
        material_location="https://x.az", created_by=teacher["id"], course_id=course["id"],
    )
    env["question_sets"].add_question(qs["id"], MCQQuestion(
        question="Q?", options=["A", "B", "C", "D", "E"], correct_index=0, explanation="izah",
    ))
    env["question_sets"].mark_ready(qs["id"])
    session = env["live_sessions"].create_session(qs["id"], chat_id=chat["id"],
                                                  created_by=teacher["id"])
    return teacher, student, session


class TestLiveWebsocket:
    def test_waiting_session_host_rejected_when_course_closed(self, env):
        teacher, _, session = _live_setup(env, env["open"])
        env["courses"].set_status(env["open"]["id"], "suspended")
        _, code = _ws_reason(
            env["client"], f"/ws/live/sessions/{session['id']}/host?token={_token(teacher)}"
        )
        assert code == 4402

    def test_waiting_session_player_rejected_when_course_closed(self, env):
        _, student, session = _live_setup(env, env["open"])
        env["courses"].set_status(env["open"]["id"], "suspended")
        _, code = _ws_reason(
            env["client"], f"/ws/live/sessions/{session['id']}/play?token={_token(student)}"
        )
        assert code == 4402

    def test_started_session_runs_to_end_after_course_closes(self, env):
        """İstifadəçi qərarı: «başlamış sessiya sonuna qədər getsin».
        Tələbə telefonu kilidlənib qayıdanda da qoşula bilməlidir."""
        teacher, student, session = _live_setup(env, env["open"])
        env["live_sessions"].start(session["id"], duration_seconds=300)
        env["courses"].set_status(env["open"]["id"], "suspended")

        with env["client"].websocket_connect(
            f"/ws/live/sessions/{session['id']}/play?token={_token(student)}"
        ) as ws:
            assert ws.receive_json()["type"] == "joined"
        with env["client"].websocket_connect(
            f"/ws/live/sessions/{session['id']}/host?token={_token(teacher)}"
        ) as ws:
            assert ws.receive_json()["type"] == "state"

    def test_inactive_student_rejected_even_in_started_session(self, env):
        _, student, session = _live_setup(env, env["open"])
        env["live_sessions"].start(session["id"], duration_seconds=300)
        env["users"].set_active(student["id"], False)
        _, code = _ws_reason(
            env["client"], f"/ws/live/sessions/{session['id']}/play?token={_token(student)}"
        )
        assert code == 4401
