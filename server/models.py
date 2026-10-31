"""FastAPI request/response Pydantic modelləri (auth + çat)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator

from pipeline.models import Difficulty
from pipeline.summary import LessonSummary


class RegisterRequest(BaseModel):
    email: EmailStr
    # 8 simvol minimum — ümumi təhlükəsizlik gözləntisi (dildostu naxışı).
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=100)
    # Qapalı qeydiyyat (spec 2026-09-29 §4): tələbə kurs kodu ilə, müəllim
    # sahibin birdəfəlik dəvəti ilə. DƏQİQ BİRİ məcburidir.
    course_code: str | None = Field(default=None, max_length=32)
    invite_token: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def _exactly_one_entry(self) -> "RegisterRequest":
        has_code = bool(self.course_code and self.course_code.strip())
        has_invite = bool(self.invite_token and self.invite_token.strip())
        if has_code == has_invite:
            raise ValueError("Kurs kodu tələb olunur")
        return self


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
    # Frontend sahib paneli linkini bununla göstərir. QORUMA serverdədir
    # (`get_platform_owner`) — bu bayraq yalnız görünüş üçündür.
    is_platform_owner: bool = False


class MeCourseInfo(BaseModel):
    """Cari istifadəçinin kursu — müəllim banneri (bitməyə ≤5 gün) üçün.
    `days_left` `owner` kursu üçün `None`-dur (müddət yoxdur)."""

    name: str
    status: str
    days_left: int | None
    is_open: bool
    profile: str


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
    # Dəvət kodu YALNIZ çatı yaradana göstərilir (bax `app.py`,
    # `_chat_info_for`). Adi üzvə `None` qayıdır — kodu paylaşmaq
    # müəllimin qərarıdır, üzv onu kənara ötürə bilməməlidir.
    # Şəxsi çatda kod anlayışı yoxdur, ona görə orada da `None`.
    invite_code: str | None = None


class JoinByCodeRequest(BaseModel):
    """Kod ilə qoşulma istəyi. Uzunluq sərhədi qəsdən genişdir —
    normallaşdırma defis/boşluq da qəbul edir (`K7M-3QX`)."""

    code: str = Field(default="", max_length=32)


class JoinRequestResult(BaseModel):
    """İstək göndərildikdən sonra tələbəyə qayıdan cavab.

    `chat_id` QƏSDƏN YOXDUR: cavabda olsa, kod ilə ID arasında xəritə
    qurmaq və hansı ID-lərin «canlı» olduğunu öyrənmək olardı.
    """

    chat_name: str | None
    status: str


class JoinRequestRow(BaseModel):
    """Müəllimin gözləyənlər siyahısındakı bir sətir — ID yox, AD."""

    user_id: int
    display_name: str
    created_at: str


class ApproveJoinRequestsRequest(BaseModel):
    """Toplu təsdiq — «Hamısını təsdiqlə» düyməsi bir sorğu göndərir."""

    user_ids: list[int] = Field(default_factory=list)


class ApproveJoinRequestsResult(BaseModel):
    """REAL təsdiqlənənlər — sorğuda göndərilənlər yox.

    Gözləyən istəyi olmayan `user_id` siyahıya düşmür, yəni bu
    endpoint ilə kimisə «zorla» çata salmaq mümkün deyil.
    """

    approved_user_ids: list[int]


class InviteCodeInfo(BaseModel):
    invite_code: str


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
    # Kurs profili (spec 2026-09-29 §5): `practice` hər yerdə, `reading`
    # yalnız ev tapşırığında (mətn tələbənin qarşısında olanda).
    profile: str = "exam_prep"
    bank_kind: str = "practice"
    # Müəllimin istədiyi çətinlik bölgüsü «asan/orta/çətin» faizləri ilə,
    # məs. «30/50/20». Faza 2-dən (2026-10-30) əvvəlki banklarda None.
    difficulty_mix: str | None = None


class LiveQuestionInfo(BaseModel):
    """Sual bankının BİR sualının TAM (düzgün cavab+izah daxil) məlumatı —
    yalnız müəllim redaktə ekranı üçün (bax Sual redaktə/təsdiq ekranı,
    Faza 5). Sessiya/tapşırıq zamanı oyunçulara göndərilən yük (`_question_
    payload`) BUNDAN QƏSDƏN fərqlidir — cavab sızmasın deyə."""

    id: int
    question_set_id: int
    question: str
    options: list[str]
    correct_index: int
    explanation: str
    created_at: str
    difficulty: Difficulty | None = None


class UpdateQuestionRequest(BaseModel):
    """`pipeline.models.MCQQuestion`-un eyni məhdudiyyətləri (5 variant,
    0-4 düzgün cavab indeksi) — AI-nin çıxardığı formatla uyğunluğu
    qorumaq üçün."""

    question: str
    options: list[str] = Field(min_length=5, max_length=5)
    correct_index: int = Field(ge=0, le=4)
    explanation: str
    # Göndərilməsə səviyyə dəyişmir (Faza 2-dən əvvəlki client).
    difficulty: Difficulty | None = None


class QualityFinding(BaseModel):
    """Auditin BİR şübhə əlaməti. `question_number` 1-dən başlayır və
    `GET /live/question-sets/{id}/questions` cavabının SIRASI ilə eyni
    olur; dəstin bütününə aid tapıntıda (məs. mövqe əyriliyi) `None`."""

    code: str
    # `pipeline.quality.Severity`-nin DƏYƏRİ (`yuksek`/`orta`/`asagi`),
    # enum-un özü yox — client Python enum-unu oxuya bilmir.
    severity: str
    message: str
    question_number: int | None


class QuestionSetQuality(BaseModel):
    """Sual bankının keyfiyyət auditi.

    DİQQƏT — bunun nə OLMADIĞI vacibdir: audit cavabın faktiki olaraq
    doğru olduğunu DEMİR (bax `pipeline/quality.py` modul qeydi).
    Məqsəd müəllimi əvəz etmək yox, onun vaxtını ən şübhəli suala
    yönəltməkdir."""

    question_count: int
    findings: list[QualityFinding]
    # Sual nömrələri, ən şübhəlidən başlayaraq.
    review_order: list[int]


class CreateLiveSessionRequest(BaseModel):
    question_set_id: int
    # MƏCBURİDİR: sessiya artıq bir sinfə (qrup çatına) bağlıdır.
    # DB sütunu isə nullable qalır — köhnə (PIN) sessiyalar çatsızdır
    # və tarixçədə oxunmalıdır.
    chat_id: int


class LiveSessionInfo(BaseModel):
    id: int
    question_set_id: int
    # PIN 2026-09-11-də çıxarılmış, 2026-10-30-da qayıtmışdır: hesabsız
    # tələbə PIN və ya `qosul.html?pin=...` linki ilə qonaq kimi qoşulur.
    # 09-11 - 10-30 arası yaradılmış sessiyalarda boş sətirdir.
    pin: str = ""
    status: str
    current_question_index: int
    created_at: str
    # Köhnə sessiyalarda hər ikisi `None` olur.
    chat_id: int | None = None
    created_by: int | None = None


class ChatLiveSessionInfo(BaseModel):
    """Çatda görünən sessiya kartı.

    `pin` YALNIZ müəllimə qaytarılır (başqalarına `None`): sinif üzvü
    PIN-ə ehtiyac duymur, «Qoşul» düyməsi ilə hesabla girir. PIN
    müəllimin sinifdən kənar tələbələrə paylaşması üçündür.
    """

    session_id: int
    status: str
    title: str
    subject: str
    started_by: str
    # Client bunu ÖZ istifadəçi ID-si ilə müqayisə edir: sessiyanı
    # başladan müəllim konsola, qalanları oynamağa gedir. Adla
    # müqayisə kövrəkdir - eyni adlı iki müəllim ola bilər.
    started_by_user_id: int | None = None
    pin: str | None = None


class LivePinLookup(BaseModel):
    """`qosul.html` PIN-i ad soruşmazdan ƏVVƏL yoxlayır: səhv PIN-lə
    ad yazdırıb sonra rədd etmək tələbəni çaşdırar. Sessiya ID-si
    QAYTARILMIR — qonaq ona yalnız PIN ilə çatır."""

    title: str
    subject: str
    status: str


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
    # 2026-10-30-dan əvvəl saxlanmış hesabatlarda yoxdur.
    difficulty: Difficulty | None = None


class DifficultyStat(BaseModel):
    """Səviyyə üzrə nəticə: `level=None` — səviyyəsiz (köhnə) suallar."""

    level: Difficulty | None
    question_count: int
    correct_count: int
    total_answers: int


class LiveSessionReport(BaseModel):
    session_id: int
    total_questions: int
    rankings: list[LiveRankingRow]
    per_question: list[LiveQuestionReport]
    by_difficulty: list[DifficultyStat] = []


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
    # Reading bankı: sualların ÜSTÜNDƏ göstərilən mətn; digərlərində None.
    passage: str | None = None


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
    # Xalın MƏXRƏCİ. Bunsuz «8 düzgün» tələbəyə heç nə demir; həm də
    # başlamazdan əvvəl neçə sual olduğunu bilmək vaxt planlaması üçün
    # lazımdır.
    question_count: int


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


class LeaderboardRow(BaseModel):
    """Çat-üzrə liderlik lövhəsi sətri.

    2026-09-11-ə qədər YALNIZ ev tapşırığı xalları sayılırdı, çünki
    canlı sessiyalar heç bir çata bağlı deyildi. Sessiya çata
    bağlandıqdan sonra hər iki mənbə sayılır.

    Sıralama CƏMİYƏ görədir, amma komponentlər ayrıca qaytarılır —
    tələbə hansı sahədə geridə qaldığını görməlidir.
    """

    user_id: int
    display_name: str
    homework_score: int
    live_score: int
    total_score: int
    rank: int


class BadgeInfo(BaseModel):
    """Bir nailiyyət nişanının vəziyyəti — `earned=False` olanda
    `earned_at=None` (bax Faza 6 dizayn sənədi, 5 sabit `badge_type`)."""

    badge_type: str
    earned: bool
    earned_at: str | None


class CourseDeadline(BaseModel):
    """Bitmə xəbərdarlığı sətri (n8n → Telegram, spec 2026-09-29 §2)."""

    id: int
    name: str
    status: str
    days_left: int
    ends_at: str | None


class AdminStatsInfo(BaseModel):
    users_total: int
    materials_total: int
    materials_ready: int
    materials_failed: int
    questions_total: int
    quiz_sessions_total: int
    friendships_accepted: int
    # Bitməyə ≤5 gün qalan açıq kurslar və müddəti keçib bağlanmış kurslar.
    expiring_courses: list[CourseDeadline] = []
    expired_courses: list[CourseDeadline] = []


# ---- Müəllim konsolunun xülasəsi ----
# Bu məlumatların hamısı bazada onsuz da var idi; müəllim onları görmək
# üçün üç ayrı səhifəni gəzməli olurdu. Endpoint yalnız bir yerə yığır.


class QuestionSetCounts(BaseModel):
    ready: int
    processing: int
    failed: int
    total: int


class NextDueAssignment(BaseModel):
    assignment_id: int
    title: str
    due_date: str
    started: int


class HomeworkSummary(BaseModel):
    active: int
    next_due: NextDueAssignment | None


class LastSessionSummary(BaseModel):
    session_id: int
    title: str
    status: str
    participants: int
    created_at: str


class TeacherSummary(BaseModel):
    question_sets: QuestionSetCounts
    homework: HomeworkSummary
    last_session: LastSessionSummary | None


# ---- Sahib paneli (spec 2026-09-29 §3) ----------------------------------


class CourseActivity(BaseModel):
    """Son 7 gün — mövcud cədvəllərdən sayılır (yeni izləmə kodu yoxdur)."""

    sessions: int
    question_sets: int
    answers: int
    messages: int


class OwnerCourseInfo(BaseModel):
    id: int
    name: str
    profile: str
    status: str
    is_open: bool
    days_left: int | None
    trial_ends_at: str | None
    paid_until: str | None
    seat_limit: int | None
    students_active: int
    teachers: int
    upload_limit_student: int
    upload_limit_teacher: int
    join_code: str | None
    activity_7d: CourseActivity
    last_activity: str | None


class CreateCourseRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    profile: Literal["exam_prep", "english"]
    trial_days: int = Field(default=30, ge=1, le=365)
    seat_limit: int | None = Field(default=None, ge=1, le=10000)


class CoursePaymentRequest(BaseModel):
    # Bir ay = 30 gün (proqnozlaşdırıla bilən; təqvim ayı fərqli uzunluqdadır).
    months: int = Field(ge=1, le=12)


class UpdateCourseRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    seat_limit: int | None = Field(default=None, ge=1, le=10000)
    upload_limit_student: int | None = Field(default=None, ge=0, le=1000)
    upload_limit_teacher: int | None = Field(default=None, ge=0, le=1000)


class JoinCodeInfo(BaseModel):
    join_code: str


class TeacherInviteInfo(BaseModel):
    """Xam token YALNIZ bu cavabda bir dəfə görünür — bazada hash-dir."""

    token: str
    expires_at: str


class AuditLogRow(BaseModel):
    id: int
    at: str
    course_id: int | None
    course_name: str | None
    action: str
    details: str
    owner_name: str | None



class SummaryInfo(BaseModel):
    """Dərs xülasəsi (Faza 3, 2026-10-30). `content` yalnız `ready`-də var.
    Tələbəyə YALNIZ dərc olunmuş xülasə qaytarılır (bax `summary_store`)."""

    id: int
    question_set_id: int
    title: str
    subject: str
    status: str
    error: str | None = None
    content: LessonSummary | None = None
    chat_id: int | None = None
    chat_name: str | None = None
    published_at: str | None = None
    updated_at: str


class PublishSummaryRequest(BaseModel):
    chat_id: int


class LessonCreate(BaseModel):
    """Dərs cədvəli (MasterAI Classroom, gün 1). `starts_at` saat qurşağı
    ilə ISO vaxtdır; brauzer yerli vaxtı UTC-yə çevirib göndərir."""

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    starts_at: datetime
    duration_min: int = Field(default=90, ge=15, le=300)
    mode: Literal["online", "offline"] = "online"


class LessonUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    starts_at: datetime | None = None
    duration_min: int | None = Field(default=None, ge=15, le=300)
    mode: Literal["online", "offline"] | None = None
    notes: str | None = Field(default=None, max_length=100_000)


class LessonInfo(BaseModel):
    id: int
    chat_id: int
    chat_name: str | None = None
    title: str
    description: str
    starts_at: str
    duration_min: int
    mode: str
    status: str
    notes: str
    started_at: str | None = None
    ended_at: str | None = None
    attended: bool = False
    # Gün 4: dərs mətnindən yaradılan sual bankı (yalnız müəllimə lazımdır).
    question_set_id: int | None = None


class LessonAttendanceRow(BaseModel):
    user_id: int
    display_name: str
    present: bool
    method: str | None = None
    joined_at: str | None = None


class LessonVideoAccess(BaseModel):
    """LiveKit otağına giriş (gün 2). `token` qısaömürlüdür."""

    url: str
    token: str
    room: str
    identity: str
    is_host: bool


class LessonTranscriptSegment(BaseModel):
    """Bir səs hissəsi (gün 3): təxminən 5 dəqiqə."""

    seq: int
    status: Literal["processing", "ready", "failed"]
    error: str | None = None


class LessonTranscript(BaseModel):
    lesson_id: int
    segments: list[LessonTranscriptSegment]
    text: str


class LessonQuizCreate(BaseModel):
    """Dərs mətnindən sual bankı + xülasə (gün 4)."""

    subject: str
    question_count: int = Field(default=10, ge=3, le=30)
    make_summary: bool = True
