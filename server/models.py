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
