"""`/live/*` endpointlərinin müəllim icazəsi.

REAL BOŞLUQ İDİ (2026-09-10-da tapıldı). Bu beş endpoint YALNIZ
`get_current_user`-dan keçirdi, yəni İSTƏNİLƏN qeydiyyatdan keçmiş
tələbə bunları edə bilirdi:

  POST /live/question-sets          → sual bankı YARADA bilirdi, yəni
                                      AI generasiyasını işə salıb Groq/
                                      Claude kvotasını və VPS diskini
                                      xərcləyə bilirdi (ən ciddisi)
  GET  /live/question-sets          → bütün müəllimlərin bank siyahısı
  GET  /live/question-sets/{id}     → bankın adı, fənni, material ünvanı
  POST /live/sessions               → istənilən hazır bankla canlı
                                      sessiya açıb PIN ala bilirdi
  GET  /live/sessions/{id}/report   → başqa tələbələrin adı və xalları

Sual MƏZMUNU endpointləri (`/questions`, `/quality`, PATCH, DELETE)
onsuz da qorunurdu — boşluq yalnız bunlarda idi.

Veb tərəfdə bu endpointləri YALNIZ müəllim səhifələri çağırır
(`muellim`, `sessiyalar`, `hesabatlar`, `suallar`), ona görə qapının
əlavəsi heç bir tələbə ekranını sındırmır.
"""

import pytest
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion
from server.app import (
    app, get_chat_store, get_live_session_store, get_question_set_store,
    get_token_secret, get_user_store,
)
from server.chat_store import ChatStore
from server.auth import create_token
from server.live_session_store import LiveSessionStore
from server.question_set_store import QuestionSetStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


@pytest.fixture
def env():
    users = UserStore(":memory:")
    question_sets = QuestionSetStore(":memory:")
    live_sessions = LiveSessionStore(":memory:")
    chats = ChatStore(":memory:")

    app.dependency_overrides[get_chat_store] = lambda: chats
    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_question_set_store] = lambda: question_sets
    app.dependency_overrides[get_live_session_store] = lambda: live_sessions
    app.dependency_overrides[get_token_secret] = lambda: _SECRET

    client = TestClient(app)
    teacher = users.create("muellim@masternr1.az", "hash", "Müəllim")
    users.set_teacher(teacher["id"], True)
    teacher = users.get_by_id(teacher["id"])
    student = users.create("telebe@masternr1.az", "hash", "Tələbə")

    qs = question_sets.create(
        subject="mentiq", title="Silloqizmlər", material_kind="link",
        material_location="https://x.az", created_by=teacher["id"],
    )
    question_sets.add_question(qs["id"], MCQQuestion(
        question="Sual?", options=["A", "B", "C", "D", "E"],
        correct_index=0, explanation="izah",
    ))
    question_sets.mark_ready(qs["id"])

    # Sessiya artıq bir çata bağlıdır — həm müəllim, həm tələbə orada
    # üzvdür ki, test İCAZƏ fərqini ölçsün, üzvlük fərqini yox.
    chat = chats.create(kind="group", created_by=teacher["id"], name="11-A")
    chats.add_member(chat["id"], teacher["id"])
    chats.add_member(chat["id"], student["id"])

    yield {
        "client": client, "users": users, "question_sets": question_sets,
        "live_sessions": live_sessions, "teacher": teacher, "student": student,
        "qs": qs, "chat": chat,
    }
    app.dependency_overrides.clear()


def _auth(user) -> dict:
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


