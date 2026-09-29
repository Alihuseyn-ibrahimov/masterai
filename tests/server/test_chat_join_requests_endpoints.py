"""Kod ilə qoşulma endpointləri — uc-uca (FastAPI `TestClient`).

Bu, Faza 1-in store qatının üstündəki İCAZƏ qatıdır. Əsas suallar:
kim kodu görür, kim təsdiqləyir, səhv kodda nə qayıdır, sürət limiti
həqiqətən bağlayırmı.

`POST /chats/{id}/join` SİLİNDİ — hazırkı təhlükəsizlik boşluğu o idi
(çat ID-ləri `AUTOINCREMENT`, yəni 1-dən saymaqla hər qrup çatına
girmək olurdu).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server.app import (
    app,
    get_chat_join_request_store,
    get_chat_store,
    get_friendship_store,
    get_join_rate_limiter,
    get_token_secret,
    get_user_store,
)
from server.chat_join_request_store import ChatJoinRequestStore
from server.chat_store import ChatStore
from server.friendship_store import FriendshipStore
from server.rate_limit import RateLimiter
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock():
    return _Clock()


@pytest.fixture
def client(clock):
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    join_requests = ChatJoinRequestStore(":memory:")
    friendships = FriendshipStore(":memory:")
    # Limiter HƏR TEST ÜÇÜN TƏZƏ olmalıdır — proses-daxili sayğac
    # testlər arasında daşınsa, sonrakı testlər səbəbsiz 429 alardı.
    limiter = RateLimiter(max_attempts=5, window_seconds=60, clock=clock)
    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_chat_store] = lambda: chats
    app.dependency_overrides[get_chat_join_request_store] = lambda: join_requests
    app.dependency_overrides[get_friendship_store] = lambda: friendships
    app.dependency_overrides[get_join_rate_limiter] = lambda: limiter
    app.dependency_overrides[get_token_secret] = lambda: _SECRET
    yield TestClient(app)
    app.dependency_overrides.clear()



def _default_course_code() -> str:
    """Qeydiyyat qapalıdır (kurs kodu məcburi) — bu testlər mövcud
    kurs #1-ə qeydiyyatdan keçir. Store testin override-ındadır."""
    return app.dependency_overrides[get_user_store]().courses.get(1)["join_code"]

def _register(client, email="ali@example.com", name="Əli"):
    return client.post(
        "/auth/register",
        json={"email": email, "password": "Parol1234", "display_name": name,
              "course_code": _default_course_code()},
    ).json()


def _headers(auth: dict) -> dict:
    return {"Authorization": f"Bearer {auth['token']}"}


def _create_chat(client, auth, name="11-A") -> dict:
    return client.post(
        "/chats", json={"kind": "group", "name": name}, headers=_headers(auth)
    ).json()


class TestOldJoinEndpointIsGone:
    def test_joining_by_chat_id_is_no_longer_possible(self, client):
        """BU TESTİN SƏBƏBİ: çat ID-ləri ARDICIL idi. Endpoint qalsa,
        1-dən saymaqla bütün qrup çatlarına girmək olar.

        Status 404-dür, çünki marşrut ÜMUMİYYƏTLƏ yoxdur. Status tək
        başına zəif dəlildir (tapılmayan çat da 404 verir) — ona görə
        əsas iddia ÜZVLÜYÜN yaranmamasıdır.
        """
        ali = _register(client)
        vali = _register(client, email="vali@example.com", name="Vəli")
        chat = _create_chat(client, ali)

        r = client.post(f"/chats/{chat['id']}/join", headers=_headers(vali))

        assert r.status_code == 404, "köhnə qoşulma yolu hələ də açıqdır"
        assert client.get("/chats", headers=_headers(vali)).json() == []


