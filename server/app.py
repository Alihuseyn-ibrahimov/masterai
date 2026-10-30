"""MasterAI backend FastAPI tətbiqi.

Auth (/auth/register, /auth/login, /health) + əsas çat (POST/GET /chats,
POST /chats/join-requests + təsdiq axını, WS /ws/chat/{id}) + AI quiz orkestrasiyası
(POST /chats/{id}/quiz/start, WS "answer" mesaj tipi).
"""

from __future__ import annotations

import asyncio
from functools import partial
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone

import httpx

from server.log_redaction import install_redaction

logger = logging.getLogger(__name__)

# Real production-da tapılıb: `llm_ok provider=...` (INFO) heç vaxt
# jurnala düşmürdü, çünki layihədə heç bir yerdə logging konfiqurasiyası
# yox idi — Python-un root logger-i defolt olaraq WARNING-dədir, gunicorn
# da yalnız öz `gunicorn.*` logger-lərini qurur. Nəticədə hansı LLM
# provayderin cavab verdiyini jurnaldan öyrənmək MÜMKÜN DEYİLDİ (yalnız
# uğursuzluqlar görünürdü). Bu, layihədə ikinci dəfə eyni növ "səssiz
# jurnal" problemidir (bax `_process_material`-a `logger.exception`
# əlavəsi) — ona görə konfiqurasiya tətbiqin özündə, açıq şəkildə edilir.
_NOISY_LOGGERS = ("httpx", "httpcore", "urllib3", "selenium", "anthropic", "groq", "PIL")


def _configure_logging() -> None:
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        root.addHandler(handler)
    # Səviyyə handler-dən ASILI OLMAYARAQ təyin edilir: handler mövcud
    # olsa belə (gunicorn/uvicorn qura bilər) səviyyə WARNING qalarsa
    # INFO yenə itərdi.
    root.setLevel(level)
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    # Sirrləri maskala (`?token=...` jurnalda açıq görünürdü).
    # Filtr LOGGER-lərə qoşulur - səbəbi `install_redaction` sənədində.
    install_redaction()
    # Bu sətir konfiqurasiyanın ÖZÜNÜN sübutudur: real VPS-də jurnalda
    # yalnız gunicorn-un öz INFO mesajları görünürdü (o, onsuz da INFO-da
    # idi) və bizim konfiqurasiyanın işlədiyini göstərən heç nə yox idi.
    # İndi hər restart öz sübutunu jurnala yazır — formatı da bizimdir
    # (`ad mesaj`), gunicorn-un `[pid] [INFO]` formatından fərqlənir.
    logger.info("logging_configured level=%s", level)


_configure_logging()
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from pydantic import ValidationError

from pipeline.difficulty import DEFAULT_MIX, breakdown as difficulty_breakdown, validate_mix as validate_difficulty_mix
from pipeline.models import MaterialSource, MCQQuestion
from pipeline.pipeline import generate_quiz
from pipeline.quality import audit_questions
from pipeline.summary import LessonSummary, summarize_material

from .auth import InvalidToken, create_token, hash_password, token_secret, verify_password, verify_token
from .badge_store import BadgeStore
from .summary_store import SummaryStore
from .chat_join_request_store import ChatJoinRequestStore
from .chat_store import ChatStore
from .course_store import TEACHER_INVITE_TTL, UnknownProfile
from .licensing import STATUS_ACTIVE, STATUS_OWNER, STATUS_SUSPENDED, STATUS_TRIAL, course_is_open, days_left
from .connection_manager import ConnectionManager
from .friendship_store import AlreadyFriends, DuplicateFriendship, FriendshipStore
from .homework_store import AttemptAlreadyCompleted, HomeworkStore
from .homework_store import NotCurrentQuestion as HomeworkNotCurrentQuestion
from .live_connection_manager import LiveConnectionManager
from .live_session_runner import AlreadyAnswered as LiveAlreadyAnswered
from .live_session_runner import DEFAULT_SESSION_DURATION_SECONDS
from .live_session_runner import LiveSessionError
from .live_session_runner import NotCurrentQuestion as LiveNotCurrentQuestion
from .live_session_runner import SessionTimeExpired as LiveSessionTimeExpired
from .live_session_runner import compute_report as compute_live_report
from .live_session_runner import join_session as join_live_session
from .live_session_runner import record_answer as record_live_answer
from .live_session_runner import request_next as request_next_live_question
from .live_session_runner import start_session as start_live_session
from .live_session_runner import watch_session_duration as watch_live_session_duration
from .live_session_store import LiveSessionStore
from .material_store import MaterialStore
from .message_store import MessageStore
from .models import (
    DifficultyStat,
    PublishSummaryRequest,
    SummaryInfo,
    AuditLogRow,
    CourseDeadline,
    CourseActivity,
    CoursePaymentRequest,
    CreateCourseRequest,
    JoinCodeInfo,
    OwnerCourseInfo,
    TeacherInviteInfo,
    UpdateCourseRequest,
    HomeworkSummary,
    LastSessionSummary,
    MeCourseInfo,
    NextDueAssignment,
    QuestionSetCounts,
    TeacherSummary,
    AdminStatsInfo,
    ApproveJoinRequestsRequest,
    ApproveJoinRequestsResult,
    AuthResponse,
    BadgeInfo,
    ChatInfo,
    ChatLiveSessionInfo,
    ChatMemberInfo,
    CreateChatRequest,
    CreateHomeworkAssignmentRequest,
    CreateLiveSessionRequest,
    FriendshipInfo,
    HistoryEntry,
    HomeworkAnswerRequest,
    HomeworkAnswerResult,
    HomeworkAssignmentInfo,
    HomeworkAttemptState,
    HomeworkQuestionPayload,
    HomeworkReportRow,
    InviteCodeInfo,
    JoinByCodeRequest,
    JoinRequestResult,
    JoinRequestRow,
    LeaderboardRow,
    LiveQuestionInfo,
    LivePinLookup,
    LiveSessionInfo,
    LiveSessionReport,
    LoginRequest,
    MaterialInfo,
    MyAssignmentInfo,
    QualityFinding,
    QuestionSetInfo,
    QuestionSetQuality,
    QuizSessionInfo,
    QuizStartRequest,
    RegisterRequest,
    SendFriendRequestRequest,
    SetTeacherRequest,
    UpdateQuestionRequest,
    UserInfo,
)
from .question_set_store import SUBJECTS, QuestionSetStore
from .question_store import QuestionStore
from .quiz_attempt_store import QuizAttemptStore
from .quiz_runner import (
    DEFAULT_QUESTION_TIMEOUT_SECONDS,
    AlreadyAnswered,
    NotCurrentQuestion,
    QuizError,
    check_timeout,
    record_answer,
    start_quiz,
)
from .quiz_session_store import QuizAlreadyActive, QuizSessionStore
from .rate_limit import RateLimiter
from .uploads import PayloadTooLarge, save_upload
from .user_store import CourseFull, DuplicateEmail, InvalidInvite, UserStore

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
_DEFAULT_UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")

# Müəllimin material yükləyəndə təyin edə biləcəyi ümumi sual sayı aralığı
# (bax `pipeline.generate_quiz`, `target_question_count`).
_MIN_QUESTION_COUNT = 3
_MAX_QUESTION_COUNT = 30

# Sənədləşmə BAĞLIDIR: `api.` domeni hər yolu backend-ə ötürür, açıq
# `/openapi.json` isə tələbəyə bütün endpoint-lərin (sahib paneli daxil)
# hazır xəritəsini verərdi. Bax tests/server/test_api_docs_hidden.py.
app = FastAPI(title="MasterAI", docs_url=None, redoc_url=None, openapi_url=None)
# Host konsolu (`app/`-in veb build-i) brauzerdə işlədiyi üçün CORS
# tələb olunur — mobil HTTP client-i buna məruz qalmır, YALNIZ veb
# `flutter run -d chrome`/`flutter build web` üçün lazımdır (bax Faza 4
# real testində tapılan bug, `masterai/CLAUDE.md`). Auth Bearer
# header-lə aparılır (cookie/credential yoxdur), ona görə `allow_origins`
# wildcard-ı `allow_credentials=False` ilə təhlükəsizdir.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.state.user_store = UserStore(os.environ.get("USERS_DB_PATH", "users.db"))
app.state.chat_store = ChatStore(os.environ.get("CHATS_DB_PATH", "chats.db"))
app.state.chat_join_request_store = ChatJoinRequestStore(
    os.environ.get("CHAT_JOIN_REQUESTS_DB_PATH", "chat_join_requests.db")
)
# Dəvət kodu təxminini bağlayan sayğac. Proses-daxilidir — servis
# QƏSDƏN tək worker-lə işləyir (bax `deploy/masterai.service`, `-w 1`).
app.state.join_rate_limiter = RateLimiter()
# Qeydiyyat: IP üzrə dəqiqədə 5 SƏHV kod/dəvət (uğurlu qeydiyyat sayılmır).
app.state.register_rate_limiter = RateLimiter()
# Giriş: (e-poçt, IP) üzrə 15 dəqiqədə 10 SƏHV cəhd (spec §4.2).
LOGIN_MAX_FAILURES = 10
LOGIN_WINDOW_SECONDS = 15 * 60
app.state.login_rate_limiter = RateLimiter(LOGIN_MAX_FAILURES, LOGIN_WINDOW_SECONDS)
# PIN: IP üzrə dəqiqədə 10 SƏHV PIN. 6 rəqəm = 1 milyon variant; limitsiz
# halda skript aktiv sessiyanı saniyələrlə tapardı.
PIN_MAX_FAILURES = 10
app.state.pin_rate_limiter = RateLimiter(PIN_MAX_FAILURES, 60)
app.state.message_store = MessageStore(os.environ.get("MESSAGES_DB_PATH", "messages.db"))
app.state.connection_manager = ConnectionManager()
app.state.material_store = MaterialStore(os.environ.get("MATERIALS_DB_PATH", "materials.db"))
app.state.question_store = QuestionStore(os.environ.get("QUESTIONS_DB_PATH", "questions.db"))
app.state.quiz_session_store = QuizSessionStore(os.environ.get("QUIZ_SESSIONS_DB_PATH", "quiz_sessions.db"))
app.state.quiz_attempt_store = QuizAttemptStore(os.environ.get("QUIZ_ATTEMPTS_DB_PATH", "quiz_attempts.db"))
app.state.friendship_store = FriendshipStore(os.environ.get("FRIENDSHIPS_DB_PATH", "friendships.db"))
app.state.question_set_store = QuestionSetStore(os.environ.get("QUESTION_SETS_DB_PATH", "question_sets.db"))
app.state.live_session_store = LiveSessionStore(os.environ.get("LIVE_SESSIONS_DB_PATH", "live_sessions.db"))
app.state.live_connection_manager = LiveConnectionManager()
app.state.homework_store = HomeworkStore(os.environ.get("HOMEWORK_DB_PATH", "homework.db"))
app.state.badge_store = BadgeStore(os.environ.get("BADGES_DB_PATH", "badges.db"))
app.state.summary_store = SummaryStore(os.environ.get("SUMMARIES_DB_PATH", "summaries.db"))
# Yarımçıq emallar: fon task-ları proses-daxilidir, servis restart olanda
# ölürlər və status əbədi `processing` qalırdı (produksiyada 3 həftə
# «Hazırlanır» göstərən iki bank tapıldı). Bu, YALNIZ tək worker-lə
# düzgündür (`-w 1`, bax deploy/masterai.service) - başqa worker-in
# davam edən emalını «ölü» saymaq olardı.
_interrupted_banks = app.state.question_set_store.fail_interrupted(
    "Server yenidən başladığı üçün emal yarımçıq qaldı. Materialı yenidən yükləyin."
)
_interrupted_materials = app.state.material_store.fail_interrupted()
app.state.summary_store.fail_interrupted(
    "Server yenidən başladığı üçün xülasə yarımçıq qaldı. Yenidən hazırlayın."
)
if _interrupted_banks or _interrupted_materials:
    logger.warning(
        "Yarımçıq emallar uğursuz kimi işarələndi: bank=%s material=%s",
        _interrupted_banks, _interrupted_materials,
    )
# chat_id -> planlaşdırılmış timeout task-ı (strong reference — Python-un
# arayışsız task-ı vaxtından əvvəl çöp yığmaması üçün).
app.state.active_quiz_timeouts = {}
# material_id -> planlaşdırılmış fon emalı task-ı (eyni naxış).
app.state.active_material_tasks = {}
# question_set_id -> planlaşdırılmış fon emalı task-ı (eyni naxış).
app.state.active_question_set_tasks = {}
# summary_id -> xülasə emalı task-ı (eyni naxış).
app.state.active_summary_tasks = {}
# live_session_id -> planlaşdırılmış timeout task-ı (eyni naxış).
app.state.active_live_timeouts = {}


def get_user_store() -> UserStore:
    """İstifadəçi hesabları store-u (testdə `:memory:` ilə override olunur)."""
    return app.state.user_store


def get_chat_store() -> ChatStore:
    """Çat store-u (testdə `:memory:` ilə override olunur)."""
    return app.state.chat_store


def get_chat_join_request_store() -> ChatJoinRequestStore:
    """Qoşulma istəkləri store-u (testdə `:memory:` ilə override olunur)."""
    return app.state.chat_join_request_store


def get_login_rate_limiter() -> RateLimiter:
    """Giriş sürət limiti (bax `get_join_rate_limiter`)."""
    return app.state.login_rate_limiter


def get_register_rate_limiter() -> RateLimiter:
    """Qeydiyyat kodu/dəvəti üçün sürət limiti (bax `get_join_rate_limiter`)."""
    return app.state.register_rate_limiter


def _client_ip(request: Request) -> str:
    """Real müştəri IP-si. Backend yalnız 127.0.0.1-də dinləyir və
    nginx `X-Real-IP`-ni ÖZÜ yazır (bax `deploy/nginx-masterai.conf`) —
    ona görə başlığa etibar etmək təhlükəsizdir; kənardan birbaşa
    backend-ə çatmaq mümkün deyil."""
    forwarded = request.headers.get("x-real-ip")
    if forwarded:
        return forwarded.strip()
    return request.client.host if request.client else "naməlum"


def get_pin_rate_limiter() -> RateLimiter:
    """PIN təxmini üçün sürət limiti (bax `get_join_rate_limiter`)."""
    return app.state.pin_rate_limiter


def get_join_rate_limiter() -> RateLimiter:
    """Kod ilə qoşulma sürət limiti.

    ASILILIQ KİMİ VERİLİR ki, test onu təzə nüsxə ilə əvəz edə
    bilsin — sayğac proses-daxili olduğu üçün testlər arasında
    daşınsa, sonrakı testlər səbəbsiz 429 alardı.
    """
    return app.state.join_rate_limiter


def get_message_store() -> MessageStore:
    """Mesaj store-u (testdə `:memory:` ilə override olunur)."""
    return app.state.message_store


def get_connection_manager() -> ConnectionManager:
    """WebSocket reyestri (testdə təzə instansla override olunur)."""
    return app.state.connection_manager


def get_material_store() -> MaterialStore:
    """Material store-u (testdə `:memory:` ilə override olunur)."""
    return app.state.material_store


def get_question_store() -> QuestionStore:
    """Sual store-u (testdə `:memory:` ilə override olunur)."""
    return app.state.question_store


def get_quiz_session_store() -> QuizSessionStore:
    """Quiz sessiya store-u (testdə `:memory:` ilə override olunur)."""
    return app.state.quiz_session_store


def get_quiz_attempt_store() -> QuizAttemptStore:
    """Quiz cavab store-u (testdə `:memory:` ilə override olunur)."""
    return app.state.quiz_attempt_store


def get_friendship_store() -> FriendshipStore:
    """Dostluq store-u (testdə `:memory:` ilə override olunur)."""
    return app.state.friendship_store


def get_question_set_store() -> QuestionSetStore:
    """Canlı sessiya sual bankı store-u (testdə `:memory:` ilə override olunur)."""
    return app.state.question_set_store


def get_live_session_store() -> LiveSessionStore:
    """Canlı sessiya store-u (testdə `:memory:` ilə override olunur)."""
    return app.state.live_session_store


def get_live_connection_manager() -> LiveConnectionManager:
    """Canlı sessiya WebSocket reyestri (testdə təzə instansla override olunur)."""
    return app.state.live_connection_manager


def get_homework_store() -> HomeworkStore:
    """Ev təkrarı rejimi store-u (testdə `:memory:` ilə override olunur)."""
    return app.state.homework_store


def get_badge_store() -> BadgeStore:
    """Nailiyyət nişanları store-u (testdə `:memory:` ilə override olunur)."""
    return app.state.badge_store


def get_summary_store() -> SummaryStore:
    """Dərs xülasələri store-u (testdə `:memory:` ilə override olunur)."""
    return app.state.summary_store


def get_summarizer():
    """Material→xülasə funksiyası (testdə fake funksiya ilə override olunur)."""
    return summarize_material


def get_material_generator():
    """Material→sual pipeline funksiyası (testdə fake funksiya ilə override olunur)."""
    return generate_quiz


def get_upload_dir() -> str:
    """Yüklənən faylların saxlanacağı qovluq (testdə `tmp_path` ilə override olunur)."""
    return os.environ.get("MATERIAL_UPLOAD_DIR", _DEFAULT_UPLOAD_DIR)


def get_token_secret() -> str:
    """JWT imzalama açarı (testdə sabit açarla override olunur)."""
    return token_secret()


