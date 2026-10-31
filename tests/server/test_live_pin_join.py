"""PIN ilə qonaq qoşulması (2026-10-30, istifadəçi qərarı ilə qayıdıb).

Hesabsız tələbə `qosul.html`-də PIN (və ya `?pin=` linki) + ad yazır.
Yoxlananlar:
  - sessiya yaranan kimi 6 rəqəmli PIN alır, müəllim onu görür
  - qonaq adla qoşulur, cavablayır, hesabatda görünür
  - səhifəni yeniləyən qonaq (eyni brauzer açarı) YENİ sətir yaratmır
  - bitmiş sessiyanın PIN-i işləmir, səhv PIN sürət limitinə düşür
  - qonaq sayı kursun `seat_limit`-i ilə məhdudlaşır
  - sinif üzvü tokenlə PIN-dən gəlsə hesablı iştirakçı olur
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion
from server.app import (
    PIN_MAX_FAILURES,
    app,
    get_chat_store,
    get_live_connection_manager,
    get_live_session_store,
    get_question_set_store,
    get_token_secret,
    get_user_store,
)
from server.auth import create_token
from server.chat_store import ChatStore
from server.live_connection_manager import LiveConnectionManager
from server.live_session_store import LiveSessionStore
from server.question_set_store import QuestionSetStore
from server.user_store import DEFAULT_COURSE_ID, UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"
_GUEST = "qonaq-acari-0001"


@pytest.fixture
def env():
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    question_sets = QuestionSetStore(":memory:")
    live_sessions = LiveSessionStore(":memory:")
    manager = LiveConnectionManager()

    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_chat_store] = lambda: chats
    app.dependency_overrides[get_question_set_store] = lambda: question_sets
    app.dependency_overrides[get_live_session_store] = lambda: live_sessions
    app.dependency_overrides[get_live_connection_manager] = lambda: manager
    app.dependency_overrides[get_token_secret] = lambda: _SECRET

    teacher = users.create("muellim@kurs.az", "hash", "Müəllim")
    users.set_teacher(teacher["id"], True)
    teacher = users.get_by_id(teacher["id"])
    student = users.create("telebe@kurs.az", "hash", "Üzv tələbə")

    chat = chats.create(kind="group", created_by=teacher["id"], name="11-A")
    for member in (teacher, student):
        chats.add_member(chat["id"], member["id"])

    qs = question_sets.create(
        subject="mentiq", title="Silloqizmlər", material_kind="link",
        material_location="https://x.az", created_by=teacher["id"],
    )
    for i in range(2):
        question_sets.add_question(qs["id"], MCQQuestion(
            question=f"Sual {i}?", options=["A", "B", "C", "D", "E"],
            correct_index=0, explanation="izah",
        ))
    question_sets.mark_ready(qs["id"])

    client = TestClient(app)
    r = client.post(
        "/live/sessions",
        json={"question_set_id": qs["id"], "chat_id": chat["id"]},
        headers={"Authorization": f"Bearer {create_token(teacher['id'], secret=_SECRET)}"},
    )
    assert r.status_code == 201, r.text

    yield {
        "client": client, "users": users, "chats": chats, "live_sessions": live_sessions,
        "teacher": teacher, "student": student, "chat": chat, "session": r.json(),
    }
    app.dependency_overrides.clear()


def _play_url(pin: str, name: str = "Aysel", guest: str = _GUEST, token: str = "") -> str:
    url = f"/ws/live/pin/{pin}/play?name={name}&guest={guest}"
    return url + (f"&token={token}" if token else "")


def _expect_rejection(ws, code: int) -> str:
    payload = ws.receive_json()
    assert payload["type"] == "error" and payload["detail"]
    assert ws.receive().get("code") == code
    return payload["detail"]


def test_session_gets_a_six_digit_pin(env):
    pin = env["session"]["pin"]
    assert len(pin) == 6 and pin.isdigit()


def test_teacher_sees_pin_in_chat_card_student_does_not(env):
    def card(user):
        token = create_token(user["id"], secret=_SECRET)
        r = env["client"].get(
            f"/chats/{env['chat']['id']}/live-session", headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        return r.json()

    assert card(env["teacher"])["pin"] == env["session"]["pin"]
    assert card(env["student"])["pin"] is None


def test_lookup_returns_title_without_session_id(env):
    r = env["client"].get(f"/live/pin/{env['session']['pin']}")
    assert r.status_code == 200
    assert r.json() == {"title": "Silloqizmlər", "subject": "mentiq", "status": "waiting"}


def test_guest_joins_without_account(env):
    pin = env["session"]["pin"]
    with env["client"].websocket_connect(_play_url(pin)) as ws:
        joined = ws.receive_json()
        assert joined["type"] == "joined"

    participants = env["live_sessions"].list_participants(env["session"]["id"])
    assert [(p["display_name"], p["user_id"]) for p in participants] == [("Aysel", None)]


def test_guest_answers_a_running_session(env):
    session_id = env["session"]["id"]
    env["live_sessions"].start(session_id, 300)
    with env["client"].websocket_connect(_play_url(env["session"]["pin"])) as ws:
        participant_id = ws.receive_json()["participant_id"]
        question = ws.receive_json()  # gec qoşulma: 0-cı sual dərhal gəlir
        assert question["type"] == "question" and question["index"] == 0
        ws.send_json({"type": "answer", "question_index": 0, "chosen_index": 0})
        ws.receive_json()
    assert env["live_sessions"].count_answers_by_participant(session_id, participant_id) == 1


def test_reconnecting_guest_keeps_the_same_row(env):
    """Sessiya #31 bug-ının qonaq versiyası: səhifəni yeniləyən qonaq
    eyni brauzer açarı ilə gəlir və yeni sətir yaranmamalıdır."""
    pin = env["session"]["pin"]
    ids = []
    for _ in range(3):
        with env["client"].websocket_connect(_play_url(pin)) as ws:
            ids.append(ws.receive_json()["participant_id"])
    assert len(set(ids)) == 1
    assert env["live_sessions"].count_participants(env["session"]["id"]) == 1


def test_two_guests_with_same_name_are_separate(env):
    pin = env["session"]["pin"]
    for key in ("acar-birinci-1", "acar-ikinci-22"):
        with env["client"].websocket_connect(_play_url(pin, guest=key)) as ws:
            ws.receive_json()
    assert env["live_sessions"].count_guests(env["session"]["id"]) == 2


@pytest.mark.parametrize("name", ["", "   ", "x" * 41])
def test_guest_name_is_required_and_bounded(env, name):
    with env["client"].websocket_connect(_play_url(env["session"]["pin"], name=name)) as ws:
        _expect_rejection(ws, 4400)


def test_guest_key_must_be_well_formed(env):
    with env["client"].websocket_connect(_play_url(env["session"]["pin"], guest="qısa")) as ws:
        _expect_rejection(ws, 4400)


def test_unknown_pin_is_rejected(env):
    wrong = "000000" if env["session"]["pin"] != "000000" else "111111"
    assert env["client"].get(f"/live/pin/{wrong}").status_code == 404
    with env["client"].websocket_connect(_play_url(wrong)) as ws:
        _expect_rejection(ws, 4404)


def test_finished_session_pin_no_longer_works(env):
    env["live_sessions"].set_status(env["session"]["id"], "finished")
    assert env["client"].get(f"/live/pin/{env['session']['pin']}").status_code == 404


def test_wrong_pins_are_rate_limited(env):
    wrong = "000000" if env["session"]["pin"] != "000000" else "111111"
    for _ in range(PIN_MAX_FAILURES):
        assert env["client"].get(f"/live/pin/{wrong}").status_code == 404
    # Limitə çatandan sonra DOĞRU PIN də keçmir — təxmin dayanmalıdır.
    assert env["client"].get(f"/live/pin/{env['session']['pin']}").status_code == 429


def test_guests_are_capped_by_course_seat_limit(env):
    env["users"].courses.update_settings(DEFAULT_COURSE_ID, seat_limit=1)
    pin = env["session"]["pin"]
    with env["client"].websocket_connect(_play_url(pin, guest="acar-birinci-1")) as ws:
        ws.receive_json()
    with env["client"].websocket_connect(_play_url(pin, guest="acar-ikinci-22")) as ws:
        _expect_rejection(ws, 4409)
    # Artıq qoşulmuş qonaq qayıda bilir — limit YENİ yerlərə aiddir.
    with env["client"].websocket_connect(_play_url(pin, guest="acar-birinci-1")) as ws:
        assert ws.receive_json()["type"] == "joined"


def test_chat_member_with_token_joins_with_account(env):
    token = create_token(env["student"]["id"], secret=_SECRET)
    with env["client"].websocket_connect(_play_url(env["session"]["pin"], name="", token=token)) as ws:
        assert ws.receive_json()["type"] == "joined"
    [participant] = env["live_sessions"].list_participants(env["session"]["id"])
    assert participant["user_id"] == env["student"]["id"]
    assert participant["display_name"] == "Üzv tələbə"


def test_member_of_other_course_joins_as_guest(env):
    """Başqa kursun hesabı tokenlə gəlsə, hesabı bu sessiyaya BAĞLANMIR —
    kurs sərhədi pozulmasın. O, adını yazan qonaq kimi qoşulur."""
    other_course = env["users"].courses.create("Başqa kurs", "exam_prep", trial_days=7, seat_limit=None)
    other = env["users"].create("kenar@diger.az", "hash", "Kənar", course_id=other_course["id"])
    token = create_token(other["id"], secret=_SECRET)
    with env["client"].websocket_connect(_play_url(env["session"]["pin"], token=token)) as ws:
        assert ws.receive_json()["type"] == "joined"
    [participant] = env["live_sessions"].list_participants(env["session"]["id"])
    assert participant["user_id"] is None
    assert participant["display_name"] == "Aysel"


def test_chat_member_with_ws_ticket_joins_with_account(env):
    """Brauzer JWT-ni URL-ə yazmır: əvvəl birdəfəlik ticket alır."""
    from server.app import get_ws_ticket_store
    from server.ws_ticket import WsTicketStore

    tickets = WsTicketStore()
    app.dependency_overrides[get_ws_ticket_store] = lambda: tickets
    ticket = tickets.issue(env["student"]["id"])
    url = _play_url(env["session"]["pin"], name="") + f"&ticket={ticket}"
    with env["client"].websocket_connect(url) as ws:
        assert ws.receive_json()["type"] == "joined"
    [participant] = env["live_sessions"].list_participants(env["session"]["id"])
    assert participant["user_id"] == env["student"]["id"]
    assert len(tickets) == 0


def test_used_ticket_falls_back_to_guest(env):
    """İşlənmiş ticket hesab vermir: ad varsa qonaq kimi qoşulur."""
    from server.app import get_ws_ticket_store
    from server.ws_ticket import WsTicketStore

    app.dependency_overrides[get_ws_ticket_store] = lambda: WsTicketStore()
    url = _play_url(env["session"]["pin"]) + "&ticket=islenmis"
    with env["client"].websocket_connect(url) as ws:
        assert ws.receive_json()["type"] == "joined"
    [participant] = env["live_sessions"].list_participants(env["session"]["id"])
    assert participant["user_id"] is None