class TestInviteCodeVisibility:
    def test_creator_sees_the_code(self, client):
        ali = _register(client)
        chat = _create_chat(client, ali)
        assert chat["invite_code"]
        assert len(chat["invite_code"]) == 6

    def test_member_who_is_not_the_creator_does_not_see_the_code(self, client):
        """Kodu paylaşmaq müəllimin qərarıdır. Üzvə göstərsək, hər
        tələbə onu kənara ötürə bilər — təsdiq yenə lazımdır, amma
        müəllim bundan xəbərsiz qalar."""
        ali = _register(client)
        vali = _register(client, email="vali@example.com", name="Vəli")
        chat = _create_chat(client, ali)
        code = chat["invite_code"]
        client.post("/chats/join-requests", json={"code": code}, headers=_headers(vali))
        client.post(
            f"/chats/{chat['id']}/join-requests/approve",
            json={"user_ids": [vali["user"]["id"]]},
            headers=_headers(ali),
        )

        vali_chats = client.get("/chats", headers=_headers(vali)).json()

        assert [c["id"] for c in vali_chats] == [chat["id"]]
        assert vali_chats[0]["invite_code"] is None

    def test_direct_chat_has_no_code(self, client):
        ali = _register(client)
        vali = _register(client, email="vali@example.com", name="Vəli")
        req = client.post(
            "/friends/requests",
            json={"addressee_user_id": vali["user"]["id"]},
            headers=_headers(ali),
        ).json()
        client.post(f"/friends/requests/{req['id']}/accept", headers=_headers(vali))

        chat = client.post(
            "/chats",
            json={"kind": "direct", "peer_user_id": vali["user"]["id"]},
            headers=_headers(ali),
        ).json()

        assert chat["invite_code"] is None


class TestRequestingByCode:
    def test_valid_code_creates_a_pending_request(self, client):
        ali = _register(client)
        vali = _register(client, email="vali@example.com", name="Vəli")
        chat = _create_chat(client, ali)

        r = client.post(
            "/chats/join-requests",
            json={"code": chat["invite_code"]},
            headers=_headers(vali),
        )

        assert r.status_code == 201
        assert r.json()["status"] == "gözləyir"
        assert r.json()["chat_name"] == "11-A"

    def test_response_does_not_leak_the_chat_id(self, client):
        """Cavabda ID olsa, kod ilə ID arasında xəritə qurmaq olar.

        İlk versiyada burada çat ID-sinin ADIN İÇİNDƏ olmadığını da
        yoxlayırdım — mənasız idi və sındı: çat 1 nömrəlidir, adı isə
        «11-A». Ad istifadəçinin yazdığı sərbəst mətndir, onunla ID
        sızması ölçülmür. Ölçülən budur: cavabda ID daşıyan AÇAR yoxdur.
        """
        ali = _register(client)
        vali = _register(client, email="vali@example.com", name="Vəli")
        chat = _create_chat(client, ali)

        body = client.post(
            "/chats/join-requests",
            json={"code": chat["invite_code"]},
            headers=_headers(vali),
        ).json()

        assert set(body) == {"chat_name", "status"}

    def test_request_does_not_make_the_user_a_member_yet(self, client):
        """ƏSAS QAYDA: istək üzvlük DEYİL."""
        ali = _register(client)
        vali = _register(client, email="vali@example.com", name="Vəli")
        chat = _create_chat(client, ali)

        client.post(
            "/chats/join-requests",
            json={"code": chat["invite_code"]},
            headers=_headers(vali),
        )

        assert client.get("/chats", headers=_headers(vali)).json() == []

    def test_code_is_accepted_in_display_form(self, client):
        """Müəllim ekranda `K7M-3QX` görür və tələbə onu olduğu kimi
        yazır — defis səhv sayılmamalıdır."""
        ali = _register(client)
        vali = _register(client, email="vali@example.com", name="Vəli")
        chat = _create_chat(client, ali)
        code = chat["invite_code"]

        r = client.post(
            "/chats/join-requests",
            json={"code": f"{code[:3]}-{code[3:].lower()}"},
            headers=_headers(vali),
        )

        assert r.status_code == 201

    def test_unknown_code_returns_404(self, client):
        auth = _register(client)
        r = client.post(
            "/chats/join-requests", json={"code": "ZZZZZZ"}, headers=_headers(auth)
        )
        assert r.status_code == 404

    def test_empty_code_returns_404_not_a_random_chat(self, client):
        ali = _register(client)
        _create_chat(client, ali)
        r = client.post("/chats/join-requests", json={"code": ""}, headers=_headers(ali))
        assert r.status_code == 404

    def test_existing_member_gets_a_clear_answer(self, client):
        """Tələbə onsuz da üzv olduğu çatın kodunu yaza bilər — «istək
        göndərildi» yalançı olardı, gözləyənlər siyahısına da düşməlidir
        deyil."""
        ali = _register(client)
        chat = _create_chat(client, ali)

        r = client.post(
            "/chats/join-requests",
            json={"code": chat["invite_code"]},
            headers=_headers(ali),
        )

        assert r.status_code == 409
        pending = client.get(
            f"/chats/{chat['id']}/join-requests", headers=_headers(ali)
        ).json()
        assert pending == []

    def test_login_is_required(self, client):
        ali = _register(client)
        chat = _create_chat(client, ali)
        r = client.post("/chats/join-requests", json={"code": chat["invite_code"]})
        assert r.status_code in (401, 403)