class TestStudentIsRefused:
    def test_cannot_create_question_set(self, env):
        """ƏN CİDDİSİ: yaratma AI generasiyasını işə salır — qorunmasa
        istənilən hesab bizim API kvotamızı xərcləyə bilər."""
        r = env["client"].post(
            "/live/question-sets",
            data={"subject": "mentiq", "title": "A", "kind": "link", "location": "https://x.az"},
            headers=_auth(env["student"]),
        )
        assert r.status_code == 403

    def test_cannot_list_question_sets(self, env):
        r = env["client"].get("/live/question-sets", headers=_auth(env["student"]))
        assert r.status_code == 403

    def test_cannot_read_one_question_set(self, env):
        r = env["client"].get(f"/live/question-sets/{env['qs']['id']}", headers=_auth(env["student"]))
        assert r.status_code == 403

    def test_cannot_read_teacher_summary(self, env):
        r = env["client"].get("/live/teacher-summary", headers=_auth(env["student"]))
        assert r.status_code == 403

    def test_cannot_start_a_live_session(self, env):
        r = env["client"].post(
            "/live/sessions",
            json={"question_set_id": env["qs"]["id"], "chat_id": env["chat"]["id"]},
            headers=_auth(env["student"]),
        )
        assert r.status_code == 403

    def test_cannot_read_a_session_report(self, env):
        """Hesabatda BAŞQA tələbələrin adı və xalı var."""
        session = env["live_sessions"].create_session(env["qs"]["id"])
        r = env["client"].get(
            f"/live/sessions/{session['id']}/report", headers=_auth(env["student"])
        )
        assert r.status_code == 403


class TestTeacherIsAllowed:
    """Qapı müəllimi bloklamamalıdır — əks halda pilot dayanar."""

    def test_can_list_question_sets(self, env):
        r = env["client"].get("/live/question-sets", headers=_auth(env["teacher"]))
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_can_read_one_question_set(self, env):
        r = env["client"].get(f"/live/question-sets/{env['qs']['id']}", headers=_auth(env["teacher"]))
        assert r.status_code == 200

    def test_can_read_teacher_summary(self, env):
        r = env["client"].get("/live/teacher-summary", headers=_auth(env["teacher"]))
        assert r.status_code == 200

    def test_can_start_a_live_session(self, env):
        r = env["client"].post(
            "/live/sessions",
            json={"question_set_id": env["qs"]["id"], "chat_id": env["chat"]["id"]},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 201


class TestUnauthenticatedStillGets401:
    """403 (müəllim deyil) ilə 401 (giriş yoxdur) QARIŞDIRILMAMALIDIR —
    client 401-də istifadəçini giriş səhifəsinə yönəldir."""

    def test_no_token_is_401_not_403(self, env):
        assert env["client"].get("/live/question-sets").status_code == 401
        assert env["client"].get("/live/teacher-summary").status_code == 401


class TestNoLiveEndpointForgetsTheGate:
    """Statik qoruyucu: `/live/*` HTTP endpointlərinin HAMISI müəllim
    qapısından keçməlidir.

    Yuxarıdakı testlər bu gün mövcud olan endpointləri yoxlayır; bu test
    isə SABAH əlavə ediləni. Boşluq məhz belə yarandı - endpoint əlavə
    edildi, yoxlama unuduldu, heç bir test bunu görmədi.

    QEYD: tələbələr canlı sessiyaya `/ws/live/{pin}/play` WebSocket-i ilə
    qoşulur (hesabsız, PIN ilə) - o, `/live/` prefiksində DEYİL, ona görə
    bu qayda tələbə axınına toxunmur.
    """

    def test_every_live_http_route_requires_a_teacher(self):
        import inspect
        import re

        from server import app as app_module

        source = inspect.getsource(app_module)
        # Dekorator + ardınca gələn funksiya imzası (ilk `) ->`-a qədər).
        routes = []
        for match in re.finditer(r'@app\.(?:get|post|put|patch|delete)\(\s*"(/live/[^"]*)"', source):
            path = match.group(1)
            body = source[match.end():]
            signature_end = body.index("\n) ")
            routes.append((path, body[:signature_end]))

        assert len(routes) >= 6, "regex sınıb ola bilər - /live/ endpointləri tapılmadı"

        ungated = [path for path, signature in routes if "get_current_teacher" not in signature]
        assert not ungated, (
            "bu /live/ endpointləri müəllim qapısından keçmir: " + ", ".join(ungated)
        )
