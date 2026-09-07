"""MasterAI backend FastAPI tətbiqi.

Auth (/auth/register, /auth/login, /health) + əsas çat (POST/GET /chats,
/chats/{id}/join, WS /ws/chat/{id}) + AI quiz orkestrasiyası
(POST /chats/{id}/quiz/start, WS "answer" mesaj tipi).
"""

from __future__ import annotations

import asyncio
import os

import httpx
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect

from pipeline.models import MaterialSource
from pipeline.pipeline import generate_quiz

from .auth import InvalidToken, create_token, hash_password, token_secret, verify_password, verify_token
from .chat_store import ChatStore
from .connection_manager import ConnectionManager
from .friendship_store import AlreadyFriends, DuplicateFriendship, FriendshipStore
from .material_store import MaterialStore
from .message_store import MessageStore
from .models import (
    AdminStatsInfo,
    AuthResponse,
    ChatInfo,
    CreateChatRequest,
    FriendshipInfo,
    LoginRequest,
    MaterialInfo,
    QuestionSetInfo,
    QuizSessionInfo,
    QuizStartRequest,
    RegisterRequest,
    SendFriendRequestRequest,
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

app = FastAPI(title="MasterAI")
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
# chat_id -> planlaşdırılmış timeout task-ı (strong reference — Python-un
# arayışsız task-ı vaxtından əvvəl çöp yığmaması üçün).
app.state.active_quiz_timeouts = {}
# material_id -> planlaşdırılmış fon emalı task-ı (eyni naxış).
app.state.active_material_tasks = {}
# question_set_id -> planlaşdırılmış fon emalı task-ı (eyni naxış).
app.state.active_question_set_tasks = {}


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


def _user_info(user: dict) -> UserInfo:
    """DB sətrindən cavab modeli — `password_hash` qəsdən daxil edilmir."""
    return UserInfo(
        id=user["id"],
        email=user["email"],
        display_name=user["display_name"],
        created_at=user["created_at"],
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
    questions_per_chunk: int = 3,
) -> None:
    """Materialı fon thread-ində emal edir — nəticə/xəta çata sistem mesajı
    kimi bildirilir, HEÇ vaxt səssiz udulmur (spec bölmə 5-6)."""
    try:
        result = await asyncio.to_thread(generator, source, questions_per_chunk)
    except Exception as exc:
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
    message = message_store.create(
        chat_id, None, "system", f"Material hazırdır! {len(result.questions)} sual yaradıldı."
    )
    await connection_manager.broadcast(chat_id, {"type": "message", **message})


@app.post("/chats/{chat_id}/materials", response_model=MaterialInfo, status_code=202)
async def upload_material(
    chat_id: int,
    kind: str = Form(...),
    location: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    label: str | None = Form(default=None),
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
    questions_per_chunk: int = 3,
) -> None:
    """Canlı sessiya sual bankını fon thread-ində emal edir — mövcud
    `_process_material`-a bənzər naxış, amma çat/mesaj sisteminə bağlı
    deyil (nəticə `question_sets.status`+`error` sahələrindən polling
    ilə oxunur, bax dizayn sənədi)."""
    try:
        result = await asyncio.to_thread(generator, source, questions_per_chunk)
    except Exception as exc:
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
    user: dict = Depends(get_current_user),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
    generator=Depends(get_material_generator),
    upload_dir: str = Depends(get_upload_dir),
) -> QuestionSetInfo:
    if subject not in SUBJECTS:
        raise HTTPException(status_code=400, detail="Naməlum fənn")
    if kind not in ("link", "pdf", "image"):
        raise HTTPException(status_code=400, detail="Naməlum material növü")

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
        )
    )
    app.state.active_question_set_tasks[question_set["id"]] = task

    return _question_set_info(question_set, question_count=0)


@app.get("/live/question-sets/{question_set_id}", response_model=QuestionSetInfo)
def get_question_set(
    question_set_id: int,
    user: dict = Depends(get_current_user),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
) -> QuestionSetInfo:
    question_set = question_sets.get(question_set_id)
    if question_set is None:
        raise HTTPException(status_code=404, detail="Sual bankı tapılmadı")
    count = question_sets.count_questions(question_set_id)
    return _question_set_info(question_set, question_count=count)


@app.get("/live/question-sets", response_model=list[QuestionSetInfo])
def list_question_sets(
    user: dict = Depends(get_current_user),
    question_sets: QuestionSetStore = Depends(get_question_set_store),
) -> list[QuestionSetInfo]:
    return [
        _question_set_info(qs, question_count=question_sets.count_questions(qs["id"]))
        for qs in question_sets.list_all()
    ]


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
        await websocket.close(code=4401)
        return
    user = users.get_by_id(user_id)
    if user is None:
        await websocket.close(code=4401)
        return

    chat = chats.get(chat_id)
    if chat is None:
        await websocket.close(code=4404)
        return
    is_member = any(c["id"] == chat_id for c in chats.list_by_user(user_id))
    if not is_member:
        await websocket.close(code=4403)
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
