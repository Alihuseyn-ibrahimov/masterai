import pytest
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion
from server.app import (
    app,
    get_chat_store,
    get_homework_store,
    get_question_set_store,
    get_token_secret,
    get_user_store,
)
from server.auth import create_token
from server.chat_store import ChatStore
from server.homework_store import HomeworkStore
from server.question_set_store import QuestionSetStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


@pytest.fixture
def env():
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    question_sets = QuestionSetStore(":memory:")
    homework = HomeworkStore(":memory:")

    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_chat_store] = lambda: chats
    app.dependency_overrides[get_question_set_store] = lambda: question_sets
    app.dependency_overrides[get_homework_store] = lambda: homework
    app.dependency_overrides[get_token_secret] = lambda: _SECRET

    client = TestClient(app)
    teacher = users.create("teacher@masternr1.az", "hash", "Müəllim")
    users.set_teacher(teacher["id"], True)
    teacher = users.get_by_id(teacher["id"])
    ali = users.create("ali@masternr1.az", "hash", "Əli")
    veli = users.create("veli@masternr1.az", "hash", "Vəli")
    outsider = users.create("kənar@masternr1.az", "hash", "Kənar")

    chat = chats.create(kind="group", created_by=teacher["id"], name="Sinif")
    chats.add_member(chat["id"], teacher["id"])
    chats.add_member(chat["id"], ali["id"])
    chats.add_member(chat["id"], veli["id"])

    yield {
        "client": client, "users": users, "chats": chats, "question_sets": question_sets,
        "homework": homework, "teacher": teacher, "ali": ali, "veli": veli,
        "outsider": outsider, "chat": chat,
    }
    app.dependency_overrides.clear()


def _auth(user) -> dict:
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


def _ready_question_set(env, n_questions=2):
    qs = env["question_sets"].create(
        subject="mentiq", title="A", material_kind="link",
        material_location="https://x.az", created_by=env["teacher"]["id"],
    )
    for i in range(n_questions):
        env["question_sets"].add_question(
            qs["id"],
            MCQQuestion(question=f"Sual {i}?", options=["A", "B", "C", "D", "E"], correct_index=0, explanation="izah"),
        )
    env["question_sets"].mark_ready(qs["id"])
    return qs


def _complete_homework(env, *, student_id, score, total_questions=2):
    qs = _ready_question_set(env, n_questions=total_questions)
    assignment = env["homework"].create_assignment(
        env["chat"]["id"], qs["id"], "2026-09-14", created_by=env["teacher"]["id"]
    )
    attempt = env["homework"].get_or_create_attempt(assignment["id"], student_id=student_id)
    for i in range(score):
        env["homework"].answer(attempt["id"], i, chosen_index=0, is_correct=True, total_questions=total_questions)
    for i in range(score, total_questions):
        env["homework"].answer(attempt["id"], i, chosen_index=1, is_correct=False, total_questions=total_questions)


class TestChatLeaderboard:
    def test_requires_auth(self, env):
        assert env["client"].get(f"/chats/{env['chat']['id']}/leaderboard").status_code == 401

    def test_non_member_gets_403(self, env):
        r = env["client"].get(f"/chats/{env['chat']['id']}/leaderboard", headers=_auth(env["outsider"]))
        assert r.status_code == 403

    def test_unknown_chat_returns_404(self, env):
        r = env["client"].get("/chats/999/leaderboard", headers=_auth(env["teacher"]))
        assert r.status_code == 404

    def test_includes_zero_score_members_but_not_the_teacher(self, env):
        """Müəllim 2026-09-11-dən siyahıdan ÇIXARILIR (Faza 5): tapşırığı
        təyin edən tərəfdir, tələbə ilə yarışmır. Əvvəl bu test onun da
        siyahıda olmasını gözləyirdi.

        Sıfır xallı TƏLƏBƏ isə qalır — əks halda tələbə «mən niyə
        yoxam?» sualı ilə qalardı."""
        r = env["client"].get(f"/chats/{env['chat']['id']}/leaderboard", headers=_auth(env["teacher"]))
        assert r.status_code == 200
        names = {row["display_name"] for row in r.json()}
        assert names == {"Əli", "Vəli"}
        assert all(row["total_score"] == 0 for row in r.json())

    def test_sorted_descending_by_score_with_correct_ranks(self, env):
        _complete_homework(env, student_id=env["ali"]["id"], score=2, total_questions=2)
        _complete_homework(env, student_id=env["veli"]["id"], score=1, total_questions=2)
        r = env["client"].get(f"/chats/{env['chat']['id']}/leaderboard", headers=_auth(env["teacher"]))
        rows = r.json()
        assert rows[0]["display_name"] == "Əli"
        assert rows[0]["total_score"] == 2
        assert rows[0]["rank"] == 1
        veli_row = next(row for row in rows if row["display_name"] == "Vəli")
        assert veli_row["total_score"] == 1
        assert veli_row["rank"] == 2

    def test_does_not_leak_across_chats(self, env):
        other_chat = env["chats"].create(kind="group", created_by=env["teacher"]["id"], name="Başqa")
        env["chats"].add_member(other_chat["id"], env["teacher"]["id"])
        env["chats"].add_member(other_chat["id"], env["ali"]["id"])
        _complete_homework(env, student_id=env["ali"]["id"], score=2, total_questions=2)  # env["chat"]-a təyin olunur
        r = env["client"].get(f"/chats/{other_chat['id']}/leaderboard", headers=_auth(env["teacher"]))
        assert r.status_code == 200
        ali_row = next(row for row in r.json() if row["display_name"] == "Əli")
        assert ali_row["total_score"] == 0
