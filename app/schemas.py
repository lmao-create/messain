"""Pydantic request/response models and input validation."""

import re

from pydantic import BaseModel, field_validator

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
USERNAME_MIN, USERNAME_MAX = 3, 32
PASSWORD_MIN, PASSWORD_MAX = 8, 128
MESSAGE_MAX = 4000


class RegisterRequest(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def _check_username(cls, value: str) -> str:
        value = value.strip()
        if not USERNAME_MIN <= len(value) <= USERNAME_MAX:
            raise ValueError(f"Username must be {USERNAME_MIN}-{USERNAME_MAX} characters long")
        if not USERNAME_PATTERN.fullmatch(value):
            raise ValueError("Username may only contain letters, numbers, dots, dashes and underscores")
        return value

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        if not PASSWORD_MIN <= len(value) <= PASSWORD_MAX:
            raise ValueError(f"Password must be {PASSWORD_MIN}-{PASSWORD_MAX} characters long")
        return value


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    created_at: str
    is_online: bool = False


class AuthResponse(BaseModel):
    token: str
    user: UserOut


class CreateConversationRequest(BaseModel):
    user_id: int


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    sender_id: int
    content: str
    created_at: str
    is_read: bool = False


class ConversationOut(BaseModel):
    id: int
    created_at: str
    partner: UserOut
    last_message: MessageOut | None = None


class SendMessageRequest(BaseModel):
    content: str

    @field_validator("content")
    @classmethod
    def _check_content(cls, value: str) -> str:
        value = value.strip()
        if not 1 <= len(value) <= MESSAGE_MAX:
            raise ValueError(f"Message must be 1-{MESSAGE_MAX} characters long")
        return value
