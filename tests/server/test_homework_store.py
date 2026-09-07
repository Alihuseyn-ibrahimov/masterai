import pytest

from server.homework_store import AttemptAlreadyCompleted, HomeworkStore, NotCurrentQuestion


@pytest.fixture
def store(tmp_path):
    return HomeworkStore(path=str(tmp_path / "homework.db"))


class TestAssignments:
    def test_create_returns_full_record(self, store):
        a = store.create_assignment(chat_id=1, question_set_id=7, due_date="2026-09-14", created_by=1)
        assert a["chat_id"] == 1
        assert a["question_set_id"] == 7
        assert a["due_date"] == "2026-09-14"
        assert a["created_by"] == 1
        assert a["created_at"]

    def test_get_returns_none_when_missing(self, store):
        assert store.get_assignment(999) is None

    def test_list_for_chat(self, store):
        store.create_assignment(1, 7, "2026-09-14", created_by=1)
        store.create_assignment(1, 8, "2026-09-20", created_by=1)
        store.create_assignment(2, 9, "2026-09-20", created_by=1)
        rows = store.list_assignments_for_chat(1)
        assert len(rows) == 2

    def test_list_by_teacher(self, store):
        store.create_assignment(1, 7, "2026-09-14", created_by=1)
        store.create_assignment(2, 8, "2026-09-14", created_by=2)
        rows = store.list_assignments_by_teacher(1)
        assert len(rows) == 1
        assert rows[0]["created_by"] == 1


class TestAttempts:
    def test_get_or_create_makes_new_attempt(self, store):
        a = store.create_assignment(1, 7, "2026-09-14", created_by=1)
        attempt = store.get_or_create_attempt(a["id"], student_id=5)
        assert attempt["assignment_id"] == a["id"]
        assert attempt["student_id"] == 5
        assert attempt["status"] == "in_progress"
        assert attempt["current_question_index"] == 0
        assert attempt["score"] == 0
        assert attempt["completed_at"] is None

    def test_get_or_create_resumes_existing(self, store):
        a = store.create_assignment(1, 7, "2026-09-14", created_by=1)
        first = store.get_or_create_attempt(a["id"], student_id=5)
        store.answer(first["id"], question_index=0, chosen_index=1, is_correct=True, total_questions=3)
        second = store.get_or_create_attempt(a["id"], student_id=5)
        assert second["id"] == first["id"]
        assert second["current_question_index"] == 1  # fasilədən sonra davam

    def test_get_or_create_returns_completed_attempt_unchanged(self, store):
        a = store.create_assignment(1, 7, "2026-09-14", created_by=1)
        attempt = store.get_or_create_attempt(a["id"], student_id=5)
        store.answer(attempt["id"], 0, 0, True, total_questions=1)
        reattempt = store.get_or_create_attempt(a["id"], student_id=5)
        assert reattempt["status"] == "completed"
        assert reattempt["id"] == attempt["id"]

    def test_list_attempts_for_assignment(self, store):
        a = store.create_assignment(1, 7, "2026-09-14", created_by=1)
        store.get_or_create_attempt(a["id"], student_id=5)
        store.get_or_create_attempt(a["id"], student_id=6)
        rows = store.list_attempts_for_assignment(a["id"])
        assert len(rows) == 2

    def test_list_attempts_by_student_only_completed(self, store):
        a1 = store.create_assignment(1, 7, "2026-09-14", created_by=1)
        a2 = store.create_assignment(1, 8, "2026-09-20", created_by=1)
        completed = store.get_or_create_attempt(a1["id"], student_id=5)
        store.answer(completed["id"], 0, chosen_index=1, is_correct=True, total_questions=1)
        store.get_or_create_attempt(a2["id"], student_id=5)  # in_progress qalır
        rows = store.list_attempts_by_student(5)
        assert len(rows) == 1
        assert rows[0]["assignment_id"] == a1["id"]
        assert rows[0]["status"] == "completed"

    def test_list_attempts_by_student_ignores_other_students(self, store):
        a = store.create_assignment(1, 7, "2026-09-14", created_by=1)
        attempt = store.get_or_create_attempt(a["id"], student_id=6)
        store.answer(attempt["id"], 0, chosen_index=1, is_correct=True, total_questions=1)
        assert store.list_attempts_by_student(5) == []


class TestAnswer:
    def test_records_correct_answer_and_advances(self, store):
        a = store.create_assignment(1, 7, "2026-09-14", created_by=1)
        attempt = store.get_or_create_attempt(a["id"], student_id=5)
        updated = store.answer(attempt["id"], 0, chosen_index=2, is_correct=True, total_questions=3)
        assert updated["score"] == 1
        assert updated["current_question_index"] == 1
        assert updated["status"] == "in_progress"

    def test_wrong_answer_does_not_increment_score(self, store):
        a = store.create_assignment(1, 7, "2026-09-14", created_by=1)
        attempt = store.get_or_create_attempt(a["id"], student_id=5)
        updated = store.answer(attempt["id"], 0, chosen_index=2, is_correct=False, total_questions=3)
        assert updated["score"] == 0
        assert updated["current_question_index"] == 1

    def test_last_question_marks_completed(self, store):
        a = store.create_assignment(1, 7, "2026-09-14", created_by=1)
        attempt = store.get_or_create_attempt(a["id"], student_id=5)
        updated = store.answer(attempt["id"], 0, 0, True, total_questions=1)
        assert updated["status"] == "completed"
        assert updated["completed_at"] is not None

    def test_wrong_question_index_raises(self, store):
        a = store.create_assignment(1, 7, "2026-09-14", created_by=1)
        attempt = store.get_or_create_attempt(a["id"], student_id=5)
        with pytest.raises(NotCurrentQuestion):
            store.answer(attempt["id"], question_index=1, chosen_index=0, is_correct=True, total_questions=3)

    def test_repeating_same_question_index_raises_not_current(self, store):
        a = store.create_assignment(1, 7, "2026-09-14", created_by=1)
        attempt = store.get_or_create_attempt(a["id"], student_id=5)
        store.answer(attempt["id"], 0, 0, True, total_questions=3)
        # `current_question_index` artıq 1-dir — 0-ı təkrar göndərmək "köhnə sual" sayılır
        with pytest.raises(NotCurrentQuestion):
            store.answer(attempt["id"], 0, 0, True, total_questions=3)

    def test_answering_completed_attempt_raises(self, store):
        a = store.create_assignment(1, 7, "2026-09-14", created_by=1)
        attempt = store.get_or_create_attempt(a["id"], student_id=5)
        store.answer(attempt["id"], 0, 0, True, total_questions=1)
        with pytest.raises(AttemptAlreadyCompleted):
            store.answer(attempt["id"], 0, 0, True, total_questions=1)