_UNAUTHORIZED = HTTPException(
    status_code=401,
    detail="Giriş tələb olunur",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    authorization: str | None = Header(default=None),
    store: UserStore = Depends(get_user_store),
    secret: str = Depends(get_token_secret),
) -> dict:
    """`Authorization: Bearer <token>` başlığından cari istifadəçini tapır."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _UNAUTHORIZED
    token = authorization[7:].strip()
    try:
        user_id = verify_token(token, secret=secret)
    except InvalidToken:
        raise _UNAUTHORIZED
    user = store.get_by_id(user_id)
    if user is None:
        raise _UNAUTHORIZED
    _enforce_access(user, store)
    return user


# ---- Lisenziya qapısı (spec 2026-09-29 §2) ---------------------------------

LICENSE_CLOSED_DETAIL = (
    "Kursunuzun abunəsi bitib. Davam etmək üçün kurs rəhbərliyi ilə əlaqə saxlayın."
)
# HTTP 402 «Payment Required» — client bunu 401-dən (yenidən giriş) və
# 403-dən (icazə yoxdur) ayırıb «abunə bitib» ekranını göstərir.
_LICENSE_CLOSED = HTTPException(status_code=402, detail=LICENSE_CLOSED_DETAIL)
WS_CODE_LICENSE_CLOSED = 4402


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _access_problem(user: dict, users: UserStore) -> int | None:
    """İstifadəçi sistemə buraxılmırsa səbəb kodu (401/402), buraxılırsa None.

    Lisenziya HƏR SORĞUDA bazadan oxunur, JWT-yə yazılmır: dayandırma
    dərhal təsir edir və 90 günlük token problem olmur. Platforma sahibi
    kurs qapısından azaddır (öz paneli bağlı kursda da işləməlidir), amma
    `is_active` ondan da yoxlanır.
    """
    if not user["is_active"]:
        return 401
    if user["is_platform_owner"]:
        return None
    if not course_is_open(users.courses.get(user["course_id"]), _utcnow()):
        return 402
    return None


# Azərbaycan 2016-dan yay vaxtını ləğv edib: sabit UTC+4. `zoneinfo`
# QƏSDƏN işlədilmir — Windows-da tzdata paketi olmadan «Asia/Baku» tapılmır.
_BAKU_TZ = timezone(timedelta(hours=4))


def _baku_day_start_utc(now: datetime) -> datetime:
    """Bakı təqvim gününün başlanğıcı, UTC-də (gündəlik limit sayğacı üçün)."""
    local = now.astimezone(_BAKU_TZ)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc)


def _enforce_upload_quota(
    user: dict, users: UserStore, materials: MaterialStore, question_sets: QuestionSetStore
) -> None:
    """Gündəlik yükləmə limiti (spec §4.5): hər yükləmə AI generasiyasıdır,
    yəni xərc. Çat materialı VƏ sual bankı BİRLİKDƏ sayılır. Yeni sayğac
    yoxdur — mövcud cədvəllərdən sayılır. Platforma sahibi azaddır."""
    if user["is_platform_owner"]:
        return
    course = users.courses.get(user["course_id"])
    if course is None:
        return
    limit = course["upload_limit_teacher"] if user["is_teacher"] else course["upload_limit_student"]
    since = _baku_day_start_utc(_utcnow()).isoformat()
    used = materials.count_by_uploader_since(user["id"], since) + question_sets.count_by_creator_since(
        user["id"], since
    )
    if used >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Gündəlik yükləmə limiti ({limit}) dolub. Sabah yenidən cəhd edin.",
        )


def _enforce_access(user: dict, users: UserStore) -> None:
    problem = _access_problem(user, users)
    if problem == 401:
        raise _UNAUTHORIZED
    if problem == 402:
        raise _LICENSE_CLOSED


def get_current_teacher(user: dict = Depends(get_current_user)) -> dict:
    """Müəllim əməliyyatları üçün qapı.

    NİYƏ AYRICA ASILILIQ: bu yoxlama əvvəl hər endpoint-in içində əl ilə
    yazılırdı və BEŞ yerdə unudulmuşdu (2026-09-10-da tapıldı) — istənilən
    tələbə sual bankı yarada (yəni AI kvotamızı xərcləyə), bütün bankların
    siyahısını görə və canlı sessiya aça bilirdi. Asılılıq kimi yazılanda
    unudulması imzada görünür.

    401 (giriş yoxdur) və 403 (müəllim deyil) QƏSDƏN fərqlidir: client
    401-də istifadəçini giriş səhifəsinə yönəldir, 403-də yönəltməməlidir.
    """
    if not user["is_teacher"]:
        raise HTTPException(status_code=403, detail="Bu əməliyyat yalnız müəllim üçündür")
    return user


def _user_info(user: dict) -> UserInfo:
    """DB sətrindən cavab modeli — `password_hash` qəsdən daxil edilmir."""
    return UserInfo(
        id=user["id"],
        email=user["email"],
        display_name=user["display_name"],
        created_at=user["created_at"],
        is_teacher=bool(user["is_teacher"]),
        is_admin=bool(user["is_admin"]),
        is_platform_owner=bool(user["is_platform_owner"]),
    )


_COURSE_CODE_NOT_FOUND = "Kurs kodu tapılmadı"
_INVITE_NOT_FOUND = "Dəvət linki etibarsızdır və ya müddəti bitib"


@app.post("/auth/register", response_model=AuthResponse, status_code=201)
def auth_register(
    req: RegisterRequest,
    request: Request,
    store: UserStore = Depends(get_user_store),
    secret: str = Depends(get_token_secret),
    limiter: RateLimiter = Depends(get_register_rate_limiter),
) -> AuthResponse:
    """Qapalı qeydiyyat (spec 2026-09-29 §4.1).

    SIRA VACİBDİR: (1) IP bloku, (2) kod/dəvət, (3) e-poçt. Kod səhvdirsə
    e-poçtun mövcudluğu açılmır. Səhv, bağlı və ya mövcud olmayan kurs
    EYNİ 404-ü alır. Yalnız SƏHV cəhdlər sayılır — sinif eyni Wi-Fi-dan
    qeydiyyatdan keçir.
    """
    ip = _client_ip(request)
    if limiter.is_blocked(ip):
        raise HTTPException(status_code=429, detail="Çox sayda səhv cəhd. Bir dəqiqə sonra yenidən yoxlayın.")
    now = _utcnow()
    password_hash = hash_password(req.password)

    if req.invite_token:
        invite = store.courses.peek_teacher_invite(req.invite_token, now=now)
        if invite is None or not course_is_open(store.courses.get(invite["course_id"]), now):
            limiter.record(ip)
            raise HTTPException(status_code=404, detail=_INVITE_NOT_FOUND)
        try:
            user = store.create_teacher_from_invite(
                req.email, password_hash, req.display_name, req.invite_token, now=now
            )
        except InvalidInvite:
            limiter.record(ip)
            raise HTTPException(status_code=404, detail=_INVITE_NOT_FOUND)
        except DuplicateEmail:
            raise HTTPException(status_code=409, detail="Bu e-poçt artıq qeydiyyatdadır")
    else:
        course = store.courses.get_by_join_code(req.course_code)
        if course is None or not course_is_open(course, now):
            limiter.record(ip)
            raise HTTPException(status_code=404, detail=_COURSE_CODE_NOT_FOUND)
        try:
            user = store.create_student(
                req.email, password_hash, req.display_name, course_id=course["id"]
            )
        except CourseFull:
            raise HTTPException(
                status_code=409,
                detail="Kursda boş yer qalmayıb. Müəlliminizə müraciət edin.",
            )
        except DuplicateEmail:
            raise HTTPException(status_code=409, detail="Bu e-poçt artıq qeydiyyatdadır")
    return AuthResponse(token=create_token(user["id"], secret=secret), user=_user_info(user))


@app.post("/auth/login", response_model=AuthResponse)
def auth_login(
    req: LoginRequest,
    request: Request,
    store: UserStore = Depends(get_user_store),
    secret: str = Depends(get_token_secret),
    limiter: RateLimiter = Depends(get_login_rate_limiter),
) -> AuthResponse:
    # Açar (e-poçt, IP) CÜTÜDÜR: yalnız e-poçt olsaydı, tələbə müəllimin
    # e-poçtuna səhv şifrə göndərib müəllimi bloklaya bilərdi. Blok doğru
    # şifrəni də buraxmır; uğurlu giriş sayılmır.
    limit_key = f"{req.email.strip().lower()}|{_client_ip(request)}"
    if limiter.is_blocked(limit_key):
        raise HTTPException(
            status_code=429, detail="Çox sayda səhv cəhd. 15 dəqiqə sonra yenidən yoxlayın."
        )
    user = store.get_by_email(req.email)
    # Naməlum e-poçt və səhv şifrə EYNİ cavabı verir — hansı e-poçtların
    # qeydiyyatda olduğunu üzə çıxarmamaq üçün.
    if user is None or not verify_password(req.password, user["password_hash"]):
        limiter.record(limit_key)
        raise HTTPException(status_code=401, detail="E-poçt və ya şifrə səhvdir")
    # Kurs/aktivlik YALNIZ doğru şifrədən sonra yoxlanır — əks halda şifrəsiz
    # «bu e-poçt bağlı kursdadır» öyrənmək olardı. Çıxarılmış istifadəçi
    # naməlum e-poçtla EYNİ cavabı alır.
    problem = _access_problem(user, store)
    if problem == 401:
        raise HTTPException(status_code=401, detail="E-poçt və ya şifrə səhvdir")
    if problem == 402:
        raise _LICENSE_CLOSED
    return AuthResponse(token=create_token(user["id"], secret=secret), user=_user_info(user))


@app.get("/me/course", response_model=MeCourseInfo)
def get_my_course(
    user: dict = Depends(get_current_user),
    users: UserStore = Depends(get_user_store),
) -> MeCourseInfo:
    """Bağlı kursun istifadəçisi bura ÇATMIR (qapı 402 qaytarır) — yəni
    `is_open` praktikada həmişə True-dur; platforma sahibi istisnadır."""
    course = users.courses.get(user["course_id"])
    if course is None:
        raise HTTPException(status_code=404, detail="Kurs tapılmadı")
    now = _utcnow()
    return MeCourseInfo(
        name=course["name"],
        status=course["status"],
        days_left=days_left(course, now),
        is_open=course_is_open(course, now),
        profile=course["profile"],
    )


# ==== Sahib paneli (spec 2026-09-29 §3) ======================================


def get_platform_owner(user: dict = Depends(get_current_user)) -> dict:
    """Yalnız platforma sahibi. Başqasına FastAPI-nin naməlum marşrut
    cavabı ilə EYNİ 404 qaytarılır — panelin varlığı belə açılmır (admin
    də daxil). Bayraq API ilə dəyişdirilmir, yalnız VPS-də əl ilə."""
    if not user["is_platform_owner"]:
        raise HTTPException(status_code=404, detail="Not Found")
    return user


_ACTIVITY_WINDOW = timedelta(days=7)

# Jurnal İNSANA göstərilir — daxili dəyərlər (`english`, `active`,
# `seat_limit`) orada görünməməlidir.
_PROFILE_WORDS = {"english": "ingilis dili", "exam_prep": "imtahana hazırlıq"}
_STATUS_WORDS = {STATUS_ACTIVE: "ödənişli", STATUS_TRIAL: "sınaq"}
_SETTING_WORDS = {
    "name": "ad",
    "seat_limit": "tələbə limiti",
    "upload_limit_student": "tələbə yükləməsi/gün",
    "upload_limit_teacher": "müəllim yükləməsi/gün",
}
_DAYS_PER_PAID_MONTH = 30


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _owner_course_info(
    course: dict,
    *,
    users: UserStore,
    chats: ChatStore,
    messages: MessageStore,
    question_sets: QuestionSetStore,
    live_sessions: LiveSessionStore,
    homework: HomeworkStore,
) -> OwnerCourseInfo:
    """Aktivlik YENİ izləmə kodu olmadan mövcud cədvəllərdən sayılır —
    yeni izləmə sistemi yeni sınma nöqtəsi olardı. Store-lar ayrı
    fayllardadır, ona görə kursun çat ID-ləri ötürülür."""
    now = _utcnow()
    since = (now - _ACTIVITY_WINDOW).isoformat()
    chat_ids = chats.list_ids_by_course(course["id"])
    activity = CourseActivity(
        sessions=live_sessions.count_sessions_in_chats_since(chat_ids, since),
        question_sets=question_sets.count_by_course_since(course["id"], since),
        answers=live_sessions.count_answers_in_chats_since(chat_ids, since)
        + homework.count_answers_in_chats_since(chat_ids, since),
        messages=messages.count_in_chats_since(chat_ids, since),
    )
    stamps = [
        messages.last_in_chats(chat_ids),
        live_sessions.last_answer_in_chats(chat_ids),
        homework.last_answer_in_chats(chat_ids),
        question_sets.last_created_in_course(course["id"]),
    ]
    parsed = [(p, raw) for raw in stamps if raw and (p := _parse_iso(raw))]
    last_activity = max(parsed)[1] if parsed else None
    return OwnerCourseInfo(
        id=course["id"],
        name=course["name"],
        profile=course["profile"],
        status=course["status"],
        is_open=course_is_open(course, now),
        days_left=days_left(course, now),
        trial_ends_at=course["trial_ends_at"],
        paid_until=course["paid_until"],
        seat_limit=course["seat_limit"],
        students_active=users.count_active_students(course["id"]),
        teachers=users.count_teachers(course["id"]),
        upload_limit_student=course["upload_limit_student"],
        upload_limit_teacher=course["upload_limit_teacher"],
        join_code=course["join_code"],
        activity_7d=activity,
        last_activity=last_activity,
    )


def _owner_course_or_404(users: UserStore, course_id: int) -> dict:
    course = users.courses.get(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Kurs tapılmadı")
    return course


def _reject_owner_course(course: dict) -> None:
    """Kurs #1 (mövcud imtahan kursu) müddətsizdir — səhv kliklə bütün
    mövcud istifadəçiləri bağlamaq mümkün olmamalıdır."""
    if course["status"] == STATUS_OWNER:
        raise HTTPException(status_code=400, detail="Bu kurs müddətsizdir, statusu dəyişdirilmir")


class _OwnerDeps:
    """Siyahı cavabı üçün lazım olan store-lar — hər endpoint-də eyni
    uzun imzanı təkrarlamamaq üçün."""

    def __init__(
        self,
        users: UserStore = Depends(get_user_store),
        chats: ChatStore = Depends(get_chat_store),
        messages: MessageStore = Depends(get_message_store),
        question_sets: QuestionSetStore = Depends(get_question_set_store),
        live_sessions: LiveSessionStore = Depends(get_live_session_store),
        homework: HomeworkStore = Depends(get_homework_store),
    ) -> None:
        self.users = users
        self.chats = chats
        self.messages = messages
        self.question_sets = question_sets
        self.live_sessions = live_sessions
        self.homework = homework

    def info(self, course_id: int) -> OwnerCourseInfo:
        return _owner_course_info(
            self.users.courses.get(course_id),
            users=self.users, chats=self.chats, messages=self.messages,
            question_sets=self.question_sets, live_sessions=self.live_sessions,
            homework=self.homework,
        )


@app.get("/owner/courses", response_model=list[OwnerCourseInfo])
def owner_list_courses(
    owner: dict = Depends(get_platform_owner),
    deps: _OwnerDeps = Depends(),
) -> list[OwnerCourseInfo]:
    return [deps.info(course["id"]) for course in deps.users.courses.list_all()]


@app.post("/owner/courses", response_model=OwnerCourseInfo, status_code=201)
def owner_create_course(
    req: CreateCourseRequest,
    owner: dict = Depends(get_platform_owner),
    deps: _OwnerDeps = Depends(),
) -> OwnerCourseInfo:
    try:
        course = deps.users.courses.create(
            req.name, req.profile, trial_days=req.trial_days, seat_limit=req.seat_limit,
            now=_utcnow(),
        )
    except UnknownProfile:
        raise HTTPException(status_code=422, detail="Naməlum kurs profili")
    seats = req.seat_limit if req.seat_limit is not None else "limitsiz"
    deps.users.courses.log_owner_action(
        owner_id=owner["id"], course_id=course["id"], action="create",
        details=f"{req.name}, {_PROFILE_WORDS[req.profile]}, sınaq {req.trial_days} gün, {seats} yer",
    )
    return deps.info(course["id"])


@app.post("/owner/courses/{course_id}/payments", response_model=OwnerCourseInfo)
def owner_record_payment(
    course_id: int,
    req: CoursePaymentRequest,
    owner: dict = Depends(get_platform_owner),
    deps: _OwnerDeps = Depends(),
) -> OwnerCourseInfo:
    """Ödəniş əl ilə qeyd olunur. Yeni dövr İNDİDƏN yox, cari dövrün
    sonundan başlayır: sınaqda ödəyən qalan sınaq günlərini, vaxtından
    əvvəl uzadan qalan ödənişli günləri itirmir."""
    course = _owner_course_or_404(deps.users, course_id)
    _reject_owner_course(course)
    now = _utcnow()
    candidates = [now] + [
        d for d in (_parse_iso(course["paid_until"]), _parse_iso(course["trial_ends_at"])) if d
    ]
    paid_until = max(candidates) + timedelta(days=_DAYS_PER_PAID_MONTH * req.months)
    deps.users.courses.set_paid_until(course_id, paid_until)
    deps.users.courses.log_owner_action(
        owner_id=owner["id"], course_id=course_id, action="payment",
        details=f"+{req.months} ay, {paid_until.date().isoformat()} tarixinədək",
    )
    return deps.info(course_id)


@app.post("/owner/courses/{course_id}/suspend", response_model=OwnerCourseInfo)
def owner_suspend_course(
    course_id: int,
    owner: dict = Depends(get_platform_owner),
    deps: _OwnerDeps = Depends(),
) -> OwnerCourseInfo:
    course = _owner_course_or_404(deps.users, course_id)
    _reject_owner_course(course)
    deps.users.courses.set_status(course_id, STATUS_SUSPENDED)
    deps.users.courses.log_owner_action(
        owner_id=owner["id"], course_id=course_id, action="suspend", details="dayandırıldı",
    )
    return deps.info(course_id)


@app.post("/owner/courses/{course_id}/resume", response_model=OwnerCourseInfo)
def owner_resume_course(
    course_id: int,
    owner: dict = Depends(get_platform_owner),
    deps: _OwnerDeps = Depends(),
) -> OwnerCourseInfo:
    """Ödəniş qeydi varsa `active`, yoxdursa `trial`-a qayıdır. Tarixlər
    keçibsə kurs bərpadan sonra da BAĞLI qalır — onda «Ödənildi» lazımdır
    (panel bunu `is_open` ilə göstərir)."""
    course = _owner_course_or_404(deps.users, course_id)
    _reject_owner_course(course)
    status = STATUS_ACTIVE if course["paid_until"] else STATUS_TRIAL
    deps.users.courses.set_status(course_id, status)
    deps.users.courses.log_owner_action(
        owner_id=owner["id"], course_id=course_id, action="resume",
        details=f"bərpa edildi ({_STATUS_WORDS[status]})",
    )
    return deps.info(course_id)


@app.patch("/owner/courses/{course_id}", response_model=OwnerCourseInfo)
def owner_update_course(
    course_id: int,
    req: UpdateCourseRequest,
    owner: dict = Depends(get_platform_owner),
    deps: _OwnerDeps = Depends(),
) -> OwnerCourseInfo:
    _owner_course_or_404(deps.users, course_id)
    changes = req.model_dump(exclude_none=True)
    deps.users.courses.update_settings(course_id, **changes)
    if changes:
        details = ", ".join(f"{_SETTING_WORDS[key]} {value}" for key, value in changes.items())
        deps.users.courses.log_owner_action(
            owner_id=owner["id"], course_id=course_id, action="update", details=details,
        )
    return deps.info(course_id)


@app.post("/owner/courses/{course_id}/join-code", response_model=JoinCodeInfo)
def owner_regenerate_join_code(
    course_id: int,
    owner: dict = Depends(get_platform_owner),
    users: UserStore = Depends(get_user_store),
) -> JoinCodeInfo:
    _owner_course_or_404(users, course_id)
    code = users.courses.regenerate_join_code(course_id)
    users.courses.log_owner_action(
        owner_id=owner["id"], course_id=course_id, action="join_code",
        details="tələbə kodu yeniləndi (köhnə kod artıq işləmir)",
    )
    return JoinCodeInfo(join_code=code)


@app.post("/owner/courses/{course_id}/teacher-invites", response_model=TeacherInviteInfo, status_code=201)
def owner_create_teacher_invite(
    course_id: int,
    owner: dict = Depends(get_platform_owner),
    users: UserStore = Depends(get_user_store),
) -> TeacherInviteInfo:
    """Müəllimi YALNIZ sahib dəvət edir (istifadəçi qərarı). Token
    jurnala YAZILMIR — jurnal oxuyan onu işlədə bilməməlidir."""
    _owner_course_or_404(users, course_id)
    now = _utcnow()
    token = users.courses.create_teacher_invite(course_id, created_by=owner["id"], now=now)
    expires_at = now + TEACHER_INVITE_TTL
    users.courses.log_owner_action(
        owner_id=owner["id"], course_id=course_id, action="teacher_invite",
        details=f"müəllim dəvəti, {expires_at.date().isoformat()} tarixinədək etibarlı",
    )
    return TeacherInviteInfo(token=token, expires_at=expires_at.isoformat())


@app.get("/owner/audit-log", response_model=list[AuditLogRow])
def owner_audit_log(
    owner: dict = Depends(get_platform_owner),
    users: UserStore = Depends(get_user_store),
) -> list[AuditLogRow]:
    return [AuditLogRow(**row) for row in users.courses.list_audit_log()]


@app.post("/admin/teachers", response_model=UserInfo)
def set_teacher_role(
    req: SetTeacherRequest,
    user: dict = Depends(get_current_user),
    users: UserStore = Depends(get_user_store),
) -> UserInfo:
    """`is_admin` istifadəçilər e-poçtla başqa bir istifadəçini müəllim
    edə/etməkdən çıxara bilər (bax Çox-müəllimli idarəetmə, Faza 4). Bu,
    aşağıdakı `require_admin` (API-açarlı, n8n avtomatlaşdırması üçün)
    İLƏ QARIŞDIRILMAMALIDIR — tamam fərqli bir icazə mexanizmidir
    (istifadəçinin öz Bearer token-lə gələn `is_admin` bayrağı). İLK
    admin hələ də VPS-də əl ilə (`UserStore.set_admin`) təyin edilməlidir
    — bootstrap problemi, admin YOXDURSA heç kim admin təyin edə bilməz."""
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Yalnız admin müəllim təyin edə bilər")
    target = users.get_by_email(req.email)
    # Başqa kursun istifadəçisi «tapılmadı» ilə EYNİ cavabı alır — admin
    # yalnız öz kursunu idarə edir və başqa kursda kimin olduğunu öyrənmir.
    if target is None or target["course_id"] != user["course_id"]:
        raise HTTPException(status_code=404, detail="İstifadəçi tapılmadı")
    users.set_teacher(target["id"], req.is_teacher)
    return _user_info(users.get_by_id(target["id"]))


@app.get("/admin/teachers", response_model=list[UserInfo])
def list_teacher_role(
    user: dict = Depends(get_current_user),
    users: UserStore = Depends(get_user_store),
) -> list[UserInfo]:
    """Hazırda müəllim olan bütün istifadəçilər — admin-in "Müəllim
    idarəetməsi" ekranında siyahını görməsi üçün."""
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Yalnız admin müəllim siyahısına baxa bilər")
    return [_user_info(t) for t in users.list_teachers(course_id=user["course_id"])]


