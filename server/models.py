"""FastAPI request/response Pydantic modelləri (auth + çat)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    # 8 simvol minimum — ümumi təhlükəsizlik gözləntisi (dildostu naxışı).
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserInfo(BaseModel):
    """İstifadəçiyə qaytarılan hesab məlumatı — şifrə hash-i HEÇ VAXT daxil deyil."""

    id: int
    email: str
    display_name: str
    created_at: str
    is_teacher: bool
    is_admin: bool


class AuthResponse(BaseModel):
    token: str
    user: UserInfo


class CreateChatRequest(BaseModel):
    kind: Literal["direct", "group"]
    name: str | None = Field(default=None, max_length=100)
    peer_user_id: int | None = None

    @model_validator(mode="after")
    def _validate_kind_specific_fields(self):
        if self.kind == "group" and not self.name:
            raise ValueError("Qrup çatı üçün 'name' tələb olunur")
        if self.kind == "direct" and self.peer_user_id is None:
            raise ValueError("Direct çat üçün 'peer_user_id' tələb olunur")
        return self


class ChatInfo(BaseModel):
    id: int
    kind: str
    name: str | None
    created_by: int
    created_at: str


class QuizStartRequest(BaseModel):
    material_id: int


class QuizSessionInfo(BaseModel):
    chat_id: int
    material_id: int
    question_ids: list[int]
    current_index: int
    status: str


class MaterialInfo(BaseModel):
    id: int
    chat_id: int
    uploaded_by: int
    kind: str
    location: str
    label: str | None
    status: str
    created_at: str


class SendFriendRequestRequest(BaseModel):
    addressee_email: str | None = None
    addressee_user_id: int | None = None

    @model_validator(mode="after")
    def _exactly_one_target(self):
        if (self.addressee_email is None) == (self.addressee_user_id is None):
            raise ValueError("'addressee_email' VƏ YA 'addressee_user_id' — dəqiq biri tələb olunur")
        return self


class FriendshipInfo(BaseModel):
    id: int
    requester_id: int
    addressee_id: int
    status: str
    created_at: str
    responded_at: str | None


class QuestionSetInfo(BaseModel):
    id: int
    subject: str
    title: str
    status: str
    material_kind: str
    material_location: str
    error: str | None
    question_count: int
    created_by: int
    created_at: str


class CreateLiveSessionRequest(BaseModel):
    question_set_id: int


class LiveSessionInfo(BaseModel):
    id: int
    question_set_id: int
    pin: str
    status: str
    current_question_index: int
    created_at: str


class LiveRankingRow(BaseModel):
    rank: int
    participant_id: int
    display_name: str
    score: int


class LiveQuestionReport(BaseModel):
    index: int
    question: str
    correct_index: int
    correct_count: int
    total_answers: int
    most_common_wrong_index: int | None


class LiveSessionReport(BaseModel):
    session_id: int
    total_questions: int
    rankings: list[LiveRankingRow]
    per_question: list[LiveQuestionReport]


class CreateHomeworkAssignmentRequest(BaseModel):
    chat_id: int
    question_set_id: int
    due_date: str


class HomeworkAssignmentInfo(BaseModel):
    id: int
    chat_id: int
    question_set_id: int
    due_date: str
    created_by: int
    created_at: str
    completed_count: int
    total_members: int


class HomeworkQuestionPayload(BaseModel):
    index: int
    total: int
    question: str
    options: list[str]


class HomeworkAttemptState(BaseModel):
    attempt_id: int
    status: str
    current_question_index: int
    score: int
    # `None` — cəhd artıq tamamlanıb, göstəriləcək sual yoxdur.
    question: HomeworkQuestionPayload | None


class HomeworkAnswerRequest(BaseModel):
    question_index: int
    chosen_index: int


class HomeworkAnswerResult(BaseModel):
    is_correct: bool
    correct_index: int
    explanation: str
    # `None` — bu, sonuncu sual idi, cəhd tamamlandı.
    next_question: HomeworkQuestionPayload | None


class HomeworkReportRow(BaseModel):
    student_id: int
    display_name: str
    status: Literal["gözləyir", "davam edir", "tamamlanıb"]
    score: int | None


class MyAssignmentInfo(BaseModel):
    assignment_id: int
    chat_id: int
    subject: str
    title: str
    due_date: str
    status: Literal["gözləyir", "davam edir", "tamamlanıb"]
    score: int | None


class SetTeacherRequest(BaseModel):
    """Admin-in başqa bir istifadəçini müəllim edib/etməməsi üçün
    (bax `app.py`, `POST /admin/teachers` — yalnız `is_admin`)."""

    email: str
    is_teacher: bool


class ChatMemberInfo(BaseModel):
    user_id: int
    display_name: str


class HistoryEntry(BaseModel):
    """Fərdi tələbə tarixçəsi sətri — canlı sessiya VƏ ev tapşırığı
    nəticələri eyni xronoloji siyahıda birləşdirilir (bax `app.py`,
    `_history_entries_for_student`)."""

    kind: Literal["live", "homework"]
    subject: str
    title: str
    score: int
    total_questions: int
    date: str
    chat_id: int | None = None
    session_id: int | None = None


class AdminStatsInfo(BaseModel):
    users_total: int
    materials_total: int
    materials_ready: int
    materials_failed: int
    questions_total: int
    quiz_sessions_total: int
    friendships_accepted: int