class TestRateLimit:
    def test_sixth_attempt_in_a_minute_is_blocked(self, client):
        auth = _register(client)
        for _ in range(5):
            assert (
                client.post(
                    "/chats/join-requests", json={"code": "ZZZZZZ"}, headers=_headers(auth)
                ).status_code
                == 404
            )

        r = client.post(
            "/chats/join-requests", json={"code": "ZZZZZZ"}, headers=_headers(auth)
        )

        assert r.status_code == 429

    def test_the_limit_lifts_after_the_window(self, client, clock):
        auth = _register(client)
        for _ in range(6):
            client.post(
                "/chats/join-requests", json={"code": "ZZZZZZ"}, headers=_headers(auth)
            )

        clock.advance(61)

        r = client.post(
            "/chats/join-requests", json={"code": "ZZZZZZ"}, headers=_headers(auth)
        )
        assert r.status_code == 404, "pəncərə keçdi, amma hələ bloklanır"

    def test_one_user_cannot_block_another(self, client):
        """Limit istifadəçi üzrədir — biri limitə çatsa, digəri
        qoşulmağa davam edə bilməlidir."""
        ali = _register(client)
        vali = _register(client, email="vali@example.com", name="Vəli")
        chat = _create_chat(client, ali)
        for _ in range(6):
            client.post(
                "/chats/join-requests", json={"code": "ZZZZZZ"}, headers=_headers(vali)
            )

        ucuncu = _register(client, email="uc@example.com", name="Üçüncü")
        r = client.post(
            "/chats/join-requests",
            json={"code": chat["invite_code"]},
            headers=_headers(ucuncu),
        )
        assert r.status_code == 201


class TestPendingList:
    def test_creator_sees_pending_requests_with_names(self, client):
        ali = _register(client)
        vali = _register(client, email="vali@example.com", name="Vəli")
        chat = _create_chat(client, ali)
        client.post(
            "/chats/join-requests",
            json={"code": chat["invite_code"]},
            headers=_headers(vali),
        )

        rows = client.get(
            f"/chats/{chat['id']}/join-requests", headers=_headers(ali)
        ).json()

        assert len(rows) == 1
        assert rows[0]["user_id"] == vali["user"]["id"]
        assert rows[0]["display_name"] == "Vəli", "müəllim ID yox, AD görməlidir"
        assert rows[0]["created_at"]

    def test_a_plain_member_cannot_see_the_requests(self, client):
        """Üzv olmaq təsdiq səlahiyyəti VERMİR."""
        ali = _register(client)
        vali = _register(client, email="vali@example.com", name="Vəli")
        chat = _create_chat(client, ali)
        client.post(
            "/chats/join-requests",
            json={"code": chat["invite_code"]},
            headers=_headers(vali),
        )
        client.post(
            f"/chats/{chat['id']}/join-requests/approve",
            json={"user_ids": [vali["user"]["id"]]},
            headers=_headers(ali),
        )

        r = client.get(f"/chats/{chat['id']}/join-requests", headers=_headers(vali))

        assert r.status_code == 403

    def test_a_stranger_cannot_see_the_requests(self, client):
        ali = _register(client)
        kenar = _register(client, email="kenar@example.com", name="Kənar")
        chat = _create_chat(client, ali)
        r = client.get(f"/chats/{chat['id']}/join-requests", headers=_headers(kenar))
        assert r.status_code == 403

    def test_unknown_chat_returns_404(self, client):
        ali = _register(client)
        r = client.get("/chats/9999/join-requests", headers=_headers(ali))
        assert r.status_code == 404


