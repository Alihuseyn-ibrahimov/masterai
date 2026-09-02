"""MasterAI backend FastAPI tətbiqi.

Auth (/auth/register, /auth/login, /health) + əsas çat (POST/GET /chats,
/chats/{id}/join, WS /ws/chat/{id}) + AI quiz orkestrasiyası
(POST /chats/{id}/quiz/start, WS "answer" mesaj tipi).
"""

from __future__ import annotations

import asyncio
import os

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect

from pipeline.models import MaterialSource
from pipeline.pipeline import generate_quiz

from .auth import InvalidToken, create_token, hash_password, token_secret, verify_password, verify_token
from .chat_store import ChatStore
from .connection_manager import ConnectionManager
from .material_store import MaterialStore
from .message_store import MessageStore
from .models import (
    AuthResponse,
    ChatInfo,
    CreateChatRequest,
    LoginRequest,
    MaterialInfo,
    QuizSessionInfo,
    QuizStartRequest,
    RegisterRequest,
    UserInfo,
)
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
# chat_id -> planlaşdırılmış timeout task-ı (strong reference — Python-un
# arayışsız task-ı vaxtından əvvəl çöp yığmaması üçün).
app.state.active_quiz_timeouts = {}
# material_id -> planlaşdırılmış fon emalı task-ı (eyni naxış).
app.state.active_material_tasks = {}


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


@app.post("/chats", response_model=ChatInfo, status_code=201)
def create_chat(
    req: CreateChatRequest,
    user: dict = Depends(get_current_user),
    chats: ChatStore = Depends(get_chat_store),
    users: UserStore = Depends(get_user_store),
) -> ChatInfo:
    if req.kind == "group":
        chat = chats.create(kind="group", created_by=user["id"], name=req.name)
        chats.add_member(chat["id"], user["id"])
    else:
        peer = users.get_by_id(req.peer_user_id)
        if peer is None:
            raise HTTPException(status_code=404, detail="İstifadəçi tapılmadı")
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