@app.get("/health")
def health(store: UserStore = Depends(get_user_store)) -> dict:
    store.ping()
    return {"status": "ok"}


def require_admin(x_admin_key: str = Header(default="")) -> None:
    """Admin-yalnız endpoint-lər üçün paylaşılan açar yoxlaması.

    `ADMIN_API_KEY` boşdursa (env təyin olunmayıb) BÜTÜN çağırışlar
    403 alır — boş açar "açıq admin" mənasına gəlmir.
    """
    expected = os.environ.get("ADMIN_API_KEY", "")
    if not expected or x_admin_key != expected:
        raise HTTPException(status_code=403, detail="Admin açarı səhvdir")


@app.get("/admin/stats", response_model=AdminStatsInfo, dependencies=[Depends(require_admin)])
def admin_stats(
    users: UserStore = Depends(get_user_store),
    materials: MaterialStore = Depends(get_material_store),
    questions: QuestionStore = Depends(get_question_store),
    sessions: QuizSessionStore = Depends(get_quiz_session_store),
    friendships: FriendshipStore = Depends(get_friendship_store),
) -> AdminStatsInfo:
    return AdminStatsInfo(
        users_total=users.count_all(),
        materials_total=materials.count_all(),
        materials_ready=materials.count_by_status("ready"),
        materials_failed=materials.count_by_status("failed"),
        questions_total=questions.count_all(),
        quiz_sessions_total=sessions.count_all(),
        friendships_accepted=friendships.count_by_status("accepted"),
        **_course_deadlines(users),
    )


# Xəbərdarlıq həddi — müəllimin banneri ilə EYNİ (web/assets/js/license.js).
EXPIRY_WARNING_DAYS = 5


def _course_deadlines(users: UserStore) -> dict[str, list[CourseDeadline]]:
    """Sahibə gündəlik Telegram xəbərdarlığı üçün (n8n «Gündəlik Statistika»).

    Yalnız MÜDDƏTLİ kurslar (sınaq/ödənişli): `owner` müddətsizdir,
    `suspended`-i isə sahib özü dayandırıb — onlar haqqında xəbərdarlıq
    mənasızdır. Bağlanmış kurs ayrıca siyahıdadır: ödəniş gözlənilir."""
    now = _utcnow()
    expiring: list[CourseDeadline] = []
    expired: list[CourseDeadline] = []
    for course in users.courses.list_all():
        if course["status"] not in (STATUS_TRIAL, STATUS_ACTIVE):
            continue
        ends_at = course["trial_ends_at"] if course["status"] == STATUS_TRIAL else course["paid_until"]
        row = CourseDeadline(
            id=course["id"], name=course["name"], status=course["status"],
            days_left=days_left(course, now), ends_at=ends_at,
        )
        if not course_is_open(course, now):
            expired.append(row)
        elif row.days_left <= EXPIRY_WARNING_DAYS:
            expiring.append(row)
    expiring.sort(key=lambda row: row.days_left)
    return {"expiring_courses": expiring, "expired_courses": expired}


@app.post("/friends/requests", response_model=FriendshipInfo, status_code=201)
def send_friend_request(
    req: SendFriendRequestRequest,
    user: dict = Depends(get_current_user),
    users: UserStore = Depends(get_user_store),
    friendships: FriendshipStore = Depends(get_friendship_store),
) -> FriendshipInfo:
    if req.addressee_email is not None:
        addressee = users.get_by_email(req.addressee_email)
    else:
        addressee = users.get_by_id(req.addressee_user_id)
    # Başqa kursun istifadəçisi naməlum e-poçtla EYNİ cavabı alır.
    if addressee is None or not _same_course(addressee["course_id"], user):
        raise HTTPException(status_code=404, detail="İstifadəçi tapılmadı")
    if addressee["id"] == user["id"]:
        raise HTTPException(status_code=400, detail="Özünüzə dost sorğusu göndərə bilməzsiniz")

    try:
        friendship = friendships.create(user["id"], addressee["id"])
    except DuplicateFriendship:
        raise HTTPException(status_code=409, detail="Artıq gözləyən dostluq sorğusu var")
    except AlreadyFriends:
        raise HTTPException(status_code=409, detail="Artıq dostsunuz")
    return FriendshipInfo(**friendship)


@app.get("/friends/requests", response_model=list[FriendshipInfo])
def list_friend_requests(
    user: dict = Depends(get_current_user),
    friendships: FriendshipStore = Depends(get_friendship_store),
) -> list[FriendshipInfo]:
    return [
        FriendshipInfo(**f)
        for f in friendships.list_by_user(user["id"])
        if f["status"] == "pending"
    ]


def _get_friendship_or_404(friendship_id: int, friendships: FriendshipStore, user: dict) -> dict:
    """Tərəf olmayan istifadəçi «tapılmadı» alır (403 yox) — ID-lər ardıcıldır
    və 403 başqalarının dostluq sorğularının mövcudluğunu açardı (spec §4)."""
    friendship = friendships.get(friendship_id)
    if friendship is None or user["id"] not in (
        friendship["requester_id"], friendship["addressee_id"]
    ):
        raise HTTPException(status_code=404, detail="Dostluq sorğusu tapılmadı")
    return friendship


@app.post("/friends/requests/{friendship_id}/accept", response_model=FriendshipInfo)
def accept_friend_request(
    friendship_id: int,
    user: dict = Depends(get_current_user),
    friendships: FriendshipStore = Depends(get_friendship_store),
) -> FriendshipInfo:
    friendship = _get_friendship_or_404(friendship_id, friendships, user)
    if friendship["addressee_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Yalnız ünvanlanan qəbul edə bilər")
    if friendship["status"] != "pending":
        raise HTTPException(status_code=409, detail="Sorğu artıq gözləmədə deyil")
    friendships.update_status(friendship_id, "accepted")
    return FriendshipInfo(**friendships.get(friendship_id))


@app.post("/friends/requests/{friendship_id}/decline", response_model=FriendshipInfo)
def decline_friend_request(
    friendship_id: int,
    user: dict = Depends(get_current_user),
    friendships: FriendshipStore = Depends(get_friendship_store),
) -> FriendshipInfo:
    friendship = _get_friendship_or_404(friendship_id, friendships, user)
    if friendship["addressee_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Yalnız ünvanlanan rədd edə bilər")
    if friendship["status"] != "pending":
        raise HTTPException(status_code=409, detail="Sorğu artıq gözləmədə deyil")
    friendships.update_status(friendship_id, "declined")
    return FriendshipInfo(**friendships.get(friendship_id))


@app.post("/friends/requests/{friendship_id}/cancel", response_model=FriendshipInfo)
def cancel_friend_request(
    friendship_id: int,
    user: dict = Depends(get_current_user),
    friendships: FriendshipStore = Depends(get_friendship_store),
) -> FriendshipInfo:
    friendship = _get_friendship_or_404(friendship_id, friendships, user)
    if friendship["requester_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Yalnız sorğunu göndərən ləğv edə bilər")
    if friendship["status"] != "pending":
        raise HTTPException(status_code=409, detail="Sorğu artıq gözləmədə deyil")
    friendships.update_status(friendship_id, "cancelled")
    return FriendshipInfo(**friendships.get(friendship_id))


@app.get("/friends", response_model=list[FriendshipInfo])
def list_friends(
    user: dict = Depends(get_current_user),
    friendships: FriendshipStore = Depends(get_friendship_store),
) -> list[FriendshipInfo]:
    return [
        FriendshipInfo(**f)
        for f in friendships.list_by_user(user["id"])
        if f["status"] == "accepted"
    ]


@app.post("/friends/{friendship_id}/unfriend", response_model=FriendshipInfo)
def unfriend(
    friendship_id: int,
    user: dict = Depends(get_current_user),
    friendships: FriendshipStore = Depends(get_friendship_store),
) -> FriendshipInfo:
    friendship = _get_friendship_or_404(friendship_id, friendships, user)
    if user["id"] not in (friendship["requester_id"], friendship["addressee_id"]):
        raise HTTPException(status_code=403, detail="Bu dostluğa aid deyilsiniz")
    if friendship["status"] != "accepted":
        raise HTTPException(status_code=409, detail="Yalnız aktiv dostluq pozula bilər")
    friendships.update_status(friendship_id, "unfriended")
    return FriendshipInfo(**friendships.get(friendship_id))


@app.post("/chats", response_model=ChatInfo, status_code=201)
def create_chat(
    req: CreateChatRequest,
    user: dict = Depends(get_current_user),
    chats: ChatStore = Depends(get_chat_store),
    users: UserStore = Depends(get_user_store),
    friendships: FriendshipStore = Depends(get_friendship_store),
) -> ChatInfo:
    if req.kind == "group":
        chat = chats.create(
            kind="group", created_by=user["id"], name=req.name, course_id=user["course_id"]
        )
        chats.add_member(chat["id"], user["id"])
    else:
        peer = users.get_by_id(req.peer_user_id)
        if peer is None or not _same_course(peer["course_id"], user):
            raise HTTPException(status_code=404, detail="İstifadəçi tapılmadı")
        if not friendships.are_friends(user["id"], req.peer_user_id):
            raise HTTPException(status_code=403, detail="Yalnız dostlarla birbaşa çat yaradıla bilər")
        chat = chats.create(kind="direct", created_by=user["id"], course_id=user["course_id"])
        chats.add_member(chat["id"], user["id"])
        chats.add_member(chat["id"], req.peer_user_id)
    return _chat_info_for(chat, user["id"])


@app.get("/chats", response_model=list[ChatInfo])
def list_chats(
    user: dict = Depends(get_current_user),
    chats: ChatStore = Depends(get_chat_store),
) -> list[ChatInfo]:
    return [_chat_info_for(c, user["id"]) for c in chats.list_by_user(user["id"])]


# `POST /chats/{chat_id}/join` BURADAN SİLİNDİ (2026-09-11).
# Səbəb: heç bir yoxlama etmirdi, çat ID-ləri isə `AUTOINCREMENT`, yəni
# ARDICIL — 1-dən saymaqla sistemdəki bütün qrup çatlarına girmək
# olurdu. Yerini kod + təsdiq axını tutdu (aşağıda).


# ---- Kurs sərhədi (spec 2026-09-29 §4) ------------------------------------
# Başqa kursun obyekti «tapılmadı» ilə EYNİ cavabı alır: 403 «var, amma
# sənin deyil» deməkdir, ID-lər isə ardıcıldır — 1-dən saymaqla digər
# kursların nəyə sahib olduğu öyrənilərdi. Bütün yoxlamalar bu köməkçilərdən
# keçir; `tests/server/test_course_boundary.py` hər ID marşrutunu sınayır.


def _course_profile(users: UserStore, course_id: int) -> str:
    """Kursun generasiya profili (spec §5); kurs tapılmasa imtahan profili."""
    course = users.courses.get(course_id)
    return course["profile"] if course else "exam_prep"


def _same_course(course_id: int | None, user: dict) -> bool:
    return course_id is not None and course_id == user["course_id"]