class TestApproval:
    def test_approval_adds_the_member(self, client):
        ali = _register(client)
        vali = _register(client, email="vali@example.com", name="Vəli")
        chat = _create_chat(client, ali)
        client.post(
            "/chats/join-requests",
            json={"code": chat["invite_code"]},
            headers=_headers(vali),
        )

        r = client.post(
            f"/chats/{chat['id']}/join-requests/approve",
            json={"user_ids": [vali["user"]["id"]]},
            headers=_headers(ali),
        )

        assert r.status_code == 200
        assert r.json()["approved_user_ids"] == [vali["user"]["id"]]
        assert [c["id"] for c in client.get("/chats", headers=_headers(vali)).json()] == [
            chat["id"]
        ]

    def test_bulk_approval_adds_everyone(self, client):
        """İlk dərs ssenarisi: müəllim «Hamısını təsdiqlə» basır."""
        ali = _register(client)
        chat = _create_chat(client, ali)
        students = [
            _register(client, email=f"t{i}@example.com", name=f"Tələbə {i}")
            for i in range(3)
        ]
        for student in students:
            client.post(
                "/chats/join-requests",
                json={"code": chat["invite_code"]},
                headers=_headers(student),
            )

        r = client.post(
            f"/chats/{chat['id']}/join-requests/approve",
            json={"user_ids": [s["user"]["id"] for s in students]},
            headers=_headers(ali),
        )

        assert sorted(r.json()["approved_user_ids"]) == sorted(
            s["user"]["id"] for s in students
        )
        members = client.get(f"/chats/{chat['id']}/members", headers=_headers(ali)).json()
        assert len(members) == 4  # üç tələbə + müəllim

    def test_only_the_creator_can_approve(self, client):
        ali = _register(client)
        vali = _register(client, email="vali@example.com", name="Vəli")
        kenar = _register(client, email="kenar@example.com", name="Kənar")
        chat = _create_chat(client, ali)
        client.post(
            "/chats/join-requests",
            json={"code": chat["invite_code"]},
            headers=_headers(vali),
        )

        r = client.post(
            f"/chats/{chat['id']}/join-requests/approve",
            json={"user_ids": [vali["user"]["id"]]},
            headers=_headers(kenar),
        )

        assert r.status_code == 403
        assert client.get("/chats", headers=_headers(vali)).json() == []

    def test_approving_without_a_request_does_not_add_a_member(self, client):
        """Ən vacib mühafizə: `user_ids` çağırandan gəlir. Gözləyən
        istəyi olmayan adamı bura yazmaqla çata salmaq MÜMKÜN
        OLMAMALIDIR."""
        ali = _register(client)
        kenar = _register(client, email="kenar@example.com", name="Kənar")
        chat = _create_chat(client, ali)

        r = client.post(
            f"/chats/{chat['id']}/join-requests/approve",
            json={"user_ids": [kenar["user"]["id"]]},
            headers=_headers(ali),
        )

        assert r.json()["approved_user_ids"] == []
        assert client.get("/chats", headers=_headers(kenar)).json() == []

    def test_empty_user_ids_is_accepted(self, client):
        ali = _register(client)
        chat = _create_chat(client, ali)
        r = client.post(
            f"/chats/{chat['id']}/join-requests/approve",
            json={"user_ids": []},
            headers=_headers(ali),
        )
        assert r.status_code == 200


