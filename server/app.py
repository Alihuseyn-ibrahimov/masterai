"""MasterAI backend FastAPI tətbiqi.

Auth (/auth/register, /auth/login, /health) + əsas çat (POST/GET /chats,
/chats/{id}/join, WS /ws/chat/{id}) + AI quiz orkestrasiyası
(POST /chats/{id}/quiz/start, WS "answer" mesaj tipi).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime

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
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from pydantic import ValidationError

from pipeline.models import MaterialSource, MCQQuestion
from pipeline.pipeline import generate_quiz
from pipeline.quality import audit_questions

from .auth import InvalidToken, create_token, hash_password, token_secret, verify_password, verify_token
from .badge_store import BadgeStore
from .chat_store import ChatStore
from .connection_manager import ConnectionManager
from .friendship_store import AlreadyFriends, DuplicateFriendship, FriendshipStore
from .homework_store import AttemptAlreadyCompleted, HomeworkStore
from .homework_store import NotCurrentQuestion as HomeworkNotCurrentQuestion
from .live_connection_manager import LiveConnectionManager
from .live_session_runner import AlreadyAnswered as LiveAlreadyAnswered
from .live_session_runner import DEFAULT_SESSION_DURATION_SECONDS
from .live_session_runner import LiveSessionError
from .live_session_runner import NotCurrentQuestion as LiveNotCurrentQuestion
from .live_session_runner import SessionNotFound as LiveSessionNotFound
from .live_session_runner import SessionNotJoinable as LiveSessionNotJoinable
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
    HomeworkSummary,
    LastSessionSummary,
    NextDueAssignment,
    QuestionSetCounts,
    TeacherSummary,
    AdminStatsInfo,
    AuthResponse,
    BadgeInfo,
    ChatInfo,
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
    LeaderboardRow,
    LiveQuestionInfo,
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
from .uploads import PayloadTooLarge, save_upload
from .user_store import DuplicateEmail, UserStore

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
_DEFAULT_UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")

# Müəllimin material yükləyəndə təyin edə biləcəyi ümumi sual sayı aralığı
# (bax `pipeline.generate_quiz`, `target_question_count`).
_MIN_QUESTION_COUNT = 3
_MAX_QUESTION_COUNT = 30

app = FastAPI(title="MasterAI")
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
# chat_id -> planlaşdırılmış timeout task-ı (strong reference — Python-un
# arayışsız task-ı vaxtından əvvəl çöp yığmaması üçün).
app.state.active_quiz_timeouts = {}
# material_id -> planlaşdırılmış fon emalı task-ı (eyni naxış).
app.state.active_material_tasks = {}
# question_set_id -> planlaşdırılmış fon emalı task-ı (eyni naxış).
app.state.active_question_set_tasks = {}
# live_session_id -> planlaşdırılmış timeout task-ı (eyni naxış).
app.state.active_live_timeouts = {}


def get_user_store() -> UserStore:
    """İstifadəçi hesabları store-u (testdə `:memory:` ilə override olunur)."""
    return app.state.user_store


def get_chat_store() -> ChatStore:
    """Çat store-u (testdə `:memory:` ilə override olunur)."""
    return app.state.chat_store


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
    return user


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
    )


@app.post("/auth/register", response_model=AuthResponse, status_code=201)
def auth_register(
    req: RegisterRequest,
    store: UserStore = Depends(get_user_store),
    secret: str = Depends(get_token_secret),
) -> AuthResponse:
    try:
        user = store.create(req.email, hash_password(req.password), req.display_name)
    except DuplicateEmail:
        raise HTTPException(status_code=409, detail="Bu e-poçt artıq qeydiyyatdadır")
    return AuthResponse(token=create_token(user["id"], secret=secret), user=_user_info(user))


@app.post("/auth/login", response_model=AuthResponse)
def auth_login(
    req: LoginRequest,
    store: UserStore = Depends(get_user_store),
    secret: str = Depends(get_token_secret),
) -> AuthResponse:
    user = store.get_by_email(req.email)
    # Naməlum e-poçt və səhv şifrə EYNİ cavabı verir — hansı e-poçtların
    # qeydiyyatda olduğunu üzə çıxarmamaq üçün.
    if user is None or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="E-poçt və ya şifrə səhvdir")
    return AuthResponse(token=create_token(user["id"], secret=secret), user=_user_info(user))


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
    if target is None:
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
    return [_user_info(t) for t in users.list_teachers()]


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
    )


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
    if addressee is None:
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


def _get_friendship_or_404(friendship_id: int, friendships: FriendshipStore) -> dict:
    friendship = friendships.get(friendship_id)
    if friendship is None:
        raise HTTPException(status_code=404, detail="Dostluq sorğusu tapılmadı")
    return friendship


@app.post("/friends/requests/{friendship_id}/accept", response_model=FriendshipInfo)
def accept_friend_request(
    friendship_id: int,
    user: dict = Depends(get_current_user),
    friendships: FriendshipStore = Depends(get_friendship_store),
) -> FriendshipInfo:
    friendship = _get_friendship_or_404(friendship_id, friendships)
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
    friendship = _get_friendship_or_404(friendship_id, friendships)
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
    friendship = _get_friendship_or_404(friendship_id, friendships)
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
    friendship = _get_friendship_or_404(friendship_id, friendships)
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
        chat = chats.create(kind="group", created_by=user["id"], name=req.name)
        chats.add_member(chat["id"], user["id"])
    else:
        peer = users.get_by_id(req.peer_user_id)
        if peer is None:
            raise HTTPException(status_code=404, detail="İstifadəçi tapılmadı")
        if not friendships.are_friends(user["id"], req.peer_user_id):
            raise HTTPException(status_code=403, detail="Yalnız dostlarla birbaşa çat yaradıla bilər")
        chat = chats.create(kind="direct", created_by=user["id"])
        chats.add_member(chat["id"], user["id"])
        chats.add_member(chat["id"], req.peer_user_id)
    return ChatInfo(**chat)


@app.get("/chats", response_model=list[ChatInfo])
def list_chats(
    user: dict = Depends(get_current_user),
    chats: ChatStore = Depends(get_chat_store),
) -> list[ChatInfo]:
    return [ChatInfo(**c) for c in chats.list_by_user(user["id"])]


@app.post("/chats/{chat_id}/join", response_model=ChatInfo)
def join_chat(
    chat_id: int,
    user: dict = Depends(get_current_user),
    chats: ChatStore = Depends(get_chat_store),
) -> ChatInfo:
    chat = chats.get(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Çat tapılmadı")
    if chat["kind"] == "direct":
        raise HTTPException(status_code=400, detail="Direct çata kənardan qoşulmaq olmaz")
    chats.add_member(chat_id, user["id"])
    return ChatInfo(**chat)


@app.get("/chats/{chat_id}/members", response_model=list[ChatMemberInfo])
def list_chat_members(
    chat_id: int,
    user: dict = Depends(get_current_user),
    chats: ChatStore = Depends(get_chat_store),
    users: UserStore = Depends(get_user_store),
) -> list[ChatMemberInfo]:
    """Çatın üzv siyahısı — müəllimin Fərdi tələbə tarixçəsi ekranında
    tələbə seçmək üçün istifadə olunur (bax `/history/student/{id}`)."""
    if chats.get(chat_id) is None:
        raise HTTPException(status_code=404, detail="Çat tapılmadı")
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
) -> list[LeaderboardRow]:
    """Çatın liderlik lövhəsi — YALNIZ ev tapşırığı xalları (bax Faza 6
    dizayn sənədi, "canlı sessiyalar çata bağlı deyil"). 0-xallı üzvlər
    də daxildir (`live_session_store.compute_scores`-un eyni naxışı)."""
    if chats.get(chat_id) is None:
        raise HTTPException(status_code=404, detail="Çat tapılmadı")
    if user["id"] not in chats.list_member_ids(chat_id):
        raise HTTPException(status_code=403, detail="Bu çatın üzvü deyilsiniz")

    scores = homework.get_chat_leaderboard(chat_id)
    rows = []
    for member_id in chats.list_member_ids(chat_id):
        member = users.get_by_id(member_id)
        if member is not None:
            rows.append((member_id, member["display_name"], scores.get(member_id, 0)))
    rows.sort(key=lambda r: r[2], reverse=True)
    return [
        LeaderboardRow(user_id=uid, display_name=name, total_score=score, rank=i + 1)
        for i, (uid, name, score) in enumerate(rows)
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
) -> QuizSessionInfo:
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
) -> None:
    """Materialı fon thread-ində emal edir — nəticə/xəta çata sistem mesajı
    kimi bildirilir, HEÇ vaxt səssiz udulmur (spec bölmə 5-6)."""
    try:
        result = await asyncio.to_thread(generator, source, question_count)
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
) -> MaterialInfo:
    chat = chats.get(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Çat tapılmadı")
    if user["id"] not in chats.list_member_ids(chat_id):
        raise HTTPException(status_code=403, detail="Bu çatın üzvü deyilsiniz")

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
    chat = chats.get(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Çat tapılmadı")
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
) -> None:
    """Canlı sessiya sual bankını fon thread-ində emal edir — mövcud
    `_process_material`-a bənzər naxış, amma çat/mesaj sisteminə bağlı
    deyil (nəticə `question_sets.status`+`error` sahələrindən polling
    ilə oxunur, bax dizayn sənədi)."""
    try:
        result = await asyncio.to_thread(generator, source, question_count)
    except Exception as exc:
        logger.exception("Sual bankı emalı uğursuz oldu (question_set_id=%s)", question_set_id)
        question_set_store.mark_failed(question_set_id, str(exc))
        return

    for mcq in result.questions:
        question_set_store.add_question(question_set_id, mcq)
    question_set_store.mark_ready(question_set_id)


@app.post("/live/question-sets", response_model=QuestionSetInfo, status_code=202)
async def create_question_set(
    subject: str = Form(...),
    title: str = Form(...),
    kind: str = Form(...),
    location: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    question_count: int = Form(default=10),
    user: dict = Depends(get_current_teacher),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    generator=Depends(get_material_generator),
    upload_dir: str = Depends(get_upload_dir),
) -> QuestionSetInfo:
    if subject not in SUBJECTS:
        raise HTTPException(status_code=400, detail="Naməlum fənn")
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

    question_set = question_sets.create(
        subject=subject,
        title=title,
        material_kind=kind,
        material_location=source_location,
        created_by=user["id"],
    )

    task = asyncio.create_task(
        _process_question_set(
            question_set["id"],
            MaterialSource(kind=kind, location=source_location),
            generator=generator,
            question_set_store=question_sets,
            question_count=question_count,
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
    question_set = question_sets.get(question_set_id)
    if question_set is None:
        raise HTTPException(status_code=404, detail="Sual bankı tapılmadı")
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
    all_sets = question_sets.list_all()
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
    if question_sets.get(question_set_id) is None:
        raise HTTPException(status_code=404, detail="Sual bankı tapılmadı")
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
    if question_sets.get(question_set_id) is None:
        raise HTTPException(status_code=404, detail="Sual bankı tapılmadı")

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
    report = audit_questions(questions)
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
    if question_sets.get_question(question_id) is None:
        raise HTTPException(status_code=404, detail="Sual tapılmadı")
    updated = question_sets.update_question(
        question_id,
        question=req.question,
        options=req.options,
        correct_index=req.correct_index,
        explanation=req.explanation,
    )
    return LiveQuestionInfo(**updated)


@app.delete("/live/questions/{question_id}", status_code=204)
def delete_live_question(
    question_id: int,
    user: dict = Depends(get_current_teacher),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
) -> None:
    if question_sets.get_question(question_id) is None:
        raise HTTPException(status_code=404, detail="Sual tapılmadı")
    question_sets.delete_question(question_id)


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

    chat = chats.get(chat_id)
    if chat is None:
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
def create_live_session(
    req: CreateLiveSessionRequest,
    user: dict = Depends(get_current_teacher),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    live_sessions: LiveSessionStore = Depends(get_live_session_store),
) -> LiveSessionInfo:
    question_set = question_sets.get(req.question_set_id)
    if question_set is None:
        raise HTTPException(status_code=404, detail="Sual bankı tapılmadı")
    if question_set["status"] != "ready":
        raise HTTPException(status_code=400, detail="Sual bankı hələ hazır deyil")
    session = live_sessions.create_session(req.question_set_id)
    return LiveSessionInfo(**session)


@app.get("/live/sessions/{session_id}/report", response_model=LiveSessionReport)
def get_live_session_report(
    session_id: int,
    user: dict = Depends(get_current_teacher),
    live_sessions: LiveSessionStore = Depends(get_live_session_store),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
) -> LiveSessionReport:
    session = live_sessions.get(session_id)
    if session is None:
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


def _homework_attempt_state(attempt: dict, questions: list[dict]) -> HomeworkAttemptState:
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
    if chats.get(req.chat_id) is None:
        raise HTTPException(status_code=404, detail="Çat tapılmadı")
    if user["id"] not in chats.list_member_ids(req.chat_id):
        raise HTTPException(status_code=403, detail="Bu çatın üzvü deyilsiniz")
    question_set = question_sets.get(req.question_set_id)
    if question_set is None:
        raise HTTPException(status_code=404, detail="Sual bankı tapılmadı")
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
    assignment = homework.get_assignment(assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Tapşırıq tapılmadı")
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
) -> list[HistoryEntry]:
    """Müəllimin başqa bir tələbənin tarixçəsinə baxması — yalnız ortaq
    çatı olan (bax `list_chat_members`-in eyni naxışı) tələbələr üçün."""
    if not user["is_teacher"]:
        raise HTTPException(status_code=403, detail="Yalnız müəllim başqa tələbənin tarixçəsinə baxa bilər")
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
    assignment = homework.get_assignment(assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Tapşırıq tapılmadı")
    if user["id"] not in chats.list_member_ids(assignment["chat_id"]):
        raise HTTPException(status_code=403, detail="Bu çatın üzvü deyilsiniz")

    questions = question_sets.list_questions(assignment["question_set_id"])
    attempt = homework.get_or_create_attempt(assignment_id, student_id=user["id"])
    return _homework_attempt_state(attempt, questions)


@app.post("/homework/attempts/{attempt_id}/answer", response_model=HomeworkAnswerResult)
def answer_homework_question(
    attempt_id: int,
    req: HomeworkAnswerRequest,
    user: dict = Depends(get_current_user),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    homework: HomeworkStore = Depends(get_homework_store),
) -> HomeworkAnswerResult:
    attempt = homework.get_attempt(attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="Cəhd tapılmadı")
    if attempt["student_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Bu cəhd sizə aid deyil")

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


@app.websocket("/ws/live/{pin}/host")
async def live_host_websocket(
    websocket: WebSocket,
    pin: str,
    token: str = Query(...),
    secret: str = Depends(get_token_secret),
    users: UserStore = Depends(get_user_store),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    live_sessions: LiveSessionStore = Depends(get_live_session_store),
    manager: LiveConnectionManager = Depends(get_live_connection_manager),
) -> None:
    try:
        user_id = verify_token(token, secret=secret)
    except InvalidToken:
        await _reject_websocket(websocket, 4401, "Sessiyanız bitib. Yenidən daxil olun.")
        return
    if users.get_by_id(user_id) is None:
        await _reject_websocket(websocket, 4401, "Sessiyanız bitib. Yenidən daxil olun.")
        return

    session = live_sessions.get_by_pin(pin)
    if session is None:
        # `get_by_pin` BİTMİŞ sessiyanı qaytarmır — ən çox rast gəlinən
        # hal budur: müəllimin səhifəsi köhnəlib.
        await _reject_websocket(
            websocket, 4404,
            "Bu sessiya artıq bitib və ya tapılmadı. Sessiyalar bölməsindən yenisini başladın.",
        )
        return

    await websocket.accept()
    manager.connect_host(session["id"], websocket)
    await websocket.send_json(
        {
            "type": "state",
            "session_id": session["id"],
            "status": session["status"],
            "participants": live_sessions.list_participants(session["id"]),
        }
    )

    try:
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

            action = data.get("action")

            if action == "start":
                duration_seconds = data.get("duration_seconds")
                if not isinstance(duration_seconds, int) or duration_seconds <= 0:
                    duration_seconds = DEFAULT_SESSION_DURATION_SECONDS
                try:
                    await start_live_session(
                        session["id"],
                        duration_seconds,
                        session_store=live_sessions,
                        question_set_store=question_sets,
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
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect_host(session["id"], websocket)


@app.websocket("/ws/live/{pin}/play")
async def live_play_websocket(
    websocket: WebSocket,
    pin: str,
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    live_sessions: LiveSessionStore = Depends(get_live_session_store),
    manager: LiveConnectionManager = Depends(get_live_connection_manager),
    secret: str = Depends(get_token_secret),
) -> None:
    await websocket.accept()

    try:
        join_msg = await websocket.receive_json()
    except Exception:
        await websocket.close(code=4400)
        return
    display_name = (join_msg or {}).get("display_name") if isinstance(join_msg, dict) else None
    if not isinstance(display_name, str) or not display_name.strip():
        await websocket.close(code=4400)
        return

    # `token` KÖNÜLLÜDÜR — PIN qoşulması hesabsız da mümkündür (bax
    # `JoinPinScreen`, giriş ekranından ƏVVƏL istifadə edilə bilər).
    # Daxil olmuş istifadəçi öz tokenini göndərəndə iştirakçı hesaba
    # bağlanır (Fərdi tələbə tarixçəsi buna əsaslanır) — etibarsız/köhnə
    # tokenlə qoşulma RƏDD EDİLMİR, sadəcə anonim kimi davam edir.
    token = (join_msg or {}).get("token") if isinstance(join_msg, dict) else None
    user_id: int | None = None
    if isinstance(token, str) and token.strip():
        try:
            user_id = verify_token(token.strip(), secret=secret)
        except InvalidToken:
            user_id = None

    try:
        session, participant = await join_live_session(
            pin, display_name, session_store=live_sessions, connection_manager=manager, user_id=user_id
        )
    except LiveSessionNotFound:
        await websocket.close(code=4404)
        return
    except LiveSessionNotJoinable:
        await websocket.close(code=4409)
        return

    manager.connect_player(session["id"], participant["id"], websocket)
    await websocket.send_json(
        {"type": "joined", "participant_id": participant["id"], "session_id": session["id"]}
    )

    try:
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
                        session["id"], participant["id"],
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
                    session["id"], participant["id"], question_index, chosen_index,
                    session_store=live_sessions, question_set_store=question_sets,
                    connection_manager=manager,
                )
            except (LiveNotCurrentQuestion, LiveAlreadyAnswered, LiveSessionTimeExpired, LiveSessionError) as exc:
                await websocket.send_json({"type": "error", "detail": str(exc)})
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect_player(session["id"], participant["id"], websocket)
