"""Sessiya çatın içindən başlayır — endpoint və WS icazələri.

DƏYİŞƏN NƏDİR: əvvəl müəllim ayrıca ekranda sessiya açır, PIN alır və
onu sinifə deyirdi; tələbə isə PIN yazırdı. İndi sessiya bir ÇATA
bağlıdır, «hansı sinif» sualı çat üzvlüyü ilə cavablanır və tələbə
heç nə yazmır.

İcazə qərarları (spec-dən):
  - sessiyanı ÇATDAKI istənilən MÜƏLLİM başlada bilər, tələbə YOX
  - host konsolu YALNIZ sessiyanı başladanındır (çatda iki müəllim
    ola bilər, amma idarə edən bir nəfərdir)
  - oyun bağlantısı üçün token MƏCBURİDİR (anonim yol silinir)
  - GEC QOŞULMA açıqdır
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion
from server.app import (
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
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


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

    def _user(email, name, *, teacher=False):
        row = users.create(email, "hash", name)
        if teacher:
            users.set_teacher(row["id"], True)
        return users.get_by_id(row["id"])

    teacher = _user("muellim@masternr1.az", "Müəllim", teacher=True)
    teacher2 = _user("muellim2@masternr1.az", "İkinci müəllim", teacher=True)
    student = _user("telebe@masternr1.az", "Tələbə")
    outsider = _user("kenar@masternr1.az", "Kənar")
    outside_teacher = _user("kenarmuellim@masternr1.az", "Kənar müəllim", teacher=True)

    chat = chats.create(kind="group", created_by=teacher["id"], name="11-A")
    for member in (teacher, teacher2, student):
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

    yield {
        "client": TestClient(app), "users": users, "chats": chats,
        "question_sets": question_sets, "live_sessions": live_sessions,
        "manager": manager, "chat": chat, "qs": qs,
        "teacher": teacher, "teacher2": teacher2, "student": student,
        "outsider": outsider, "outside_teacher": outside_teacher,
    }
    app.dependency_overrides.clear()


def _token(user: dict) -> str:
    return create_token(user["id"], secret=_SECRET)


def _auth(user: dict) -> dict:
    return {"Authorization": f"Bearer {_token(user)}"}


def _expect_rejection(ws, code: int) -> None:
    """Rədd HƏMİŞƏ iki addımdır: əvvəlcə SƏBƏB mesajı, sonra bağlanma.

    `_reject_websocket` qəsdən belə yazılıb — `accept()`-dən əvvəl
    bağlansa, brauzerə 4401/4403/4404 yox, 1006 çatır və client sonsuz
    yenidən qoşulur (real produksiyada baş verib). Ona görə test
    yalnız kodu yox, istifadəçiyə görünən səbəbin varlığını da yoxlayır.
    """
    payload = ws.receive_json()
    assert payload["type"] == "error"
    assert payload["detail"], "rədd səbəbsizdir - brauzerdə izah görünməz"
    assert ws.receive().get("code") == code


def _start(env, user=None) -> dict:
    """Sessiyanı endpoint vasitəsilə yaradır (store-a birbaşa yazmır —
    icazə yolunun özü də sınanmalıdır)."""
    user = user or env["teacher"]
    r = env["client"].post(
        "/live/sessions",
        json={"question_set_id": env["qs"]["id"], "chat_id": env["chat"]["id"]},
        headers=_auth(user),
    )
    assert r.status_code == 201, r.text
    return r.json()


class TestCreatingASession:
    def test_chat_id_is_required(self, env):
        """Sütun NULLABLE-dır (köhnə sessiyalar üçün), amma endpoint
        onu MƏCBURİ tələb edir — çatsız sessiya artıq mənasızdır."""
        r = env["client"].post(
            "/live/sessions",
            json={"question_set_id": env["qs"]["id"]},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 422

    def test_teacher_in_the_chat_can_start(self, env):
        session = _start(env)
        assert session["chat_id"] == env["chat"]["id"]
        assert session["created_by"] == env["teacher"]["id"]

    def test_any_teacher_in_the_chat_can_start(self, env):
        """Spec qərarı: çatı yaradan deyil, çatdakı İSTƏNİLƏN müəllim."""
        session = _start(env, env["teacher2"])
        assert session["created_by"] == env["teacher2"]["id"]

    def test_a_student_in_the_chat_cannot_start(self, env):
        r = env["client"].post(
            "/live/sessions",
            json={"question_set_id": env["qs"]["id"], "chat_id": env["chat"]["id"]},
            headers=_auth(env["student"]),
        )
        assert r.status_code == 403

    def test_a_teacher_outside_the_chat_cannot_start(self, env):
        """Müəllim olmaq KİFAYƏT ETMİR — əks halda istənilən müəllim
        istənilən sinifdə sessiya aça bilərdi."""
        r = env["client"].post(
            "/live/sessions",
            json={"question_set_id": env["qs"]["id"], "chat_id": env["chat"]["id"]},
            headers=_auth(env["outside_teacher"]),
        )
        assert r.status_code == 403

    def test_unknown_chat_returns_404(self, env):
        r = env["client"].post(
            "/live/sessions",
            json={"question_set_id": env["qs"]["id"], "chat_id": 9999},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 404

    def test_creating_announces_the_session_in_the_chat(self, env):
        """HAMI görməlidir — istifadəçinin əsas tələbi bu idi:
        «QRUPDA MÜƏLLİM SESSİYA BAŞLADANDA HAMI QUZİ GÖRƏ BİLƏCƏK»."""
        url = f"/ws/chat/{env['chat']['id']}?token={_token(env['student'])}"
        with env["client"].websocket_connect(url) as ws:
            # Çat soketi qoşulan kimi mesaj tarixçəsini göndərir —
            # yayım ondan SONRA gəlir.
            assert ws.receive_json()["type"] == "history"
            session = _start(env)
            payload = ws.receive_json()

        assert payload["type"] == "live_session"
        assert payload["session_id"] == session["id"]
        assert payload["title"] == "Silloqizmlər"
        assert payload["started_by_user_id"] == env["teacher"]["id"]


class TestChatSessionLookup:
    def test_member_sees_the_open_session(self, env):
        """Yayım yalnız o an bağlı olanlara çatır — sonra çatı açan
        tələbə sessiyanı bu endpoint ilə görür."""
        session = _start(env)
        r = env["client"].get(
            f"/chats/{env['chat']['id']}/live-session", headers=_auth(env["student"])
        )
        assert r.status_code == 200
        assert r.json()["session_id"] == session["id"]
        # Client bunu öz ID-si ilə müqayisə edir (konsol vs oyun) —
        # adla müqayisə eyni adlı iki müəllimdə səhv işləyərdi.
        assert r.json()["started_by_user_id"] == env["teacher"]["id"]

    def test_no_session_returns_null(self, env):
        r = env["client"].get(
            f"/chats/{env['chat']['id']}/live-session", headers=_auth(env["student"])
        )
        assert r.status_code == 200
        assert r.json() is None

    def test_a_non_member_is_refused(self, env):
        _start(env)
        r = env["client"].get(
            f"/chats/{env['chat']['id']}/live-session", headers=_auth(env["outsider"])
        )
        assert r.status_code == 403


class TestHostSocket:
    def _url(self, session_id: int, user: dict) -> str:
        return f"/ws/live/sessions/{session_id}/host?token={_token(user)}"

    def test_the_starter_gets_the_console(self, env):
        session = _start(env)
        with env["client"].websocket_connect(self._url(session["id"], env["teacher"])) as ws:
            state = ws.receive_json()
        assert state["type"] == "state"
        assert state["session_id"] == session["id"]

    def test_another_teacher_in_the_chat_is_refused(self, env):
        """Spec qərarı: konsol YALNIZ sessiyanı başladanındır. İki
        müəllim eyni anda idarə etsə, sinifdə nə baş verdiyi anlaşılmaz
        olardı."""
        session = _start(env)
        with env["client"].websocket_connect(self._url(session["id"], env["teacher2"])) as ws:
            _expect_rejection(ws, 4403)

    def test_a_student_is_refused(self, env):
        session = _start(env)
        with env["client"].websocket_connect(self._url(session["id"], env["student"])) as ws:
            _expect_rejection(ws, 4403)

    def test_an_outsider_is_refused(self, env):
        session = _start(env)
        with env["client"].websocket_connect(self._url(session["id"], env["outsider"])) as ws:
            _expect_rejection(ws, 4403)

    def test_an_invalid_token_is_refused_with_a_reason(self, env):
        """Rədd SƏBƏBİ ilə olmalıdır: `accept()`-dən əvvəl bağlansa,
        brauzerə 1006 çatır və client sonsuz yenidən qoşulur (real
        produksiyada baş verib)."""
        session = _start(env)
        with env["client"].websocket_connect(
            f"/ws/live/sessions/{session['id']}/host?token=yalan"
        ) as ws:
            _expect_rejection(ws, 4401)

    def test_unknown_session_is_refused(self, env):
        with env["client"].websocket_connect(
            f"/ws/live/sessions/9999/host?token={_token(env['teacher'])}"
        ) as ws:
            _expect_rejection(ws, 4404)


class TestPlaySocket:
    def _url(self, session_id: int, user: dict | None) -> str:
        if user is None:
            return f"/ws/live/sessions/{session_id}/play"
        return f"/ws/live/sessions/{session_id}/play?token={_token(user)}"

    def test_a_chat_member_joins_with_their_own_name(self, env):
        """Tələbə artıq AD YAZMIR — adı hesabından götürülür."""
        session = _start(env)
        with env["client"].websocket_connect(self._url(session["id"], env["student"])) as ws:
            joined = ws.receive_json()

        assert joined["type"] == "joined"
        names = [p["display_name"] for p in env["live_sessions"].list_participants(session["id"])]
        assert names == ["Tələbə"]

    def test_the_participant_is_linked_to_the_account(self, env):
        """Fərdi tarixçə buna söykənir: `user_id` dolmasa, nəticə
        tələbənin tarixçəsində görünməz."""
        session = _start(env)
        with env["client"].websocket_connect(self._url(session["id"], env["student"])):
            pass
        participants = env["live_sessions"].list_participants(session["id"])
        assert participants[0]["user_id"] == env["student"]["id"]

    def test_a_token_is_now_mandatory(self, env):
        """Anonim yol SİLİNİR — əvvəl token könüllü idi və tokensiz
        qoşulan iştirakçı heç bir hesaba bağlanmırdı."""
        session = _start(env)
        with env["client"].websocket_connect(self._url(session["id"], None)) as ws:
            _expect_rejection(ws, 4401)

    def test_an_outsider_is_refused(self, env):
        """Sessiya ID-ləri də ARDICIL-dır — üzvlük yoxlanmasa, qonşu
        sinfin sessiyasına girmək olardı."""
        session = _start(env)
        with env["client"].websocket_connect(self._url(session["id"], env["outsider"])) as ws:
            _expect_rejection(ws, 4403)

    def test_unknown_session_is_refused(self, env):
        with env["client"].websocket_connect(
            f"/ws/live/sessions/9999/play?token={_token(env['student'])}"
        ) as ws:
            _expect_rejection(ws, 4404)


class TestLateJoin:
    def test_a_member_can_join_after_the_session_started(self, env):
        """SPEC QƏRARI: gec qoşulma açıqdır. Əvvəl `waiting` olmayan
        sessiya 4409 ilə rədd edilirdi — real sinifdə tələbə gecikir,
        telefonu söndürülür, dərsə sonradan qoşulur."""
        session = _start(env)
        env["live_sessions"].start(session["id"], 600)

        with env["client"].websocket_connect(
            f"/ws/live/sessions/{session['id']}/play?token={_token(env['student'])}"
        ) as ws:
            assert ws.receive_json()["type"] == "joined"
            # Gec qoşulan DƏRHAL öz ilk sualını almalıdır — `start`
            # yayımı artıq keçib, yəni heç nə göndərilməsə tələbə boş
            # ekrana baxardı.
            question = ws.receive_json()

        assert question["type"] == "question"
        assert question["index"] == 0

    def test_joining_a_finished_session_is_refused(self, env):
        session = _start(env)
        env["live_sessions"].set_status(session["id"], "finished")
        with env["client"].websocket_connect(
            f"/ws/live/sessions/{session['id']}/play?token={_token(env['student'])}"
        ) as ws:
            _expect_rejection(ws, 4404)