class TestDecline:
    def test_declining_removes_it_from_the_pending_list(self, client):
        ali = _register(client)
        vali = _register(client, email="vali@example.com", name="Vəli")
        chat = _create_chat(client, ali)
        client.post(
            "/chats/join-requests",
            json={"code": chat["invite_code"]},
            headers=_headers(vali),
        )

        r = client.post(
            f"/chats/{chat['id']}/join-requests/{vali['user']['id']}/decline",
            headers=_headers(ali),
        )

        assert r.status_code == 200
        assert client.get(
            f"/chats/{chat['id']}/join-requests", headers=_headers(ali)
        ).json() == []
        assert client.get("/chats", headers=_headers(vali)).json() == []

    def test_declined_student_can_ask_again(self, client):
        """Rədd BLOKLAMA deyil — müəllim səhvən rədd edə bilər."""
        ali = _register(client)
        vali = _register(client, email="vali@example.com", name="Vəli")
        chat = _create_chat(client, ali)
        client.post(
            "/chats/join-requests",
            json={"code": chat["invite_code"]},
            headers=_headers(vali),
        )
        client.post(
            f"/chats/{chat['id']}/join-requests/{vali['user']['id']}/decline",
            headers=_headers(ali),
        )

        r = client.post(
            "/chats/join-requests",
            json={"code": chat["invite_code"]},
            headers=_headers(vali),
        )

        assert r.status_code == 201
        rows = client.get(
            f"/chats/{chat['id']}/join-requests", headers=_headers(ali)
        ).json()
        assert [row["user_id"] for row in rows] == [vali["user"]["id"]]

    def test_only_the_creator_can_decline(self, client):
        ali = _register(client)
        vali = _register(client, email="vali@example.com", name="Vəli")
        kenar = _register(client, email="kenar@example.com", name="Kənar")
        chat = _create_chat(client, ali)
        client.post(
            "/chats/join-requests",
            json={"code": chat["invite_code"]},
            headers=_headers(vali),
        )

        r = client.post(
            f"/chats/{chat['id']}/join-requests/{vali['user']['id']}/decline",
            headers=_headers(kenar),
        )

        assert r.status_code == 403

    def test_declining_a_missing_request_returns_404(self, client):
        ali = _register(client)
        kenar = _register(client, email="kenar@example.com", name="Kənar")
        chat = _create_chat(client, ali)
        r = client.post(
            f"/chats/{chat['id']}/join-requests/{kenar['user']['id']}/decline",
            headers=_headers(ali),
        )
        assert r.status_code == 404


class TestRegeneratingTheCode:
    def test_creator_can_rotate_the_code(self, client):
        """Kod sinifdən kənara çıxsa (şəkil, ekran paylaşımı) müəllim
        onu yeniləyir."""
        ali = _register(client)
        chat = _create_chat(client, ali)
        old = chat["invite_code"]

        r = client.post(f"/chats/{chat['id']}/invite-code", headers=_headers(ali))

        assert r.status_code == 200
        new = r.json()["invite_code"]
        assert new != old

    def test_the_old_code_stops_working_immediately(self, client):
        ali = _register(client)
        vali = _register(client, email="vali@example.com", name="Vəli")
        chat = _create_chat(client, ali)
        old = chat["invite_code"]
        client.post(f"/chats/{chat['id']}/invite-code", headers=_headers(ali))

        r = client.post(
            "/chats/join-requests", json={"code": old}, headers=_headers(vali)
        )

        assert r.status_code == 404

    def test_only_the_creator_can_rotate(self, client):
        ali = _register(client)
        vali = _register(client, email="vali@example.com", name="Vəli")
        chat = _create_chat(client, ali)
        client.post(
            "/chats/join-requests",
            json={"code": chat["invite_code"]},
            headers=_headers(vali),
        )
        client.post(
            f"/chats/{chat['id']}/join-requests/approve",
            json={"user_ids": [vali["user"]["id"]]},
            headers=_headers(ali),
        )

        r = client.post(f"/chats/{chat['id']}/invite-code", headers=_headers(vali))

        assert r.status_code == 403
