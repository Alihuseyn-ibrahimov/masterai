"""MasterAI backend FastAPI tətbiqi.

Auth (/auth/register, /auth/login, /health) + əsas çat (POST/GET /chats,
/chats/{id}/join). WebSocket mesajlaşma (Faza 4) və AI quiz orkestrasiyası
hələ əhatə xaricindədir — bax spec-lər.
"""

from __future__ import annotations

import os

from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect

from .auth import InvalidToken, create_token, hash_password, token_secret, verify_password, verify_token
from .chat_store import ChatStore
from .connection_manager import ConnectionManager
from .message_store import MessageStore
from .models import AuthResponse, ChatInfo, CreateChatRequest, LoginRequest, RegisterRequest, UserInfo
from .user_store import DuplicateEmail, UserStore

app = FastAPI(title="MasterAI")
app.state.user_store = UserStore(os.environ.get("USERS_DB_PATH", "users.db"))
app.state.chat_store = ChatStore(os.environ.get("CHATS_DB_PATH", "chats.db"))
app.state.message_store = MessageStore(os.environ.get("MESSAGES_DB_PATH", "messages.db"))
app.state.connection_manager = ConnectionManager()


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

            if not isinstance(data, dict) or data.get("type") != "text":
                await websocket.send_json({"type": "error", "detail": "mesaj formatı düzgün deyil"})
                continue
            content = data.get("content")
            if not isinstance(content, str) or not content.strip():
                await websocket.send_json({"type": "error", "detail": "mesaj formatı düzgün deyil"})
                continue

            message = messages.create(chat_id, user_id, "text", content)
            await manager.broadcast(chat_id, {"type": "message", **message})
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(chat_id, user_id, websocket)