def _chat_in_course(chats: ChatStore, chat_id: int, user: dict) -> dict:
    chat = chats.get(chat_id)
    if chat is None or not _same_course(chat.get("course_id"), user):
        raise HTTPException(status_code=404, detail="Çat tapılmadı")
    return chat


def _question_set_in_course(
    question_sets: QuestionSetStore, question_set_id: int, user: dict
) -> dict:
    question_set = question_sets.get(question_set_id)
    if question_set is None or not _same_course(question_set.get("course_id"), user):
        raise HTTPException(status_code=404, detail="Sual bankı tapılmadı")
    return question_set


def _question_in_course(question_sets: QuestionSetStore, question_id: int, user: dict) -> dict:
    question = question_sets.get_question(question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Sual tapılmadı")
    question_set = question_sets.get(question["question_set_id"])
    if question_set is None or not _same_course(question_set.get("course_id"), user):
        raise HTTPException(status_code=404, detail="Sual tapılmadı")
    return question


def _assignment_in_course(
    homework: HomeworkStore, chats: ChatStore, assignment_id: int, user: dict
) -> dict:
    """Tapşırığın kursu çatından gəlir."""
    assignment = homework.get_assignment(assignment_id)
    chat = chats.get(assignment["chat_id"]) if assignment else None
    if chat is None or not _same_course(chat.get("course_id"), user):
        raise HTTPException(status_code=404, detail="Tapşırıq tapılmadı")
    return assignment


def _session_course_id(
    session: dict, chats: ChatStore, question_sets: QuestionSetStore
) -> int | None:
    """Canlı sessiyanın kursu — çatdan; köhnə (çatsız PIN) sessiyada bankdan."""
    if session.get("chat_id") is not None:
        chat = chats.get(session["chat_id"])
        return chat["course_id"] if chat else None
    question_set = question_sets.get(session["question_set_id"])
    return question_set["course_id"] if question_set else None


def _require_chat_creator(chat_id: int, user: dict, chats: ChatStore) -> dict:
    """Çatı YARADAN olmaq şərti — üzv olmaq kifayət etmir.

    Ayrıca funksiyadır, çünki dörd endpoint eyni qapıdan keçir; sətiriçi
    yazılsa, biri unudulanda bu heç yerdə görünməzdi (bax `/live/*`-dakı
    beş qapısız endpoint hadisəsi).
    """
    chat = _chat_in_course(chats, chat_id, user)
    if chat["created_by"] != user["id"]:
        raise HTTPException(status_code=403, detail="Yalnız çatı yaradan idarə edə bilər")
    return chat


def _chat_info_for(chat: dict, user_id: int) -> ChatInfo:
    """Dəvət kodunu YALNIZ yaradana göstərir.

    Adi üzvə kodu versək, hər tələbə onu kənara ötürə bilər — təsdiq
    yenə tələb olunur, amma müəllim bundan xəbərsiz qalar.
    """
    data = dict(chat)
    if data.get("created_by") != user_id:
        data["invite_code"] = None
    return ChatInfo(**data)


@app.post("/chats/join-requests", response_model=JoinRequestResult, status_code=201)
def request_to_join_chat(
    req: JoinByCodeRequest,
    user: dict = Depends(get_current_user),
    chats: ChatStore = Depends(get_chat_store),
    join_requests: ChatJoinRequestStore = Depends(get_chat_join_request_store),
    limiter: RateLimiter = Depends(get_join_rate_limiter),
) -> JoinRequestResult:
    """Dəvət kodu ilə qoşulma istəyi. Üzvlük YARATMIR — müəllim təsdiqi
    ayrı addımdır.

    SÜRƏT LİMİTİ istifadəçi üzrədir: 887 milyon variantlı kodu dəqiqədə
    5 cəhdlə axtarmaq orta hesabla ≈169 il çəkir.
    AÇIQ MƏHDUDİYYƏT: qeydiyyat sərbəstdir, yəni çoxlu hesab açan
    hücumçu üçün limit hesab sayına bölünür. Bu, kodun tək müdafiə
    olmadığı üçün qəbul edilir (təsdiq onsuz da tələb olunur, müəllim
    kodu istənilən vaxt yeniləyə bilər), amma bilinən boşluqdur.
    """
    if not limiter.allow(str(user["id"])):
        raise HTTPException(
            status_code=429, detail="Çox sayda cəhd. Bir dəqiqə sonra yenidən yoxlayın."
        )
    chat = chats.get_by_invite_code(req.code)
    # Səhv kodda HƏMİŞƏ eyni cavab — cavab fərqinə baxıb kod təxmin
    # etmək mümkün olmamalıdır.
    if chat is None or not _same_course(chat.get("course_id"), user):
        raise HTTPException(status_code=404, detail="Belə kod tapılmadı")
    if user["id"] in chats.list_member_ids(chat["id"]):
        # «İstək göndərildi» yalançı olardı; üstəlik onsuz da üzv olan
        # adam müəllimin gözləyənlər siyahısına düşməməlidir.
        raise HTTPException(status_code=409, detail="Siz artıq bu çatın üzvüsünüz")
    row = join_requests.request(chat_id=chat["id"], user_id=user["id"])
    return JoinRequestResult(chat_name=chat["name"], status=row["status"])


@app.get("/chats/{chat_id}/join-requests", response_model=list[JoinRequestRow])
def list_join_requests(
    chat_id: int,
    user: dict = Depends(get_current_user),
    chats: ChatStore = Depends(get_chat_store),
    join_requests: ChatJoinRequestStore = Depends(get_chat_join_request_store),
    users: UserStore = Depends(get_user_store),
) -> list[JoinRequestRow]:
    """Gözləyən istəklər — yalnız çatı yaradana."""
    _require_chat_creator(chat_id, user, chats)
    rows = []
    for row in join_requests.list_pending(chat_id):
        requester = users.get_by_id(row["user_id"])
        # Başqa kursun istifadəçisi (köhnə/əl ilə yaranmış istək) göstərilmir.
        if requester is None or not _same_course(requester["course_id"], user):
            # Hesab silinibsə sətri göstərmirik — müəllim qərar verə
            # bilməyəcəyi sətirlə qarşılaşmamalıdır.
            continue
        rows.append(
            JoinRequestRow(
                user_id=row["user_id"],
                display_name=requester["display_name"],
                created_at=row["created_at"],
            )
        )
    return rows


@app.post(
    "/chats/{chat_id}/join-requests/approve", response_model=ApproveJoinRequestsResult
)
def approve_join_requests(
    chat_id: int,
    req: ApproveJoinRequestsRequest,
    user: dict = Depends(get_current_user),
    chats: ChatStore = Depends(get_chat_store),
    join_requests: ChatJoinRequestStore = Depends(get_chat_join_request_store),
    users: UserStore = Depends(get_user_store),
) -> ApproveJoinRequestsResult:
    """Toplu təsdiq — «Hamısını təsdiqlə» bir sorğu göndərir.

    Üzv YALNIZ store-un təsdiqlədiyi `user_id`-lər üçün əlavə olunur.
    `user_ids` çağırandan gəldiyi üçün bu vacibdir: gözləyən istəyi
    olmayan adamı bu endpoint ilə çata salmaq mümkün olmamalıdır.
    """
    chat = _require_chat_creator(chat_id, user, chats)
    # Müdafiə dərinliyi: başqa kursun istifadəçisi istəyi olsa belə çata
    # SALINMIR (qoşulma kodu onsuz da kurs daxilindədir).
    same_course_ids = [
        uid for uid in req.user_ids
        if (member := users.get_by_id(uid)) is not None
        and _same_course(member["course_id"], {"course_id": chat["course_id"]})
    ]
    approved = join_requests.approve(
        chat_id=chat_id, user_ids=same_course_ids, decided_by=user["id"]
    )
    for user_id in approved:
        chats.add_member(chat_id, user_id)
    return ApproveJoinRequestsResult(approved_user_ids=approved)


@app.post("/chats/{chat_id}/join-requests/{requester_id}/decline", status_code=200)
def decline_join_request(
    chat_id: int,
    requester_id: int,
    user: dict = Depends(get_current_user),
    chats: ChatStore = Depends(get_chat_store),
    join_requests: ChatJoinRequestStore = Depends(get_chat_join_request_store),
) -> dict:
    """Rədd. Tələbə YENİDƏN istək göndərə bilər — müəllim səhvən rədd
    etsə, bu, həmişəlik bloklanma olmamalıdır."""
    _require_chat_creator(chat_id, user, chats)
    if not join_requests.decline(
        chat_id=chat_id, user_id=requester_id, decided_by=user["id"]
    ):
        raise HTTPException(status_code=404, detail="Gözləyən istək tapılmadı")
    return {"status": "rədd edildi"}


@app.post("/chats/{chat_id}/invite-code", response_model=InviteCodeInfo)
def regenerate_invite_code(
    chat_id: int,
    user: dict = Depends(get_current_user),
    chats: ChatStore = Depends(get_chat_store),
) -> InviteCodeInfo:
    """Kodu yeniləyir — köhnə kod dərhal işləməz olur.

    Kod sinifdən kənara çıxanda (şəkil, ekran paylaşımı) müəllimin
    yeganə çarəsidir.
    """
    _require_chat_creator(chat_id, user, chats)
    return InviteCodeInfo(invite_code=chats.regenerate_invite_code(chat_id))


@app.get("/chats/{chat_id}/members", response_model=list[ChatMemberInfo])
def list_chat_members(
    chat_id: int,
    user: dict = Depends(get_current_user),
    chats: ChatStore = Depends(get_chat_store),
    users: UserStore = Depends(get_user_store),
) -> list[ChatMemberInfo]:
    """Çatın üzv siyahısı — müəllimin Fərdi tələbə tarixçəsi ekranında
    tələbə seçmək üçün istifadə olunur (bax `/history/student/{id}`)."""
    _chat_in_course(chats, chat_id, user)
    if user["id"] not in chats.list_member_ids(chat_id):
        raise HTTPException(status_code=403, detail="Bu çatın üzvü deyilsiniz")
    result = []
    for member_id in chats.list_member_ids(chat_id):
        member = users.get_by_id(member_id)
        if member is not None:
            result.append(ChatMemberInfo(user_id=member_id, display_name=member["display_name"]))
    return result


@app.get("/chats/{chat_id}/leaderboard", response_model=list[LeaderboardRow])
def get_chat_leaderboard(
    chat_id: int,
    user: dict = Depends(get_current_user),
    chats: ChatStore = Depends(get_chat_store),
    users: UserStore = Depends(get_user_store),
    homework: HomeworkStore = Depends(get_homework_store),
    live_sessions: LiveSessionStore = Depends(get_live_session_store),
) -> list[LeaderboardRow]:
    """Çatın liderlik lövhəsi — ev tapşırığı + canlı sessiya CƏMİ.

    2026-09-11-ə qədər yalnız ev tapşırığı sayılırdı, çünki canlı
    sessiyalar çata bağlı deyildi. İndi hər ikisi sayılır.

    Sıralama cəmiyədir, komponentlər isə sətirdə görünür — «hansı
    sahədə geridəyəm» sualı cavabsız qalmamalıdır.

    MÜƏLLİM SİYAHIDAN ÇIXARILIR: tapşırığı təyin edən tərəfdir, tələbə
    ilə yarışmır. Baxmaq isə qadağan deyil.

    Xalı olmayan üzvlər 0 ilə DAXİLDİR — hər iki mənbə metodu sıfır
    sətirləri qaytarmır (eyni müqavilə), doldurma burada olur.
    """
    _chat_in_course(chats, chat_id, user)
    if user["id"] not in chats.list_member_ids(chat_id):
        raise HTTPException(status_code=403, detail="Bu çatın üzvü deyilsiniz")

    homework_scores = homework.get_chat_leaderboard(chat_id)
    live_scores = live_sessions.chat_scores_by_user(chat_id)

    rows = []
    for member_id in chats.list_member_ids(chat_id):
        member = users.get_by_id(member_id)
        if member is None or member["is_teacher"]:
            continue
        hw = homework_scores.get(member_id, 0)
        live = live_scores.get(member_id, 0)
        rows.append((member_id, member["display_name"], hw, live, hw + live))
    # Bərabər cəmdə ad ilə sıralama — əks halda sıra təsadüfi olardı və
    # səhifə hər yenilənəndə dəyişərdi.
    rows.sort(key=lambda r: (-r[4], r[1]))
    return [
        LeaderboardRow(
            user_id=uid, display_name=name,
            homework_score=hw, live_score=live, total_score=total, rank=i + 1,
        )
        for i, (uid, name, hw, live, total) in enumerate(rows)
    ]


def _schedule_timeout(
    chat_id: int,
    expected_index: int,
    *,
    session_store: QuizSessionStore,
    question_store: QuestionStore,
    attempt_store: QuizAttemptStore,
    message_store: MessageStore,
    connection_manager: ConnectionManager,
) -> None:
    """Sual üçün fon timeout-u planlaşdırır. Köhnə (artıq üstələnmiş) task-ın
    üzərinə yazılması təhlükəsizdir — o, işə düşəndə `check_timeout`-un öz
    `expected_index` yoxlaması onsuz da no-op edəcəkdi; erkən çöp yığılması
    bu səbəbdən funksional fərq yaratmır."""
    task = asyncio.create_task(
        check_timeout(
            chat_id,
            expected_index,
            session_store=session_store,
            question_store=question_store,
            attempt_store=attempt_store,
            message_store=message_store,
            connection_manager=connection_manager,
            timeout_seconds=DEFAULT_QUESTION_TIMEOUT_SECONDS,
        )
    )
    app.state.active_quiz_timeouts[chat_id] = task


@app.post("/chats/{chat_id}/quiz/start", response_model=QuizSessionInfo, status_code=201)
async def start_chat_quiz(
    chat_id: int,
    req: QuizStartRequest,
    user: dict = Depends(get_current_user),
    materials: MaterialStore = Depends(get_material_store),
    questions: QuestionStore = Depends(get_question_store),
    sessions: QuizSessionStore = Depends(get_quiz_session_store),
    attempts: QuizAttemptStore = Depends(get_quiz_attempt_store),
    messages: MessageStore = Depends(get_message_store),
    manager: ConnectionManager = Depends(get_connection_manager),
    chats: ChatStore = Depends(get_chat_store),
) -> QuizSessionInfo:
    _chat_in_course(chats, chat_id, user)
    material = materials.get(req.material_id)
    if material is None:
        raise HTTPException(status_code=404, detail="Material tapılmadı")
    if material["uploaded_by"] != user["id"]:
        raise HTTPException(status_code=403, detail="Yalnız materialı yükləyən quiz başlada bilər")
    if material["chat_id"] != chat_id:
        raise HTTPException(status_code=400, detail="Bu material bu çata aid deyil")
    if material["status"] != "ready":
        raise HTTPException(status_code=400, detail="Material hələ hazır deyil")

    try:
        session = await start_quiz(
            chat_id,
            req.material_id,
            question_store=questions,
            session_store=sessions,
            message_store=messages,
            connection_manager=manager,
        )
    except QuizAlreadyActive:
        raise HTTPException(status_code=409, detail="Bu çatda artıq aktiv quiz var")
    except QuizError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    _schedule_timeout(
        chat_id,
        session["current_index"],
        session_store=sessions,
        question_store=questions,
        attempt_store=attempts,
        message_store=messages,
        connection_manager=manager,
    )
    return QuizSessionInfo(**session)


async def _notify_admin_webhook(payload: dict) -> None:
    """`ADMIN_WEBHOOK_URL` (n8n Webhook Trigger) təyin olunubsa fire-and-
    forget POST edir. Heç vaxt istisna atmır — bildiriş uğursuzluğu
    material emalının nəticəsini POZMAMALIDIR (spec bölmə 3.2/6)."""
    webhook_url = os.environ.get("ADMIN_WEBHOOK_URL")
    if not webhook_url:
        return
    try:
        async with httpx.AsyncClient(timeout=3) as http:
            await http.post(webhook_url, json=payload)
    except Exception:
        pass


def _material_ready_message(result) -> str:
    actual = len(result.questions)
    requested = result.requested_question_count
    if actual >= requested:
        return f"Material hazırdır! {actual} sual yaradıldı."
    return (
        f"Material hazırdır! {actual}/{requested} sual yaradıldı "
        "(material qısa idi, daha az sual alındı)."
    )


async def _process_material(
    material_id: int,
    chat_id: int,
    source: MaterialSource,
    *,
    generator,
    material_store: MaterialStore,
    question_store: QuestionStore,
    message_store: MessageStore,
    connection_manager: ConnectionManager,
    question_count: int = 10,
    profile: str = "exam_prep",
) -> None:
    """Materialı fon thread-ində emal edir — nəticə/xəta çata sistem mesajı
    kimi bildirilir, HEÇ vaxt səssiz udulmur (spec bölmə 5-6)."""
    try:
        # Profil çatın kursundan gəlir (spec 2026-09-29 §5). Çat quiz-i
        # canlıdır — mətn göstərilmir, ona görə həmişə `practice`.
        result = await asyncio.to_thread(
            partial(generator, source, question_count, profile=profile, bank_kind="practice")
        )
    except Exception as exc:
        # `str(exc)` çat mesajında yalnız QISA görünür — tam traceback
        # (chained `__cause__` daxil) yalnız burada, journalctl-də qalır.
        logger.exception("Material emalı uğursuz oldu (material_id=%s)", material_id)
        material_store.update_status(material_id, "failed")
        message = message_store.create(
            chat_id, None, "system", f"Material emalı uğursuz oldu: {exc}"
        )
        await connection_manager.broadcast(chat_id, {"type": "message", **message})
        await _notify_admin_webhook(
            {
                "material_id": material_id,
                "chat_id": chat_id,
                "kind": source.kind,
                "location": source.location,
                "error": str(exc),
            }
        )
        return

    for mcq in result.questions:
        question_store.create_from_mcq(material_id, mcq)
    material_store.update_status(material_id, "ready")
    message = message_store.create(chat_id, None, "system", _material_ready_message(result))
    await connection_manager.broadcast(chat_id, {"type": "message", **message})


@app.post("/chats/{chat_id}/materials", response_model=MaterialInfo, status_code=202)
async def upload_material(
    chat_id: int,
    kind: str = Form(...),
    location: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    label: str | None = Form(default=None),
    question_count: int = Form(default=10),
    user: dict = Depends(get_current_user),
    chats: ChatStore = Depends(get_chat_store),
    materials: MaterialStore = Depends(get_material_store),
    questions: QuestionStore = Depends(get_question_store),
    messages: MessageStore = Depends(get_message_store),
    manager: ConnectionManager = Depends(get_connection_manager),
    generator=Depends(get_material_generator),
    upload_dir: str = Depends(get_upload_dir),
    users: UserStore = Depends(get_user_store),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
) -> MaterialInfo:
    chat = _chat_in_course(chats, chat_id, user)
    if user["id"] not in chats.list_member_ids(chat_id):
        raise HTTPException(status_code=403, detail="Bu çatın üzvü deyilsiniz")
    # Limit FAYL SAXLANMAZDAN əvvəl: rədd olunan yükləmə diskə yazılmamalıdır.
    _enforce_upload_quota(user, users, materials, question_sets)

    if kind not in ("link", "pdf", "image"):
        raise HTTPException(status_code=400, detail="Naməlum material növü")
    if not (_MIN_QUESTION_COUNT <= question_count <= _MAX_QUESTION_COUNT):
        raise HTTPException(
            status_code=400,
            detail=f"Sual sayı {_MIN_QUESTION_COUNT}-{_MAX_QUESTION_COUNT} arasında olmalıdır",
        )

    if kind == "link":
        if not location:
            raise HTTPException(status_code=400, detail="Link üçün 'location' tələb olunur")
        source_location = location
    else:
        if file is None:
            raise HTTPException(status_code=400, detail="Fayl tələb olunur")
        try:
            source_location = await save_upload(
                file, upload_dir=upload_dir, max_bytes=MAX_UPLOAD_BYTES
            )
        except PayloadTooLarge:
            raise HTTPException(status_code=413, detail="Fayl çox böyükdür")

    material = materials.create(chat_id, user["id"], kind, source_location, label=label)

    task = asyncio.create_task(
        _process_material(
            material["id"],
            chat_id,
            MaterialSource(kind=kind, location=source_location, label=label),
            generator=generator,
            material_store=materials,
            question_store=questions,
            message_store=messages,
            connection_manager=manager,
            question_count=question_count,
            profile=_course_profile(users, chat["course_id"]),
        )
    )
    app.state.active_material_tasks[material["id"]] = task

    return MaterialInfo(**material)


@app.get("/chats/{chat_id}/materials", response_model=list[MaterialInfo])
def list_materials(
    chat_id: int,
    user: dict = Depends(get_current_user),
    chats: ChatStore = Depends(get_chat_store),
    materials: MaterialStore = Depends(get_material_store),
) -> list[MaterialInfo]:
    _chat_in_course(chats, chat_id, user)
    if user["id"] not in chats.list_member_ids(chat_id):
        raise HTTPException(status_code=403, detail="Bu çatın üzvü deyilsiniz")
    return [MaterialInfo(**m) for m in materials.list_by_chat(chat_id)]


def _question_set_info(qs: dict, question_count: int) -> QuestionSetInfo:
    return QuestionSetInfo(**qs, question_count=question_count)


async def _process_question_set(
    question_set_id: int,
    source: MaterialSource,
    *,
    generator,
    question_set_store: QuestionSetStore,
    question_count: int = 10,
    profile: str = "exam_prep",
    bank_kind: str = "practice",
    difficulty_mix: tuple[int, int, int] | None = None,
    summary_job: tuple[int, object, SummaryStore] | None = None,
) -> None:
    """Canlı sessiya sual bankını fon thread-ində emal edir — mövcud
    `_process_material`-a bənzər naxış, amma çat/mesaj sisteminə bağlı
    deyil (nəticə `question_sets.status`+`error` sahələrindən polling
    ilə oxunur, bax dizayn sənədi)."""
    try:
        result = await asyncio.to_thread(
            partial(
                generator, source, question_count, profile=profile, bank_kind=bank_kind,
                difficulty_mix=difficulty_mix,
            )
        )
    except Exception as exc:
        logger.exception("Sual bankı emalı uğursuz oldu (question_set_id=%s)", question_set_id)
        question_set_store.mark_failed(question_set_id, str(exc))
    else:
        if result.passage:
            question_set_store.set_passage(question_set_id, result.passage)
        for mcq in result.questions:
            question_set_store.add_question(question_set_id, mcq)
        question_set_store.mark_ready(question_set_id)

    # Xülasə (Faza 3) suallardan SONRA, ardıcıl: link materialında hər
    # emal Chrome açır və VPS-in yaddaşı iki paralel Chrome-a çatmır.
    # Suallar alınmasa da xülasə sınanır — səbəb fərqli ola bilər.
    if summary_job is not None:
        summary_id, summarizer, summaries = summary_job
        await _process_summary(summary_id, source, summarizer=summarizer, summaries=summaries)


@app.post("/live/question-sets", response_model=QuestionSetInfo, status_code=202)
async def create_question_set(
    subject: str = Form(...),
    title: str = Form(...),
    kind: str = Form(...),
    location: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    question_count: int = Form(default=10),
    bank_kind: str = Form(default="practice"),
    # Çətinlik bölgüsü (Faza 2, 2026-10-30) — cəmi 100. Köhnə client
    # göndərmirsə defolt bölgü işləyir (istifadəçi qərarı: 30/50/20).
    easy_percent: int = Form(default=DEFAULT_MIX[0]),
    medium_percent: int = Form(default=DEFAULT_MIX[1]),
    hard_percent: int = Form(default=DEFAULT_MIX[2]),
    # Dərs xülasəsi də hazırlansın (Faza 3, 2026-10-30).
    make_summary: bool = Form(default=False),
    user: dict = Depends(get_current_teacher),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    generator=Depends(get_material_generator),
    upload_dir: str = Depends(get_upload_dir),
    users: UserStore = Depends(get_user_store),
    materials: MaterialStore = Depends(get_material_store),
    summaries: SummaryStore = Depends(get_summary_store),
    summarizer=Depends(get_summarizer),
) -> QuestionSetInfo:
    _enforce_upload_quota(user, users, materials, question_sets)
    profile = _course_profile(users, user["course_id"])
    if bank_kind not in ("practice", "reading"):
        raise HTTPException(status_code=400, detail="Naməlum bank növü")
    if bank_kind == "reading" and profile != "english":
        raise HTTPException(status_code=400, detail="Reading bankı yalnız ingilis dili kursunda mövcuddur")
    if subject not in SUBJECTS:
        raise HTTPException(status_code=400, detail="Naməlum fənn")
    if kind not in ("link", "pdf", "image"):
        raise HTTPException(status_code=400, detail="Naməlum material növü")
    if not (_MIN_QUESTION_COUNT <= question_count <= _MAX_QUESTION_COUNT):
        raise HTTPException(
            status_code=400,
            detail=f"Sual sayı {_MIN_QUESTION_COUNT}-{_MAX_QUESTION_COUNT} arasında olmalıdır",
        )
    difficulty_mix = (easy_percent, medium_percent, hard_percent)
    try:
        validate_difficulty_mix(difficulty_mix)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Çətinlik bölgüsü: {exc}") from exc

    if kind == "link":
        if not location:
            raise HTTPException(status_code=400, detail="Link üçün 'location' tələb olunur")
        source_location = location
    else:
        if file is None:
            raise HTTPException(status_code=400, detail="Fayl tələb olunur")
        try:
            source_location = await save_upload(
                file, upload_dir=upload_dir, max_bytes=MAX_UPLOAD_BYTES
            )
        except PayloadTooLarge:
            raise HTTPException(status_code=413, detail="Fayl çox böyükdür")

    question_set = question_sets.create(
        subject=subject,
        title=title,
        material_kind=kind,
        material_location=source_location,
        created_by=user["id"],
        course_id=user["course_id"],
        profile=profile,
        bank_kind=bank_kind,
        difficulty_mix="/".join(str(p) for p in difficulty_mix),
    )
    summary_job = None
    if make_summary:
        summary = summaries.start(question_set["id"], created_by=user["id"], course_id=user["course_id"])
        summary_job = (summary["id"], summarizer, summaries)

    task = asyncio.create_task(
        _process_question_set(
            question_set["id"],
            MaterialSource(kind=kind, location=source_location),
            generator=generator,
            question_set_store=question_sets,
            question_count=question_count,
            profile=profile,
            bank_kind=bank_kind,
            difficulty_mix=difficulty_mix,
            summary_job=summary_job,
        )
    )
    app.state.active_question_set_tasks[question_set["id"]] = task

    return _question_set_info(question_set, question_count=0)


@app.get("/live/question-sets/{question_set_id}", response_model=QuestionSetInfo)
def get_question_set(
    question_set_id: int,
    user: dict = Depends(get_current_teacher),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
) -> QuestionSetInfo:
    question_set = _question_set_in_course(question_sets, question_set_id, user)
    count = question_sets.count_questions(question_set_id)
    return _question_set_info(question_set, question_count=count)


@app.get("/live/question-sets", response_model=list[QuestionSetInfo])
def list_question_sets(
    user: dict = Depends(get_current_teacher),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
) -> list[QuestionSetInfo]:
    return [
        _question_set_info(qs, question_count=question_sets.count_questions(qs["id"]))
        for qs in question_sets.list_all()
        if _same_course(qs["course_id"], user)
    ]


@app.get("/live/teacher-summary", response_model=TeacherSummary)
def teacher_summary(
    user: dict = Depends(get_current_teacher),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    homework: HomeworkStore = Depends(get_homework_store),
    live_sessions: LiveSessionStore = Depends(get_live_session_store),
) -> TeacherSummary:
    """Müəllim konsolunun bir sorğuluq xülasəsi.

    Bu məlumatlar bazada onsuz da var idi, sadəcə üç ayrı səhifəyə
    səpələnmişdi: müəllim «hansı tapşırıq son tarixə yaxınlaşır?»
    sualının cavabını heç yerdə görə bilmirdi.

    Sual banklarının sayı `GET /live/question-sets` ilə EYNİ əhatədədir
    (hamısı) ki, konsoldakı rəqəm siyahı ilə uyğun gəlsin.
    """
    all_sets = [qs for qs in question_sets.list_all() if _same_course(qs["course_id"], user)]
    counts = QuestionSetCounts(
        ready=sum(1 for qs in all_sets if qs["status"] == "ready"),
        processing=sum(1 for qs in all_sets if qs["status"] == "processing"),
        failed=sum(1 for qs in all_sets if qs["status"] == "failed"),
        total=len(all_sets),
    )

    titles = {qs["id"]: qs["title"] for qs in all_sets}

    assignments = homework.list_assignments_by_teacher(user["id"])
    next_due = None
    if assignments:
        # Ən yaxın son tarix: müəllimin dərhal görməli olduğu tapşırıq.
        nearest = min(assignments, key=lambda row: row["due_date"])
        next_due = NextDueAssignment(
            assignment_id=nearest["id"],
            title=titles.get(nearest["question_set_id"], "Sual bankı"),
            due_date=nearest["due_date"],
            started=len(homework.list_attempts_for_assignment(nearest["id"])),
        )

    session = live_sessions.latest_for_question_sets(list(titles))
    last_session = None
    if session is not None:
        last_session = LastSessionSummary(
            session_id=session["id"],
            title=titles.get(session["question_set_id"], "Sual bankı"),
            status=session["status"],
            participants=live_sessions.count_participants(session["id"]),
            created_at=session["created_at"],
        )

    return TeacherSummary(
        question_sets=counts,
        homework=HomeworkSummary(active=len(assignments), next_due=next_due),
        last_session=last_session,
    )


@app.get("/live/question-sets/{question_set_id}/questions", response_model=list[LiveQuestionInfo])
def list_live_questions(
    question_set_id: int,
    user: dict = Depends(get_current_teacher),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
) -> list[LiveQuestionInfo]:
    """Sual bankının BÜTÜN sualları, düzgün cavab+izah DAXİL — yalnız
    müəllim redaktə ekranı üçün (bax Sual redaktə/təsdiq ekranı, Faza 5).
    Tələbələrə göndərilən oyun payload-u (`_question_payload`) bunu
    QƏSDƏN göstərmir."""
    _question_set_in_course(question_sets, question_set_id, user)
    return [LiveQuestionInfo(**q) for q in question_sets.list_questions(question_set_id)]


@app.get("/live/question-sets/{question_set_id}/quality", response_model=QuestionSetQuality)
def question_set_quality(
    question_set_id: int,
    user: dict = Depends(get_current_teacher),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
) -> QuestionSetQuality:
    """Sual bankının keyfiyyət auditi — müəllimin hansı sualı ƏVVƏL
    oxumalı olduğunu göstərmək üçün.

    NİYƏ ENDPOINT LAZIMDIR: `pipeline/quality.py` alətini indiyədək
    yalnız VPS-də əl ilə skript kimi işlədirdik. Müəllim terminala girə
    bilmir — 30 sualı bərabər gözdən keçirməli olduğunu görüb praktikada
    heç birini oxumur. Audit yalnız müəllimin GÖRDÜYÜ yerdə dəyər verir.

    Sual nömrələri `GET .../questions` cavabının sırası ilə eynidir —
    hər ikisi `list_questions`-un çıxışını işlədir."""
    question_set = _question_set_in_course(question_sets, question_set_id, user)

    rows = question_sets.list_questions(question_set_id)
    try:
        questions = [
            MCQQuestion(
                question=row["question"],
                options=row["options"],
                correct_index=row["correct_index"],
                explanation=row["explanation"],
            )
            for row in rows
        ]
    except ValidationError as error:
        # Normal axında yarana bilməz (add/update hər ikisi 5 variantı
        # məcbur edir), amma köhnə/əl ilə dəyişdirilmiş data mümkündür.
        # BOŞ hesabat qaytarmaq OLMAZ: ekran «şübhə əlaməti tapılmadı»
        # yazar və auditin işlədiyini sandırar. Yalançı arxayınlıq
        # auditin heç olmamasından pisdir.
        raise HTTPException(
            status_code=409,
            detail="Bu bankdakı sual formatı gözlənilən deyil - audit hesablana bilmir.",
        ) from error
    # Yoxlama dəsti bankın profilinə görədir: ingilis bankında e-qanun
    # yoxlamaları mənasızdır, reading bankında mətnə istinad normaldır.
    report = audit_questions(
        questions, profile=question_set["profile"], bank_kind=question_set["bank_kind"]
    )
    return QuestionSetQuality(
        question_count=report.question_count,
        findings=[
            QualityFinding(
                code=finding.code,
                # `.value` MƏCBURİDİR: enum-un özü JSON-a `Severity.HIGH`
                # kimi düşərdi və client rəng seçə bilməzdi.
                severity=finding.severity.value,
                message=finding.message,
                question_number=finding.question_number,
            )
            for finding in report.findings
        ],
        review_order=report.review_order,
    )


@app.patch("/live/questions/{question_id}", response_model=LiveQuestionInfo)
def update_live_question(
    question_id: int,
    req: UpdateQuestionRequest,
    user: dict = Depends(get_current_teacher),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
) -> LiveQuestionInfo:
    _question_in_course(question_sets, question_id, user)
    updated = question_sets.update_question(
        question_id,
        question=req.question,
        options=req.options,
        correct_index=req.correct_index,
        explanation=req.explanation,
        difficulty=req.difficulty,
    )
    return LiveQuestionInfo(**updated)


@app.delete("/live/questions/{question_id}", status_code=204)
def delete_live_question(
    question_id: int,
    user: dict = Depends(get_current_teacher),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
) -> None:
    _question_in_course(question_sets, question_id, user)
    question_sets.delete_question(question_id)


# ---- Dərs xülasəsi (Faza 3, 2026-10-30) ---------------------------------
# Müəllim bankın materialından xülasə hazırladır, baxır/redaktə edir, sonra
# bir qrup çatına DƏRC edir. Tələbə yalnız dərc olunmuş xülasəni, yalnız
# üzvü olduğu çatda görür.


def _summary_info(summary: dict, question_set: dict | None, chats: ChatStore) -> SummaryInfo:
    chat = chats.get(summary["chat_id"]) if summary["chat_id"] else None
    return SummaryInfo(
        id=summary["id"],
        question_set_id=summary["question_set_id"],
        title=question_set["title"] if question_set else "",
        subject=question_set["subject"] if question_set else "",
        status=summary["status"],
        error=summary["error"],
        content=LessonSummary.model_validate_json(summary["content"]) if summary["content"] else None,
        chat_id=summary["chat_id"],
        chat_name=chat["name"] if chat else None,
        published_at=summary["published_at"],
        updated_at=summary["updated_at"],
    )


def _summary_in_course(summaries: SummaryStore, question_sets: QuestionSetStore,
                       summary_id: int, user: dict) -> tuple[dict, dict]:
    summary = summaries.get(summary_id)
    question_set = question_sets.get(summary["question_set_id"]) if summary else None
    if summary is None or question_set is None or not _same_course(question_set.get("course_id"), user):
        raise HTTPException(status_code=404, detail="Xülasə tapılmadı")
    return summary, question_set


async def _process_summary(summary_id: int, source: MaterialSource, *, summarizer,
                           summaries: SummaryStore) -> None:
    try:
        result = await asyncio.to_thread(summarizer, source)
    except Exception as exc:
        logger.exception("Xülasə emalı uğursuz oldu (summary_id=%s)", summary_id)
        summaries.mark_failed(summary_id, str(exc))
        return
    summaries.mark_ready(summary_id, result.model_dump_json())


@app.post("/live/question-sets/{question_set_id}/summary", response_model=SummaryInfo, status_code=202)
async def create_summary(
    question_set_id: int,
    user: dict = Depends(get_current_teacher),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    summaries: SummaryStore = Depends(get_summary_store),
    chats: ChatStore = Depends(get_chat_store),
    summarizer=Depends(get_summarizer),
) -> SummaryInfo:
    question_set = _question_set_in_course(question_sets, question_set_id, user)
    existing = summaries.get_for_question_set(question_set_id)
    if existing and existing["status"] == "processing":
        raise HTTPException(status_code=409, detail="Xülasə artıq hazırlanır")
    if existing and existing["published_at"]:
        # Dərc olunmuş mətni sükutla əvəzləmək tələbənin oxuduğunu dəyişərdi.
        raise HTTPException(status_code=409, detail="Xülasə dərc olunub - əvvəlcə dərcdən çıxarın")

    summary = summaries.start(question_set_id, created_by=user["id"], course_id=user["course_id"])
    task = asyncio.create_task(
        _process_summary(
            summary["id"],
            MaterialSource(kind=question_set["material_kind"], location=question_set["material_location"]),
            summarizer=summarizer,
            summaries=summaries,
        )
    )
    app.state.active_summary_tasks[summary["id"]] = task
    return _summary_info(summary, question_set, chats)


@app.get("/live/question-sets/{question_set_id}/summary", response_model=SummaryInfo)
def get_question_set_summary(
    question_set_id: int,
    user: dict = Depends(get_current_teacher),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    summaries: SummaryStore = Depends(get_summary_store),
    chats: ChatStore = Depends(get_chat_store),
) -> SummaryInfo:
    question_set = _question_set_in_course(question_sets, question_set_id, user)
    summary = summaries.get_for_question_set(question_set_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Xülasə tapılmadı")
    return _summary_info(summary, question_set, chats)


@app.put("/live/summaries/{summary_id}", response_model=SummaryInfo)
def update_summary(
    summary_id: int,
    req: LessonSummary,
    user: dict = Depends(get_current_teacher),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    summaries: SummaryStore = Depends(get_summary_store),
    chats: ChatStore = Depends(get_chat_store),
) -> SummaryInfo:
    summary, question_set = _summary_in_course(summaries, question_sets, summary_id, user)
    if summary["status"] != "ready":
        raise HTTPException(status_code=400, detail="Xülasə hələ hazır deyil")
    summaries.set_content(summary_id, req.model_dump_json())
    return _summary_info(summaries.get(summary_id), question_set, chats)


@app.post("/live/summaries/{summary_id}/publish", response_model=SummaryInfo)
def publish_summary(
    summary_id: int,
    req: PublishSummaryRequest,
    user: dict = Depends(get_current_teacher),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    summaries: SummaryStore = Depends(get_summary_store),
    chats: ChatStore = Depends(get_chat_store),
) -> SummaryInfo:
    summary, question_set = _summary_in_course(summaries, question_sets, summary_id, user)
    chat = _chat_in_course(chats, req.chat_id, user)
    if chat["kind"] != "group":
        raise HTTPException(status_code=400, detail="Xülasə yalnız qrup çatına dərc oluna bilər")
    if user["id"] not in chats.list_member_ids(req.chat_id):
        raise HTTPException(status_code=403, detail="Bu çatın üzvü deyilsiniz")
    if summary["status"] != "ready":
        raise HTTPException(status_code=400, detail="Xülasə hələ hazır deyil")
    summaries.publish(summary_id, req.chat_id)
    return _summary_info(summaries.get(summary_id), question_set, chats)


@app.post("/live/summaries/{summary_id}/unpublish", response_model=SummaryInfo)
def unpublish_summary(
    summary_id: int,
    user: dict = Depends(get_current_teacher),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    summaries: SummaryStore = Depends(get_summary_store),
    chats: ChatStore = Depends(get_chat_store),
) -> SummaryInfo:
    summary, question_set = _summary_in_course(summaries, question_sets, summary_id, user)
    summaries.unpublish(summary_id)
    return _summary_info(summaries.get(summary_id), question_set, chats)


@app.get("/me/summaries", response_model=list[SummaryInfo])
def list_my_summaries(
    user: dict = Depends(get_current_user),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    summaries: SummaryStore = Depends(get_summary_store),
    chats: ChatStore = Depends(get_chat_store),
) -> list[SummaryInfo]:
    """İstifadəçinin üzvü olduğu çatlara dərc olunmuş xülasələr."""
    # `list_by_user` kurs sahəsini qaytarmır — hər çat ayrıca yoxlanır.
    chat_ids = [
        c["id"] for c in chats.list_by_user(user["id"])
        if _same_course((chats.get(c["id"]) or {}).get("course_id"), user)
    ]
    return [
        _summary_info(s, question_sets.get(s["question_set_id"]), chats)
        for s in summaries.list_published_for_chats(chat_ids)
    ]


@app.get("/me/summaries/{summary_id}", response_model=SummaryInfo)
def get_my_summary(
    summary_id: int,
    user: dict = Depends(get_current_user),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    summaries: SummaryStore = Depends(get_summary_store),
    chats: ChatStore = Depends(get_chat_store),
) -> SummaryInfo:
    # Dərc olunmamış, başqa çatın və ya başqa kursun xülasəsi — hamısı
    # eyni 404: «var, amma sənin deyil» demirik.
    summary = summaries.get(summary_id)
    if (
        summary is None
        or not summary["published_at"]
        or summary["status"] != "ready"
        or user["id"] not in chats.list_member_ids(summary["chat_id"])
    ):
        raise HTTPException(status_code=404, detail="Xülasə tapılmadı")
    _chat_in_course(chats, summary["chat_id"], user)
    return _summary_info(summary, question_sets.get(summary["question_set_id"]), chats)


async def _reject_websocket(websocket: WebSocket, code: int, detail: str) -> None:
    """Qoşulmanı SƏBƏBİ ilə rədd edir.

    NİYƏ ƏVVƏLCƏ `accept()`: `accept()`-dən əvvəl `close()` çağırsaq,
    Starlette handshake-i rədd edir və brauzer HTTP 403 görür. Onda
    `onclose`-a **1006** (anormal) gəlir, bizim 4401/4403/4404/4409
    kodlarımız isə İTİR. Real brauzerdə ölçüldü (Chromium):

        accept()-siz close(4404)       -> brauzer 1006 görür
        accept() + mesaj + close(4404) -> brauzer 4404 görür

    Kod itdiyi üçün client-in `FATAL_CLOSE_CODES` yoxlaması işə düşmür
    və o, sonsuz yenidən qoşulur. Real produksiyada müəllimin canlı
    sessiya konsolu məhz belə hər 30 saniyədən bir 403 alırdı.

    Qoşulma qısa müddət qəbul edilir, amma HEÇ BİR məxfi məlumat
    göndərilmir — yalnız səbəb mətni.
    """
    await websocket.accept()
    try:
        await websocket.send_json({"type": "error", "detail": detail})
    except Exception:  # noqa: BLE001 - client artıq qaçıbsa əhəmiyyəti yoxdur
        pass
    await websocket.close(code=code)


_WS_SESSION_EXPIRED = "Sessiyanız bitib. Yenidən daxil olun."


def _ws_access_rejection(user: dict, users: UserStore) -> tuple[int, str] | None:
    """HTTP qapısının (`_access_problem`) WebSocket ekvivalenti:
    401 → 4401, 402 → 4402. WS marşrutları `get_current_user`-dən keçmir,
    ona görə qapı burada AYRICA çağırılmalıdır."""
    problem = _access_problem(user, users)
    if problem == 401:
        return 4401, _WS_SESSION_EXPIRED
    if problem == 402:
        return WS_CODE_LICENSE_CLOSED, LICENSE_CLOSED_DETAIL
    return None


@app.websocket("/ws/chat/{chat_id}")
async def chat_websocket(
    websocket: WebSocket,
    chat_id: int,
    token: str = Query(...),
    secret: str = Depends(get_token_secret),
    users: UserStore = Depends(get_user_store),
    chats: ChatStore = Depends(get_chat_store),
    messages: MessageStore = Depends(get_message_store),
    manager: ConnectionManager = Depends(get_connection_manager),
    sessions: QuizSessionStore = Depends(get_quiz_session_store),
    questions: QuestionStore = Depends(get_question_store),
    attempts: QuizAttemptStore = Depends(get_quiz_attempt_store),
) -> None:
    try:
        user_id = verify_token(token, secret=secret)
    except InvalidToken:
        await _reject_websocket(websocket, 4401, "Sessiyanız bitib. Yenidən daxil olun.")
        return
    user = users.get_by_id(user_id)
    if user is None:
        await _reject_websocket(websocket, 4401, "Sessiyanız bitib. Yenidən daxil olun.")
        return

    rejection = _ws_access_rejection(user, users)
    if rejection is not None:
        await _reject_websocket(websocket, *rejection)
        return

    chat = chats.get(chat_id)
    if chat is None or not _same_course(chat.get("course_id"), user):
        await _reject_websocket(websocket, 4404, "Bu çat tapılmadı.")
        return
    is_member = any(c["id"] == chat_id for c in chats.list_by_user(user_id))
    if not is_member:
        await _reject_websocket(websocket, 4403, "Bu çatın üzvü deyilsiniz.")
        return

    await websocket.accept()
    await websocket.send_json({"type": "history", "messages": messages.list_by_chat(chat_id)})
    manager.connect(chat_id, user_id, websocket)

    try:
        while True:
            try:
                data = await websocket.receive_json()
            except WebSocketDisconnect:
                raise
            except Exception:
                await websocket.send_json({"type": "error", "detail": "mesaj formatı düzgün deyil"})
                continue

            # Açıq bağlantı qapını YALNIZ qoşulanda keçib — kurs söhbət
            # ortasında bağlana bilər. Hər mesajda yoxlanır (bir PK
            # sorğusudur, keşə ehtiyac yoxdur).
            fresh_user = users.get_by_id(user_id)
            rejection = (
                (4401, _WS_SESSION_EXPIRED) if fresh_user is None
                else _ws_access_rejection(fresh_user, users)
            )
            if rejection is not None:
                code, detail = rejection
                await websocket.send_json({"type": "error", "detail": detail})
                await websocket.close(code=code)
                return

            if not isinstance(data, dict):
                await websocket.send_json({"type": "error", "detail": "mesaj formatı düzgün deyil"})
                continue

            msg_type = data.get("type")

            if msg_type == "text":
                content = data.get("content")
                if not isinstance(content, str) or not content.strip():
                    await websocket.send_json({"type": "error", "detail": "mesaj formatı düzgün deyil"})
                    continue
                message = messages.create(chat_id, user_id, "text", content)
                await manager.broadcast(chat_id, {"type": "message", **message})

            elif msg_type == "answer":
                question_id = data.get("question_id")
                chosen_index = data.get("chosen_index")
                if not isinstance(question_id, int) or not isinstance(chosen_index, int):
                    await websocket.send_json({"type": "error", "detail": "mesaj formatı düzgün deyil"})
                    continue

                before = sessions.get(chat_id)
                before_index = before["current_index"] if before else None
                try:
                    await record_answer(
                        chat_id,
                        user_id,
                        question_id,
                        chosen_index,
                        session_store=sessions,
                        question_store=questions,
                        attempt_store=attempts,
                        chat_store=chats,
                        message_store=messages,
                        connection_manager=manager,
                    )
                except (NotCurrentQuestion, AlreadyAnswered, QuizError) as exc:
                    await websocket.send_json({"type": "error", "detail": str(exc)})
                    continue

                # Cavab hamı tərəfindən tamamlanıb erkən keçidi tetiklədisə,
                # növbəti sual üçün yeni timeout planlaşdırılmalıdır.
                after = sessions.get(chat_id)
                if after is not None and after["status"] == "active" and after["current_index"] != before_index:
                    _schedule_timeout(
                        chat_id,
                        after["current_index"],
                        session_store=sessions,
                        question_store=questions,
                        attempt_store=attempts,
                        message_store=messages,
                        connection_manager=manager,
                    )

            else:
                await websocket.send_json({"type": "error", "detail": "mesaj formatı düzgün deyil"})
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(chat_id, user_id, websocket)


@app.post("/live/sessions", response_model=LiveSessionInfo, status_code=201)
async def create_live_session(
    req: CreateLiveSessionRequest,
    user: dict = Depends(get_current_teacher),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    live_sessions: LiveSessionStore = Depends(get_live_session_store),
    chats: ChatStore = Depends(get_chat_store),
    manager: ConnectionManager = Depends(get_connection_manager),
) -> LiveSessionInfo:
    """Sessiya bir SİNFƏ (qrup çatına) bağlı başlayır.

    İKİ ŞƏRT birlikdə: müəllim olmaq VƏ həmin çatın üzvü olmaq.
    Yalnız birincisi olsaydı, istənilən müəllim istənilən sinifdə
    sessiya aça bilərdi; yalnız ikincisi olsaydı, tələbə öz sinfində
    sessiya aça bilərdi. Spec qərarı: «çatdakı istənilən müəllim».
    """
    _chat_in_course(chats, req.chat_id, user)
    if user["id"] not in chats.list_member_ids(req.chat_id):
        raise HTTPException(status_code=403, detail="Bu çatın üzvü deyilsiniz")
    question_set = _question_set_in_course(question_sets, req.question_set_id, user)
    if question_set["status"] != "ready":
        raise HTTPException(status_code=400, detail="Sual bankı hələ hazır deyil")
    if question_set["bank_kind"] == "reading":
        # Canlı sessiyada mətn tələbənin qarşısında olmur — reading sualları
        # cavablana bilməz (istifadəçi qərarı: yalnız ev tapşırığında).
        raise HTTPException(
            status_code=400,
            detail="Reading bankı yalnız ev tapşırığı üçündür - canlı sessiyada mətn göstərilmir",
        )

    session = live_sessions.create_session(
        req.question_set_id, chat_id=req.chat_id, created_by=user["id"]
    )
    # Çatdakı HAMI dərhal görsün — istifadəçinin əsas tələbi bu idi.
    # `connection_manager.broadcast` onsuz da mövcuddur (mesajlar üçün),
    # yeni infrastruktur lazım deyil — yalnız yeni mesaj tipi.
    await manager.broadcast(
        req.chat_id,
        {
            "type": "live_session",
            "session_id": session["id"],
            "status": session["status"],
            "title": question_set["title"],
            "subject": question_set["subject"],
            "started_by": user["display_name"],
            "started_by_user_id": user["id"],
        },
    )
    return LiveSessionInfo(**session)


@app.get("/chats/{chat_id}/live-session", response_model=ChatLiveSessionInfo | None)
def get_chat_live_session(
    chat_id: int,
    user: dict = Depends(get_current_user),
    chats: ChatStore = Depends(get_chat_store),
    live_sessions: LiveSessionStore = Depends(get_live_session_store),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    users: UserStore = Depends(get_user_store),
) -> ChatLiveSessionInfo | None:
    """Çatın açıq sessiyası (varsa).

    NİYƏ YAYIMDAN ƏLAVƏ: WS yayımı yalnız O AN bağlı olanlara çatır.
    Sonradan çatı açan tələbə sessiyanı başqa cür görə bilməzdi.
    """
    _chat_in_course(chats, chat_id, user)
    if user["id"] not in chats.list_member_ids(chat_id):
        raise HTTPException(status_code=403, detail="Bu çatın üzvü deyilsiniz")

    session = live_sessions.active_for_chat(chat_id)
    if session is None:
        return None
    question_set = question_sets.get(session["question_set_id"])
    starter = users.get_by_id(session["created_by"]) if session["created_by"] else None
    return ChatLiveSessionInfo(
        session_id=session["id"],
        status=session["status"],
        title=question_set["title"] if question_set else "Canlı sessiya",
        subject=question_set["subject"] if question_set else "",
        started_by=starter["display_name"] if starter else "Müəllim",
        started_by_user_id=session["created_by"],
        pin=(session["pin"] or None) if user["is_teacher"] else None,
    )


@app.get("/live/sessions/{session_id}/report", response_model=LiveSessionReport)
def get_live_session_report(
    session_id: int,
    user: dict = Depends(get_current_teacher),
    live_sessions: LiveSessionStore = Depends(get_live_session_store),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    chats: ChatStore = Depends(get_chat_store),
) -> LiveSessionReport:
    session = live_sessions.get(session_id)
    if session is None or not _same_course(
        _session_course_id(session, chats, question_sets), user
    ):
        raise HTTPException(status_code=404, detail="Sessiya tapılmadı")
    if session["status"] != "finished":
        raise HTTPException(status_code=400, detail="Sessiya hələ bitməyib")

    if session["report_json"]:
        report = json.loads(session["report_json"])
    else:
        # Ehtiyat yolu — normalda `_finish_session_if_ready` sessiya
        # bitəndə hesabatı artıq hesablayıb keşləyib (bax live_session_runner.py).
        report = compute_live_report(
            session_id, session_store=live_sessions, question_set_store=question_sets
        )
    return LiveSessionReport(**report)


# ==== Ev təkrarı rejimi (Faza 2) ====================================
# WebSocket YOXDUR — asinxron, tək-oyunçulu rejim (bax dizayn sənədi,
# `docs/superpowers/specs/2026-09-07-masterai-homework-mode-design.md`).


def _homework_assignment_info(
    assignment: dict, *, chats: ChatStore, homework: HomeworkStore
) -> HomeworkAssignmentInfo:
    member_count = len(chats.list_member_ids(assignment["chat_id"]))
    completed_count = sum(
        1 for a in homework.list_attempts_for_assignment(assignment["id"]) if a["status"] == "completed"
    )
    return HomeworkAssignmentInfo(
        **assignment, completed_count=completed_count, total_members=member_count
    )


def _homework_question_payload(index: int, total: int, question: dict) -> HomeworkQuestionPayload:
    # correct_index/explanation QƏSDƏN yoxdur — cavab sızmasın (bax Faza-1-in eyni naxışı).
    return HomeworkQuestionPayload(
        index=index, total=total, question=question["question"], options=question["options"]
    )


def _homework_attempt_state(
    attempt: dict, questions: list[dict], passage: str | None = None
) -> HomeworkAttemptState:
    question = None
    if attempt["status"] != "completed":
        question = _homework_question_payload(
            attempt["current_question_index"], len(questions), questions[attempt["current_question_index"]]
        )
    return HomeworkAttemptState(
        attempt_id=attempt["id"],
        status=attempt["status"],
        current_question_index=attempt["current_question_index"],
        score=attempt["score"],
        question=question,
        passage=passage,
    )


def _homework_status_and_score(attempt: dict | None) -> tuple[str, int | None]:
    if attempt is None:
        return "gözləyir", None
    if attempt["status"] == "completed":
        return "tamamlanıb", attempt["score"]
    return "davam edir", None


@app.post("/homework/assignments", response_model=HomeworkAssignmentInfo, status_code=201)
def create_homework_assignment(
    req: CreateHomeworkAssignmentRequest,
    user: dict = Depends(get_current_user),
    chats: ChatStore = Depends(get_chat_store),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    homework: HomeworkStore = Depends(get_homework_store),
) -> HomeworkAssignmentInfo:
    if not user["is_teacher"]:
        raise HTTPException(status_code=403, detail="Yalnız müəllim tapşırıq təyin edə bilər")
    _chat_in_course(chats, req.chat_id, user)
    if user["id"] not in chats.list_member_ids(req.chat_id):
        raise HTTPException(status_code=403, detail="Bu çatın üzvü deyilsiniz")
    question_set = _question_set_in_course(question_sets, req.question_set_id, user)
    if question_set["status"] != "ready":
        raise HTTPException(status_code=400, detail="Sual bankı hələ hazır deyil")

    assignment = homework.create_assignment(
        req.chat_id, req.question_set_id, req.due_date, created_by=user["id"]
    )
    return _homework_assignment_info(assignment, chats=chats, homework=homework)


@app.get("/homework/assignments", response_model=list[HomeworkAssignmentInfo])
def list_homework_assignments(
    chat_id: int,
    user: dict = Depends(get_current_user),
    chats: ChatStore = Depends(get_chat_store),
    homework: HomeworkStore = Depends(get_homework_store),
) -> list[HomeworkAssignmentInfo]:
    _chat_in_course(chats, chat_id, user)
    if user["id"] not in chats.list_member_ids(chat_id):
        raise HTTPException(status_code=403, detail="Bu çatın üzvü deyilsiniz")
    assignments = [
        a for a in homework.list_assignments_for_chat(chat_id) if a["created_by"] == user["id"]
    ]
    return [_homework_assignment_info(a, chats=chats, homework=homework) for a in assignments]


@app.get("/homework/assignments/{assignment_id}/report", response_model=list[HomeworkReportRow])
def get_homework_report(
    assignment_id: int,
    user: dict = Depends(get_current_user),
    chats: ChatStore = Depends(get_chat_store),
    users: UserStore = Depends(get_user_store),
    homework: HomeworkStore = Depends(get_homework_store),
) -> list[HomeworkReportRow]:
    assignment = _assignment_in_course(homework, chats, assignment_id, user)
    if assignment["created_by"] != user["id"]:
        raise HTTPException(status_code=403, detail="Yalnız tapşırığı yaradan müəllim hesabata baxa bilər")

    attempts_by_student = {
        a["student_id"]: a for a in homework.list_attempts_for_assignment(assignment_id)
    }
    rows = []
    for member_id in chats.list_member_ids(assignment["chat_id"]):
        member = users.get_by_id(member_id)
        if member is None:
            continue
        status, score = _homework_status_and_score(attempts_by_student.get(member_id))
        rows.append(
            HomeworkReportRow(
                student_id=member_id, display_name=member["display_name"], status=status, score=score
            )
        )
    return rows


@app.get("/homework/assignments/{assignment_id}/difficulty", response_model=list[DifficultyStat])
def get_homework_difficulty_stats(
    assignment_id: int,
    user: dict = Depends(get_current_user),
    chats: ChatStore = Depends(get_chat_store),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    homework: HomeworkStore = Depends(get_homework_store),
) -> list[DifficultyStat]:
    """Tapşırıq üzrə çətinlik səviyyəsinə görə düzgün cavab payı.
    Ayrıca marşrutdur: `/report` siyahı qaytarır və köhnə client-lər onu
    siyahı kimi oxuyur — ona sahə əlavə etmək mümkün deyil."""
    assignment = _assignment_in_course(homework, chats, assignment_id, user)
    if assignment["created_by"] != user["id"]:
        raise HTTPException(status_code=403, detail="Yalnız tapşırığı yaradan müəllim hesabata baxa bilər")
    stats = homework.answer_stats_for_assignment(assignment_id)
    rows = [
        {"difficulty": q.get("difficulty"), "correct_count": stats.get(i, (0, 0))[0],
         "total_answers": stats.get(i, (0, 0))[1]}
        for i, q in enumerate(question_sets.list_questions(assignment["question_set_id"]))
    ]
    return [DifficultyStat(**row) for row in difficulty_breakdown(rows)]


@app.get("/homework/my-assignments", response_model=list[MyAssignmentInfo])
def list_my_assignments(
    user: dict = Depends(get_current_user),
    chats: ChatStore = Depends(get_chat_store),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    homework: HomeworkStore = Depends(get_homework_store),
) -> list[MyAssignmentInfo]:
    result = []
    for chat in chats.list_by_user(user["id"]):
        for assignment in homework.list_assignments_for_chat(chat["id"]):
            question_set = question_sets.get(assignment["question_set_id"])
            if question_set is None:
                continue
            status, score = _homework_status_and_score(
                homework.get_attempt_for_student(assignment["id"], user["id"])
            )
            result.append(
                MyAssignmentInfo(
                    assignment_id=assignment["id"],
                    chat_id=chat["id"],
                    subject=question_set["subject"],
                    title=question_set["title"],
                    due_date=assignment["due_date"],
                    status=status,
                    score=score,
                    question_count=question_sets.count_questions(question_set["id"]),
                )
            )
    return result


def _history_entries_for_student(
    student_id: int,
    *,
    live_sessions: LiveSessionStore,
    question_sets: QuestionSetStore,
    homework: HomeworkStore,
) -> list[HistoryEntry]:
    """Bir tələbənin canlı sessiya VƏ ev tapşırığı nəticələrini eyni
    xronoloji siyahıda birləşdirir (bax `/history/me`,
    `/history/student/{id}`). Canlı sessiya xalı `report_json`-dan
    (sessiya bitəndə bir dəfə hesablanıb keşlənib) çıxarılır — yenidən
    hesablanmır."""
    entries: list[HistoryEntry] = []

    for row in live_sessions.list_participations_for_user(student_id):
        question_set = question_sets.get(row["question_set_id"])
        if question_set is None or not row["report_json"]:
            continue
        report = json.loads(row["report_json"])
        own_row = next(
            (r for r in report.get("rankings", []) if r["participant_id"] == row["participant_id"]),
            None,
        )
        if own_row is None:
            continue
        entries.append(
            HistoryEntry(
                kind="live",
                subject=question_set["subject"],
                title=question_set["title"],
                score=own_row["score"],
                total_questions=report.get("total_questions", question_sets.count_questions(question_set["id"])),
                date=row["created_at"],
                session_id=row["session_id"],
            )
        )

    for attempt in homework.list_attempts_by_student(student_id):
        assignment = homework.get_assignment(attempt["assignment_id"])
        if assignment is None:
            continue
        question_set = question_sets.get(assignment["question_set_id"])
        if question_set is None:
            continue
        entries.append(
            HistoryEntry(
                kind="homework",
                subject=question_set["subject"],
                title=question_set["title"],
                score=attempt["score"],
                total_questions=question_sets.count_questions(question_set["id"]),
                date=attempt["completed_at"],
                chat_id=assignment["chat_id"],
            )
        )

    entries.sort(key=lambda e: e.date, reverse=True)
    return entries


@app.get("/history/me", response_model=list[HistoryEntry])
def get_my_history(
    user: dict = Depends(get_current_user),
    live_sessions: LiveSessionStore = Depends(get_live_session_store),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    homework: HomeworkStore = Depends(get_homework_store),
) -> list[HistoryEntry]:
    return _history_entries_for_student(
        user["id"], live_sessions=live_sessions, question_sets=question_sets, homework=homework
    )


@app.get("/history/student/{student_id}", response_model=list[HistoryEntry])
def get_student_history(
    student_id: int,
    user: dict = Depends(get_current_user),
    chats: ChatStore = Depends(get_chat_store),
    live_sessions: LiveSessionStore = Depends(get_live_session_store),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    homework: HomeworkStore = Depends(get_homework_store),
    users: UserStore = Depends(get_user_store),
) -> list[HistoryEntry]:
    """Müəllimin başqa bir tələbənin tarixçəsinə baxması — yalnız ortaq
    çatı olan (bax `list_chat_members`-in eyni naxışı) tələbələr üçün."""
    if not user["is_teacher"]:
        raise HTTPException(status_code=403, detail="Yalnız müəllim başqa tələbənin tarixçəsinə baxa bilər")
    student = users.get_by_id(student_id)
    if student is None or not _same_course(student["course_id"], user):
        raise HTTPException(status_code=404, detail="Tələbə tapılmadı")
    shares_chat = any(
        student_id in chats.list_member_ids(chat["id"]) for chat in chats.list_by_user(user["id"])
    )
    if not shares_chat:
        raise HTTPException(status_code=403, detail="Bu tələbə ilə ortaq çatınız yoxdur")
    return _history_entries_for_student(
        student_id, live_sessions=live_sessions, question_sets=question_sets, homework=homework
    )


_BADGE_TYPES = ("ilk_addim", "yuz_faiz", "fenn_ustasi", "suretli_eqli", "silsile_5")
_SURETLI_EQLI_MAX_MINUTES = 3
_FENN_USTASI_MIN_COUNT = 5
_SILSILE_MIN_DAYS = 5


def _evaluate_badges(
    student_id: int,
    *,
    live_sessions: LiveSessionStore,
    question_sets: QuestionSetStore,
    homework: HomeworkStore,
    badges: BadgeStore,
) -> list[BadgeInfo]:
    """5 nişan meyarını yoxlayır, YENİ qazananları `badges.mark_earned`-ə
    yazır (tənbəl hesablama — bax Faza 6 dizayn sənədi). Mövcud
    `_history_entries_for_student`-i (Faza 3) yenidən istifadə edir,
    yalnız "sürətli əqli" üçün ev tapşırığı cəhdlərinin xam
    (`started_at`/`completed_at`) datasına ayrıca müraciət edir."""
    entries = _history_entries_for_student(
        student_id, live_sessions=live_sessions, question_sets=question_sets, homework=homework
    )
    attempts = homework.list_attempts_by_student(student_id)

    newly_qualified: set[str] = set()

    if entries:
        newly_qualified.add("ilk_addim")

    if any(e.total_questions > 0 and e.score == e.total_questions for e in entries):
        newly_qualified.add("yuz_faiz")

    subject_counts: dict[str, int] = {}
    for e in entries:
        if e.kind == "homework":
            subject_counts[e.subject] = subject_counts.get(e.subject, 0) + 1
    if any(count >= _FENN_USTASI_MIN_COUNT for count in subject_counts.values()):
        newly_qualified.add("fenn_ustasi")

    for attempt in attempts:
        started = datetime.fromisoformat(attempt["started_at"])
        completed = datetime.fromisoformat(attempt["completed_at"])
        if (completed - started).total_seconds() < _SURETLI_EQLI_MAX_MINUTES * 60:
            newly_qualified.add("suretli_eqli")
            break

    distinct_days = {datetime.fromisoformat(e.date).date() for e in entries}
    if len(distinct_days) >= _SILSILE_MIN_DAYS:
        newly_qualified.add("silsile_5")

    for badge_type in newly_qualified:
        badges.mark_earned(student_id, badge_type)

    earned = badges.get_earned(student_id)
    return [
        BadgeInfo(badge_type=bt, earned=bt in earned, earned_at=earned.get(bt))
        for bt in _BADGE_TYPES
    ]


@app.get("/badges/me", response_model=list[BadgeInfo])
def get_my_badges(
    user: dict = Depends(get_current_user),
    live_sessions: LiveSessionStore = Depends(get_live_session_store),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    homework: HomeworkStore = Depends(get_homework_store),
    badges: BadgeStore = Depends(get_badge_store),
) -> list[BadgeInfo]:
    return _evaluate_badges(
        user["id"],
        live_sessions=live_sessions,
        question_sets=question_sets,
        homework=homework,
        badges=badges,
    )


@app.post("/homework/assignments/{assignment_id}/start", response_model=HomeworkAttemptState)
def start_homework_attempt(
    assignment_id: int,
    user: dict = Depends(get_current_user),
    chats: ChatStore = Depends(get_chat_store),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    homework: HomeworkStore = Depends(get_homework_store),
) -> HomeworkAttemptState:
    assignment = _assignment_in_course(homework, chats, assignment_id, user)
    if user["id"] not in chats.list_member_ids(assignment["chat_id"]):
        raise HTTPException(status_code=403, detail="Bu çatın üzvü deyilsiniz")

    questions = question_sets.list_questions(assignment["question_set_id"])
    attempt = homework.get_or_create_attempt(assignment_id, student_id=user["id"])
    return _homework_attempt_state(
        attempt, questions, passage=question_sets.get_passage(assignment["question_set_id"])
    )


@app.post("/homework/attempts/{attempt_id}/answer", response_model=HomeworkAnswerResult)
def answer_homework_question(
    attempt_id: int,
    req: HomeworkAnswerRequest,
    user: dict = Depends(get_current_user),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    homework: HomeworkStore = Depends(get_homework_store),
) -> HomeworkAnswerResult:
    attempt = homework.get_attempt(attempt_id)
    # Başqasının cəhdi «tapılmadı» — 403 cəhd ID-lərinin mövcudluğunu açardı.
    if attempt is None or attempt["student_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Cəhd tapılmadı")

    assignment = homework.get_assignment(attempt["assignment_id"])
    questions = question_sets.list_questions(assignment["question_set_id"])
    if not 0 <= req.question_index < len(questions):
        raise HTTPException(status_code=400, detail="Sual indeksi düzgün deyil")

    question = questions[req.question_index]
    is_correct = req.chosen_index == question["correct_index"]
    try:
        updated = homework.answer(
            attempt_id, req.question_index, req.chosen_index, is_correct,
            total_questions=len(questions),
        )
    except (HomeworkNotCurrentQuestion, AttemptAlreadyCompleted) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    next_question = None
    if updated["status"] != "completed":
        next_question = _homework_question_payload(
            updated["current_question_index"], len(questions), questions[updated["current_question_index"]]
        )
    return HomeworkAnswerResult(
        is_correct=is_correct,
        correct_index=question["correct_index"],
        explanation=question["explanation"],
        next_question=next_question,
    )


def _schedule_live_duration_watch(
    session_id: int,
    duration_seconds: float,
    *,
    session_store: LiveSessionStore,
    question_set_store: QuestionSetStore,
    connection_manager: LiveConnectionManager,
) -> None:
    """Sessiya başlayanda BİR DƏFƏLİK planlaşdırılır — ümumi vaxt büdcəsi
    bitəndə sessiyanı zorla bitirir (bax `live_session_runner.
    watch_session_duration`, fərdi templi modeldə sual-üzrə timeout YOXDUR)."""
    task = asyncio.create_task(
        watch_live_session_duration(
            session_id,
            duration_seconds,
            session_store=session_store,
            question_set_store=question_set_store,
            connection_manager=connection_manager,
        )
    )
    app.state.active_live_timeouts[session_id] = task


async def _run_host_loop(
    websocket: WebSocket, session: dict, *, question_sets, live_sessions, manager
) -> None:
    """Host mesaj döngüsü.

    Marşrutun gövdəsindən AYRI saxlanılır: icazə yoxlaması (kim bu
    konsolu aça bilər) ilə mesaj emalı iki ayrı məsələdir və bir
    funksiyada qarışdıqda hər ikisi çətin oxunur.
    """
    while True:
        try:
            data = await websocket.receive_json()
        except WebSocketDisconnect:
            raise
        except Exception:
            await websocket.send_json({"type": "error", "detail": "mesaj formatı düzgün deyil"})
            continue

        if not isinstance(data, dict):
            await websocket.send_json({"type": "error", "detail": "mesaj formatı düzgün deyil"})
            continue

        if data.get("action") == "start":
            duration_seconds = data.get("duration_seconds")
            if not isinstance(duration_seconds, int) or duration_seconds <= 0:
                duration_seconds = DEFAULT_SESSION_DURATION_SECONDS
            try:
                await start_live_session(
                    session["id"], duration_seconds,
                    session_store=live_sessions, question_set_store=question_sets,
                    connection_manager=manager,
                )
            except LiveSessionError as exc:
                await websocket.send_json({"type": "error", "detail": str(exc)})
                continue
            _schedule_live_duration_watch(
                session["id"], duration_seconds,
                session_store=live_sessions, question_set_store=question_sets,
                connection_manager=manager,
            )
        else:
            await websocket.send_json({"type": "error", "detail": "mesaj formatı düzgün deyil"})


async def _run_play_loop(
    websocket: WebSocket, session_id: int, participant_id: int,
    *, question_sets, live_sessions, manager,
) -> None:
    """Tələbə mesaj döngüsü (yuxarıdakı eyni səbəb)."""
    while True:
        try:
            data = await websocket.receive_json()
        except WebSocketDisconnect:
            raise
        except Exception:
            await websocket.send_json({"type": "error", "detail": "mesaj formatı düzgün deyil"})
            continue

        if not isinstance(data, dict) or data.get("type") not in ("answer", "next"):
            await websocket.send_json({"type": "error", "detail": "mesaj formatı düzgün deyil"})
            continue

        if data.get("type") == "next":
            try:
                await request_next_live_question(
                    session_id, participant_id,
                    session_store=live_sessions, question_set_store=question_sets,
                    connection_manager=manager,
                )
            except LiveSessionError as exc:
                await websocket.send_json({"type": "error", "detail": str(exc)})
            continue

        question_index = data.get("question_index")
        chosen_index = data.get("chosen_index")
        if not isinstance(question_index, int) or not isinstance(chosen_index, int):
            await websocket.send_json({"type": "error", "detail": "mesaj formatı düzgün deyil"})
            continue

        try:
            await record_live_answer(
                session_id, participant_id, question_index, chosen_index,
                session_store=live_sessions, question_set_store=question_sets,
                connection_manager=manager,
            )
        except (LiveNotCurrentQuestion, LiveAlreadyAnswered, LiveSessionTimeExpired, LiveSessionError) as exc:
            await websocket.send_json({"type": "error", "detail": str(exc)})


def _live_session_membership(
    session: dict, user_id: int, chats: ChatStore
) -> bool:
    """Bu istifadəçi sessiyanın çatının üzvüdürmü?

    Sessiya ID-ləri `AUTOINCREMENT`, yəni ARDICIL — üzvlük yoxlanmasa,
    1-dən saymaqla qonşu sinfin sessiyasına girmək olardı (eyni səhv
    çata qoşulmada da vardı, bax `POST /chats/{id}/join` silinməsi).
    """
    if session.get("chat_id") is None:
        return False
    return user_id in chats.list_member_ids(session["chat_id"])


def _live_access_rejection(
    user: dict, users: UserStore, session: dict
) -> tuple[int, str] | None:
    """Canlı sessiya üçün qapı — istifadəçi qərarı: «başlamış sessiya
    sonuna qədər getsin». Kurs bağlansa da `active` sessiyaya qoşulma
    və yenidən qoşulma (telefon kilidlənib qayıdır) açıqdır; sessiyanın
    özünün maksimum 10 dəqiqəlik vaxt büdcəsi onu məhdudlaşdırır.
    Başlamamış (`waiting`) sessiya isə başladıla bilməz.
    `is_active=0` HƏR HALDA rədd olunur — çıxarılmış tələbə yox."""
    rejection = _ws_access_rejection(user, users)
    if (
        rejection is not None
        and rejection[0] == WS_CODE_LICENSE_CLOSED
        and session["status"] == "active"
    ):
        return None
    return rejection


@app.websocket("/ws/live/sessions/{session_id}/host")
async def live_host_by_session_websocket(
    websocket: WebSocket,
    session_id: int,
    token: str = Query(...),
    secret: str = Depends(get_token_secret),
    users: UserStore = Depends(get_user_store),
    chats: ChatStore = Depends(get_chat_store),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    live_sessions: LiveSessionStore = Depends(get_live_session_store),
    manager: LiveConnectionManager = Depends(get_live_connection_manager),
) -> None:
    """Host konsolu — YALNIZ sessiyanı BAŞLADAN müəllim.

    Çatda bir neçə müəllim ola bilər, amma iki nəfər eyni anda idarə
    etsə (start, vaxt limiti), sinifdə nə baş verdiyi anlaşılmaz
    olardı. Spec qərarı: konsol sessiyanı başladanındır.

    Rədd HƏMİŞƏ `accept()`-dən SONRA və səbəb kodu ilə olur —
    `accept()`-dən əvvəl bağlansa, brauzerə 1006 çatır və client
    sonsuz yenidən qoşulur (real produksiyada baş verib).
    """
    try:
        user_id = verify_token(token, secret=secret)
    except InvalidToken:
        await _reject_websocket(websocket, 4401, "Sessiyanız bitib. Yenidən daxil olun.")
        return
    user = users.get_by_id(user_id)
    if user is None:
        await _reject_websocket(websocket, 4401, "Sessiyanız bitib. Yenidən daxil olun.")
        return

    session = live_sessions.get(session_id)
    if session is None or session["status"] == "finished":
        await _reject_websocket(
            websocket, 4404,
            "Bu sessiya artıq bitib və ya tapılmadı. Çatdan yenisini başladın.",
        )
        return
    rejection = _live_access_rejection(user, users, session)
    if rejection is not None:
        await _reject_websocket(websocket, *rejection)
        return
    if not _same_course(_session_course_id(session, chats, question_sets), user):
        await _reject_websocket(websocket, 4404, "Bu sessiya tapılmadı.")
        return
    if (
        not user["is_teacher"]
        or session["created_by"] != user_id
        or not _live_session_membership(session, user_id, chats)
    ):
        await _reject_websocket(
            websocket, 4403, "Bu sessiyanı yalnız onu başladan müəllim idarə edə bilər."
        )
        return

    await websocket.accept()
    manager.connect_host(session["id"], websocket)
    await websocket.send_json(
        {
            "type": "state",
            "session_id": session["id"],
            "status": session["status"],
            "pin": session["pin"],
            "participants": live_sessions.list_participants(session["id"]),
        }
    )

    try:
        await _run_host_loop(
            websocket, session,
            question_sets=question_sets, live_sessions=live_sessions, manager=manager,
        )
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect_host(session["id"], websocket)


@app.websocket("/ws/live/sessions/{session_id}/play")
async def live_play_by_session_websocket(
    websocket: WebSocket,
    session_id: int,
    token: str = Query(default=""),
    secret: str = Depends(get_token_secret),
    users: UserStore = Depends(get_user_store),
    chats: ChatStore = Depends(get_chat_store),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    live_sessions: LiveSessionStore = Depends(get_live_session_store),
    manager: LiveConnectionManager = Depends(get_live_connection_manager),
) -> None:
    """Tələbə bağlantısı — token MƏCBURİDİR.

    Köhnə PIN yolunda token KÖNÜLLÜ idi və tokensiz iştirakçı heç bir
    hesaba bağlanmırdı (fərdi tarixçə buna görə boş qalırdı). Burada
    ad da yazılmır — hesabdan götürülür.
    """
    try:
        user_id = verify_token(token, secret=secret)
    except InvalidToken:
        await _reject_websocket(websocket, 4401, "Sessiyanız bitib. Yenidən daxil olun.")
        return
    user = users.get_by_id(user_id)
    if user is None:
        await _reject_websocket(websocket, 4401, "Sessiyanız bitib. Yenidən daxil olun.")
        return

    session = live_sessions.get(session_id)
    if session is None or session["status"] == "finished":
        await _reject_websocket(
            websocket, 4404, "Bu sessiya artıq bitib və ya tapılmadı."
        )
        return
    rejection = _live_access_rejection(user, users, session)
    if rejection is not None:
        await _reject_websocket(websocket, *rejection)
        return
    if not _same_course(_session_course_id(session, chats, question_sets), user):
        await _reject_websocket(websocket, 4404, "Bu sessiya tapılmadı.")
        return
    if not _live_session_membership(session, user_id, chats):
        await _reject_websocket(websocket, 4403, "Bu sinfin üzvü deyilsiniz.")
        return

    await websocket.accept()
    try:
        session, participant = await join_live_session(
            session["id"], user["display_name"],
            session_store=live_sessions, connection_manager=manager, user_id=user_id,
        )
    except LiveSessionError as exc:
        await websocket.send_json({"type": "error", "detail": str(exc)})
        await websocket.close(code=4404)
        return
    await _serve_player(
        websocket, session, participant,
        question_sets=question_sets, live_sessions=live_sessions, manager=manager,
    )


async def _serve_player(
    websocket: WebSocket, session: dict, participant: dict,
    *, question_sets, live_sessions, manager,
) -> None:
    """Qoşulmadan SONRAKI hissə — hesablı və PIN (qonaq) yolu üçün eyni."""
    manager.connect_player(session["id"], participant["id"], websocket)
    await websocket.send_json(
        {"type": "joined", "participant_id": participant["id"], "session_id": session["id"]}
    )

    # GEC QOŞULMA: sessiya artıq işləyirsə, `start` yayımı çoxdan
    # keçib — heç nə göndərilməsə tələbə boş ekrana baxardı.
    # `request_next` yeni iştirakçı üçün 0-cı sualı göndərir (indeks
    # cavab sayından törəyir).
    if session["status"] == "active":
        try:
            await request_next_live_question(
                session["id"], participant["id"],
                session_store=live_sessions, question_set_store=question_sets,
                connection_manager=manager,
            )
        except LiveSessionError as exc:
            await websocket.send_json({"type": "error", "detail": str(exc)})

    try:
        await _run_play_loop(
            websocket, session["id"], participant["id"],
            question_sets=question_sets, live_sessions=live_sessions, manager=manager,
        )
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect_player(session["id"], participant["id"], websocket)


# ==== PIN ilə qonaq qoşulması (2026-10-30, istifadəçi qərarı) ==========
# 2026-09-11-də silinmişdi, «əvvəlki formada» qayıdır: hesabsız tələbə
# `qosul.html`-də PIN (və ya `qosul.html?pin=...` linki) + ad yazır.
# Host konsolu PIN-lə AÇILMIR — o, sessiya ID-si və müəllim tokeni ilə
# qalır. Qonağın nəticəsi sessiya hesabatına düşür, tarixçəyə, nişanlara
# və liderlik lövhəsinə isə düşmür (bunlar `user_id` üzrə qurulub).

# Kursda `seat_limit` yoxdursa da qonaq sayı sonsuz olmamalıdır.
GUEST_HARD_CAP = 200
GUEST_NAME_MAX = 40
_GUEST_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_PIN_RE = re.compile(r"^[0-9]{6}$")
_PIN_NOT_FOUND = "Bu PIN ilə aktiv sessiya tapılmadı. Rəqəmləri yoxlayın."
_PIN_TOO_MANY = "Çox sayda səhv PIN. Bir dəqiqə sonra yenidən yoxlayın."


def _ws_client_ip(websocket: WebSocket) -> str:
    """`_client_ip`-in WebSocket ekvivalenti (eyni nginx fərziyyəsi)."""
    forwarded = websocket.headers.get("x-real-ip")
    if forwarded:
        return forwarded.strip()
    return websocket.client.host if websocket.client else "naməlum"


def _clean_guest_name(name: str) -> str | None:
    cleaned = " ".join((name or "").split())
    if not cleaned or len(cleaned) > GUEST_NAME_MAX:
        return None
    return cleaned


def _pin_session(
    pin: str, users: UserStore, chats: ChatStore,
    question_sets: QuestionSetStore, live_sessions: LiveSessionStore,
) -> tuple[dict, dict] | None:
    """PIN-in sessiyası və kursu — qonaq üçün ikisi birlikdə lazımdır.

    Kurs lisenziyası bağlıdırsa YENİ sessiyaya qonaq buraxılmır;
    işləyən (`active`) sessiya isə sonuna qədər gedir — hesablı yolun
    eyni qaydası (bax `_live_access_rejection`).
    """
    if not _PIN_RE.match(pin or ""):
        return None
    session = live_sessions.get_by_pin(pin)
    if session is None:
        return None
    course = users.courses.get(_session_course_id(session, chats, question_sets))
    if course is None:
        return None
    if session["status"] != "active" and not course_is_open(course, _utcnow()):
        return None
    return session, course


@app.get("/live/pin/{pin}", response_model=LivePinLookup)
def lookup_live_pin(
    pin: str,
    request: Request,
    users: UserStore = Depends(get_user_store),
    chats: ChatStore = Depends(get_chat_store),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    live_sessions: LiveSessionStore = Depends(get_live_session_store),
    limiter: RateLimiter = Depends(get_pin_rate_limiter),
) -> LivePinLookup:
    """Hesabsız — qonağın tokeni yoxdur. Yalnız başlıq qaytarılır."""
    ip = _client_ip(request)
    if limiter.is_blocked(ip):
        raise HTTPException(status_code=429, detail=_PIN_TOO_MANY)
    found = _pin_session(pin, users, chats, question_sets, live_sessions)
    if found is None:
        limiter.record(ip)
        raise HTTPException(status_code=404, detail=_PIN_NOT_FOUND)
    session, _course = found
    question_set = question_sets.get(session["question_set_id"])
    return LivePinLookup(
        title=question_set["title"] if question_set else "Canlı sessiya",
        subject=question_set["subject"] if question_set else "",
        status=session["status"],
    )


@app.websocket("/ws/live/pin/{pin}/play")
async def live_play_by_pin_websocket(
    websocket: WebSocket,
    pin: str,
    name: str = Query(default=""),
    guest: str = Query(default=""),
    token: str = Query(default=""),
    secret: str = Depends(get_token_secret),
    users: UserStore = Depends(get_user_store),
    chats: ChatStore = Depends(get_chat_store),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    live_sessions: LiveSessionStore = Depends(get_live_session_store),
    manager: LiveConnectionManager = Depends(get_live_connection_manager),
    limiter: RateLimiter = Depends(get_pin_rate_limiter),
) -> None:
    """PIN ilə qoşulma. İki hal:

    1. Token var, keçərlidir və tələbə həmin sinfin üzvüdür — hesablı
       iştirakçı kimi qoşulur (nəticə tarixçəsinə düşür). Çatdakı
       «Qoşul» düyməsi ilə eyni nəticə.
    2. Əks halda — qonaq: ad və brauzer açarı (`guest`) məcburidir.
    """
    ip = _ws_client_ip(websocket)
    if limiter.is_blocked(ip):
        await _reject_websocket(websocket, 4429, _PIN_TOO_MANY)
        return
    found = _pin_session(pin, users, chats, question_sets, live_sessions)
    if found is None:
        limiter.record(ip)
        await _reject_websocket(websocket, 4404, _PIN_NOT_FOUND)
        return
    session, course = found

    member = None
    if token:
        try:
            user = users.get_by_id(verify_token(token, secret=secret))
        except InvalidToken:
            user = None
        if (
            user is not None
            and _live_access_rejection(user, users, session) is None
            and _same_course(course["id"], user)
            and _live_session_membership(session, user["id"], chats)
        ):
            member = user

    if member is not None:
        join_kwargs = {"user_id": member["id"]}
        display_name = member["display_name"]
    else:
        display_name = _clean_guest_name(name)
        if display_name is None:
            await _reject_websocket(
                websocket, 4400, f"Adınızı yazın (ən çox {GUEST_NAME_MAX} simvol)."
            )
            return
        if not _GUEST_KEY_RE.match(guest):
            await _reject_websocket(websocket, 4400, "Brauzer açarı düzgün deyil. Səhifəni yeniləyin.")
            return
        if live_sessions.find_guest(session["id"], guest) is None:
            cap = min(course["seat_limit"] or GUEST_HARD_CAP, GUEST_HARD_CAP)
            if live_sessions.count_guests(session["id"]) >= cap:
                await _reject_websocket(
                    websocket, 4409, "Sessiya doludur - müəllimə yaxınlaşın."
                )
                return
        join_kwargs = {"guest_key": guest}

    await websocket.accept()
    try:
        session, participant = await join_live_session(
            session["id"], display_name,
            session_store=live_sessions, connection_manager=manager, **join_kwargs,
        )
    except LiveSessionError as exc:
        await websocket.send_json({"type": "error", "detail": str(exc)})
        await websocket.close(code=4404)
        return
    await _serve_player(
        websocket, session, participant,
        question_sets=question_sets, live_sessions=live_sessions, manager=manager,
    )
