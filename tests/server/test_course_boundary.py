"""Kurs sərhədi (IDOR) — spec 2026-09-29 §4.

Kurs B-nin istifadəçisi kurs A-nın HEÇ BİR obyektini görə, dəyişə və ya
ona qoşula bilməz. Başqa kursun obyekti **404** qaytarır (403 yox — 403
«var, amma sənin deyil» deməkdir və ID-lər ardıcıldır).

QORUYUCU: `test_every_id_route_has_a_cross_course_case` marşrut
cədvəlini oxuyur. Yol, sorğu və ya gövdə vasitəsilə ID/kod/e-poçt qəbul
edən HƏR marşrut ya `CASES`-də olmalıdır, ya da SƏBƏBİ ilə `EXEMPT`-də.
Yeni endpoint yazılıb bu test unudularsa, qırmızı olur.
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute, APIWebSocketRoute
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion
from server.app import (
    app,
    get_badge_store,
    get_chat_join_request_store,
    get_chat_store,
    get_connection_manager,
    get_friendship_store,
    get_homework_store,
    get_join_rate_limiter,
    get_live_connection_manager,
    get_live_session_store,
    get_material_store,
    get_message_store,
    get_question_set_store,
    get_question_store,
    get_quiz_attempt_store,
    get_quiz_session_store,
    get_register_rate_limiter,
    get_token_secret,
    get_upload_dir,
    get_user_store,
)
from server.auth import create_token
from server.badge_store import BadgeStore
from server.chat_join_request_store import ChatJoinRequestStore
from server.chat_store import ChatStore
from server.connection_manager import ConnectionManager
from server.friendship_store import FriendshipStore
from server.homework_store import HomeworkStore
from server.live_connection_manager import LiveConnectionManager
from server.live_session_store import LiveSessionStore
from server.material_store import MaterialStore
from server.message_store import MessageStore
from server.question_set_store import QuestionSetStore
from server.question_store import QuestionStore
from server.quiz_attempt_store import QuizAttemptStore
from server.quiz_session_store import QuizSessionStore
from server.rate_limit import RateLimiter
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"
_QUESTION = MCQQuestion(
    question="Q?", options=["A", "B", "C", "D", "E"], correct_index=0, explanation="izah"
)


@pytest.fixture
def world(tmp_path):
    users = UserStore(":memory:")
    stores = {
        get_user_store: users,
        get_chat_store: ChatStore(":memory:"),
        get_chat_join_request_store: ChatJoinRequestStore(":memory:"),
        get_message_store: MessageStore(":memory:"),
        get_connection_manager: ConnectionManager(),
        get_material_store: MaterialStore(":memory:"),
        get_question_store: QuestionStore(":memory:"),
        get_quiz_session_store: QuizSessionStore(":memory:"),
        get_quiz_attempt_store: QuizAttemptStore(":memory:"),
        get_friendship_store: FriendshipStore(":memory:"),
        get_question_set_store: QuestionSetStore(":memory:"),
        get_live_session_store: LiveSessionStore(":memory:"),
        get_live_connection_manager: LiveConnectionManager(),
        get_homework_store: HomeworkStore(":memory:"),
        get_badge_store: BadgeStore(":memory:"),
        get_join_rate_limiter: RateLimiter(max_attempts=1000),
        get_register_rate_limiter: RateLimiter(max_attempts=1000),
        get_upload_dir: str(tmp_path),
        get_token_secret: _SECRET,
    }

    def _const(value):
        return lambda: value

    for dep, value in stores.items():
        app.dependency_overrides[dep] = _const(value)

    chats = stores[get_chat_store]
    question_sets = stores[get_question_set_store]
    live = stores[get_live_session_store]
    homework = stores[get_homework_store]
    friendships = stores[get_friendship_store]
    materials = stores[get_material_store]

    def course(name):
        return users.courses.create(name, "english", trial_days=30, seat_limit=30)

    def person(email, c, *, teacher=False):
        row = users.create(email, "h", email.split("@")[0], course_id=c["id"])
        if teacher:
            users.set_teacher(row["id"], True)
        return users.get_by_id(row["id"])

    a, b = course("A"), course("B")
    w = {"users": users, "chats": chats, "question_sets": question_sets, "live": live,
         "homework": homework, "friendships": friendships,
         "join_requests": stores[get_chat_join_request_store]}
    w["teacher_a"] = person("ta@a.az", a, teacher=True)
    w["student_a"] = person("sa@a.az", a)
    w["teacher_b"] = person("tb@b.az", b, teacher=True)
    w["student_b"] = person("sb@b.az", b)

    for side, c in (("a", a), ("b", b)):
        chat = chats.create(kind="group", created_by=w[f"teacher_{side}"]["id"],
                            name=f"Sinif {side}", course_id=c["id"])
        chats.add_member(chat["id"], w[f"teacher_{side}"]["id"])
        chats.add_member(chat["id"], w[f"student_{side}"]["id"])
        w[f"chat_{side}"] = chats.get(chat["id"])
        qs = question_sets.create("mentiq", f"Bank {side}", "link", "https://x.az",
                                  created_by=w[f"teacher_{side}"]["id"], course_id=c["id"])
        question_sets.add_question(qs["id"], _QUESTION)
        question_sets.mark_ready(qs["id"])
        w[f"qs_{side}"] = question_sets.get(qs["id"])

    w["question_a"] = question_sets.list_questions(w["qs_a"]["id"])[0]
    w["session_a"] = live.create_session(w["qs_a"]["id"], chat_id=w["chat_a"]["id"],
                                         created_by=w["teacher_a"]["id"])
    finished = live.create_session(w["qs_a"]["id"], chat_id=w["chat_a"]["id"],
                                   created_by=w["teacher_a"]["id"])
    live.set_status(finished["id"], "finished")
    w["finished_a"] = finished
    w["assignment_a"] = homework.create_assignment(
        w["chat_a"]["id"], w["qs_a"]["id"], "2099-01-01", created_by=w["teacher_a"]["id"]
    )
    w["attempt_a"] = homework.get_or_create_attempt(w["assignment_a"]["id"],
                                                    student_id=w["student_a"]["id"])
    w["friendship_a"] = friendships.create(w["teacher_a"]["id"], w["student_a"]["id"])
    w["material_a"] = materials.create(w["chat_a"]["id"], w["teacher_a"]["id"], "link", "https://x.az")
    w["client"] = TestClient(app)
    yield w
    app.dependency_overrides.clear()


def _auth(user):
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


# (method, path) -> (aktyor, yol parametrləri, sorğu parametrləri, gövdə, form)
# Dəyərlər `world`-dən götürülür: "chat_a.id" -> world["chat_a"]["id"].
CASES = {
    ("POST", "/friends/requests/{friendship_id}/accept"): ("student_b", {"friendship_id": "friendship_a.id"}, None, None, None),
    ("POST", "/friends/requests/{friendship_id}/decline"): ("student_b", {"friendship_id": "friendship_a.id"}, None, None, None),
    ("POST", "/friends/requests/{friendship_id}/cancel"): ("student_b", {"friendship_id": "friendship_a.id"}, None, None, None),
    ("POST", "/friends/{friendship_id}/unfriend"): ("student_b", {"friendship_id": "friendship_a.id"}, None, None, None),
    ("POST", "/friends/requests"): ("student_b", {}, None, {"addressee_email": "sa@a.az"}, None),
    ("POST", "/chats"): ("student_b", {}, None, {"kind": "direct", "peer_user_id": "student_a.id"}, None),
    ("POST", "/chats/join-requests"): ("student_b", {}, None, {"code": "chat_a.invite_code"}, None),
    ("GET", "/chats/{chat_id}/join-requests"): ("teacher_b", {"chat_id": "chat_a.id"}, None, None, None),
    ("POST", "/chats/{chat_id}/join-requests/approve"): ("teacher_b", {"chat_id": "chat_a.id"}, None, {"user_ids": ["student_b.id"]}, None),
    ("POST", "/chats/{chat_id}/join-requests/{requester_id}/decline"): ("teacher_b", {"chat_id": "chat_a.id", "requester_id": "student_a.id"}, None, None, None),
    ("POST", "/chats/{chat_id}/invite-code"): ("teacher_b", {"chat_id": "chat_a.id"}, None, None, None),
    ("GET", "/chats/{chat_id}/members"): ("teacher_b", {"chat_id": "chat_a.id"}, None, None, None),
    ("GET", "/chats/{chat_id}/leaderboard"): ("teacher_b", {"chat_id": "chat_a.id"}, None, None, None),
    ("POST", "/chats/{chat_id}/quiz/start"): ("teacher_b", {"chat_id": "chat_a.id"}, None, {"material_id": "material_a.id"}, None),
    ("POST", "/chats/{chat_id}/materials"): ("teacher_b", {"chat_id": "chat_a.id"}, None, None, {"kind": "link", "location": "https://x.az"}),
    ("GET", "/chats/{chat_id}/materials"): ("teacher_b", {"chat_id": "chat_a.id"}, None, None, None),
    ("GET", "/live/question-sets/{question_set_id}"): ("teacher_b", {"question_set_id": "qs_a.id"}, None, None, None),
    ("GET", "/live/question-sets/{question_set_id}/questions"): ("teacher_b", {"question_set_id": "qs_a.id"}, None, None, None),
    ("GET", "/live/question-sets/{question_set_id}/quality"): ("teacher_b", {"question_set_id": "qs_a.id"}, None, None, None),
    ("PATCH", "/live/questions/{question_id}"): ("teacher_b", {"question_id": "question_a.id"}, None,
        {"question": "Oğurlandı?", "options": ["1", "2", "3", "4", "5"], "correct_index": 1, "explanation": "x"}, None),
    ("DELETE", "/live/questions/{question_id}"): ("teacher_b", {"question_id": "question_a.id"}, None, None, None),
    ("POST", "/live/sessions"): ("teacher_b", {}, None, {"question_set_id": "qs_a.id", "chat_id": "chat_b.id"}, None),
    ("GET", "/chats/{chat_id}/live-session"): ("teacher_b", {"chat_id": "chat_a.id"}, None, None, None),
    ("GET", "/live/sessions/{session_id}/report"): ("teacher_b", {"session_id": "finished_a.id"}, None, None, None),
    ("POST", "/homework/assignments"): ("teacher_b", {}, None, {"chat_id": "chat_b.id", "question_set_id": "qs_a.id", "due_date": "2099-01-01"}, None),
    ("GET", "/homework/assignments"): ("teacher_b", {}, {"chat_id": "chat_a.id"}, None, None),
    ("GET", "/homework/assignments/{assignment_id}/report"): ("teacher_b", {"assignment_id": "assignment_a.id"}, None, None, None),
    ("GET", "/history/student/{student_id}"): ("teacher_b", {"student_id": "student_a.id"}, None, None, None),
    ("POST", "/homework/assignments/{assignment_id}/start"): ("student_b", {"assignment_id": "assignment_a.id"}, None, None, None),
    ("POST", "/homework/attempts/{attempt_id}/answer"): ("student_b", {"attempt_id": "attempt_a.id"}, None, {"question_index": 0, "chosen_index": 0}, None),
    ("WS", "/ws/chat/{chat_id}"): ("student_b", {"chat_id": "chat_a.id"}, None, None, None),
    ("WS", "/ws/live/sessions/{session_id}/host"): ("teacher_b", {"session_id": "session_a.id"}, None, None, None),
    ("WS", "/ws/live/sessions/{session_id}/play"): ("student_b", {"session_id": "session_a.id"}, None, None, None),
}

# Obyekt qəbul edir, amma kurs sərhədi başqa yerdə yoxlanır — SƏBƏBİ ilə.
EXEMPT = {
    ("POST", "/auth/register"): "kurs kodu ilə kurs SEÇİLİR - test_closed_registration.py",
    ("POST", "/auth/login"): "obyektə çıxış yoxdur, yalnız öz hesabı",
    ("POST", "/admin/teachers"): "test_admin_teacher_scope.py",
    # Sahib paneli kursu ÖZÜ seçir — kurs sərhədi ona tətbiq olunmur. Qoruması
    # «sahib deyilsənsə 404»-dür: test_owner_panel.py::test_non_owner_gets_404_everywhere
    # HƏR /owner marşrutunu marşrut cədvəlindən tapıb sınayır.
    ("PATCH", "/owner/courses/{course_id}"): "sahib paneli - test_owner_panel.py",
    ("POST", "/owner/courses/{course_id}/join-code"): "sahib paneli - test_owner_panel.py",
    ("POST", "/owner/courses/{course_id}/payments"): "sahib paneli - test_owner_panel.py",
    ("POST", "/owner/courses/{course_id}/resume"): "sahib paneli - test_owner_panel.py",
    ("POST", "/owner/courses/{course_id}/suspend"): "sahib paneli - test_owner_panel.py",
    ("POST", "/owner/courses/{course_id}/teacher-invites"): "sahib paneli - test_owner_panel.py",
}


def _resolve(world, value):
    if isinstance(value, str) and "." in value and value.split(".")[0] in world:
        key, field = value.split(".", 1)
        return world[key][field]
    if isinstance(value, list):
        return [_resolve(world, v) for v in value]
    if isinstance(value, dict):
        return {k: _resolve(world, v) for k, v in value.items()}
    return value


def _id_routes():
    """Yol, sorğu və ya gövdə ilə obyekt identifikatoru qəbul edən marşrutlar."""
    found = set()
    for route in app.routes:
        if isinstance(route, APIWebSocketRoute) and "{" in route.path:
            found.add(("WS", route.path))
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods:
            if "{" in route.path:
                found.add((method, route.path))
            if any(p.name.endswith("_id") for p in route.dependant.query_params):
                found.add((method, route.path))
            for param in route.dependant.body_params:
                fields = getattr(param.field_info.annotation, "model_fields", {})
                if any(f.endswith(("_id", "_ids", "email", "code")) for f in fields):
                    found.add((method, route.path))
    return found


def test_every_id_route_has_a_cross_course_case():
    missing = sorted(_id_routes() - set(CASES) - set(EXEMPT))
    assert not missing, (
        f"Kurs sərhədi testi olmayan marşrutlar: {missing}. "
        "CASES-ə çarpaz-kurs halını əlavə et (və ya SƏBƏBİ ilə EXEMPT-ə)."
    )


def test_cases_do_not_reference_removed_routes():
    stale = sorted(set(CASES) - _id_routes())
    assert not stale, f"CASES-də artıq mövcud olmayan marşrutlar: {stale}"


@pytest.mark.parametrize("key", sorted(CASES), ids=lambda k: f"{k[0]} {k[1]}")
def test_other_course_object_is_not_found(world, key):
    method, path = key
    actor, path_params, query, body, form = CASES[key]
    url = path.format(**{k: _resolve(world, v) for k, v in path_params.items()})
    user = world[actor]
    client = world["client"]

    if method == "WS":
        token = create_token(user["id"], secret=_SECRET)
        with client.websocket_connect(f"{url}?token={token}") as ws:
            payload = ws.receive_json()
            closing = ws.receive()
        assert payload["type"] == "error"
        assert closing.get("code") == 4404, f"{path}: {payload}"
        return

    kwargs = {"headers": _auth(user)}
    if query:
        kwargs["params"] = _resolve(world, query)
    if body is not None:
        kwargs["json"] = _resolve(world, body)
    if form is not None:
        kwargs["data"] = form
    r = client.request(method, url, **kwargs)
    assert r.status_code == 404, f"{method} {path}: {r.status_code} {r.text[:200]}"


# ---- Yan təsirlər: 404-dən əlavə heç nə dəyişməməlidir ------------------


def test_question_not_modified_by_other_course(world):
    world["client"].patch(
        f"/live/questions/{world['question_a']['id']}",
        json={"question": "Oğurlandı?", "options": ["1", "2", "3", "4", "5"],
              "correct_index": 1, "explanation": "x"},
        headers=_auth(world["teacher_b"]),
    )
    assert world["question_sets"].list_questions(world["qs_a"]["id"])[0]["question"] == "Q?"


def test_question_set_list_is_course_scoped(world):
    r = world["client"].get("/live/question-sets", headers=_auth(world["teacher_b"]))
    assert [qs["id"] for qs in r.json()] == [world["qs_b"]["id"]]


def test_teacher_summary_counts_only_own_course(world):
    r = world["client"].get("/live/teacher-summary", headers=_auth(world["teacher_b"]))
    body = r.json()
    assert body["question_sets"]["total"] == 1
    assert body["last_session"] is None  # sessiyalar yalnız kurs A-da


def test_same_course_teacher_still_sees_banks(world):
    """Reqressiya qoruması: kurs daxilində müəllimlər bankları paylaşır."""
    r = world["client"].get(f"/live/question-sets/{world['qs_a']['id']}",
                            headers=_auth(world["teacher_a"]))
    assert r.status_code == 200


def test_approve_skips_requester_from_other_course(world):
    """Köhnə/əl ilə yaranmış çarpaz-kurs istəyi olsa belə təsdiq onu
    çata SALMAMALIDIR (müdafiə dərinliyi)."""
    world["join_requests"].request(world["chat_a"]["id"], world["student_b"]["id"])
    r = world["client"].post(
        f"/chats/{world['chat_a']['id']}/join-requests/approve",
        json={"user_ids": [world["student_b"]["id"]]},
        headers=_auth(world["teacher_a"]),
    )
    assert r.status_code == 200
    assert world["student_b"]["id"] not in world["chats"].list_member_ids(world["chat_a"]["id"])


def test_pending_list_hides_other_course_requesters(world):
    world["join_requests"].request(world["chat_a"]["id"], world["student_b"]["id"])
    r = world["client"].get(f"/chats/{world['chat_a']['id']}/join-requests",
                            headers=_auth(world["teacher_a"]))
    assert r.status_code == 200
    assert world["student_b"]["id"] not in [row["user_id"] for row in r.json()]


def test_friend_request_by_id_to_other_course(world):
    r = world["client"].post("/friends/requests",
                             json={"addressee_user_id": world["student_a"]["id"]},
                             headers=_auth(world["student_b"]))
    unknown = world["client"].post("/friends/requests", json={"addressee_email": "yoxdur@x.az"},
                                   headers=_auth(world["student_b"]))
    assert r.status_code == 404
    assert r.json() == unknown.json()


def test_legacy_cross_course_friendship_cannot_open_direct_chat(world):
    """Dostluq əvvəlcədən mövcud olsa belə (köhnə data) birbaşa çat yaranmır."""
    f = world["friendships"].create(world["student_b"]["id"], world["student_a"]["id"])
    world["friendships"].update_status(f["id"], "accepted")
    r = world["client"].post("/chats", json={"kind": "direct", "peer_user_id": world["student_a"]["id"]},
                             headers=_auth(world["student_b"]))
    assert r.status_code == 404


def test_live_session_with_foreign_chat(world):
    r = world["client"].post("/live/sessions",
                             json={"question_set_id": world["qs_b"]["id"], "chat_id": world["chat_a"]["id"]},
                             headers=_auth(world["teacher_b"]))
    assert r.status_code == 404


def test_homework_with_foreign_chat(world):
    r = world["client"].post("/homework/assignments",
                             json={"chat_id": world["chat_a"]["id"], "question_set_id": world["qs_b"]["id"],
                                   "due_date": "2099-01-01"},
                             headers=_auth(world["teacher_b"]))
    assert r.status_code == 404
