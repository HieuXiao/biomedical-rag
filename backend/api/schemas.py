"""Pydantic schemas cho request/response."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# ---- Auth / User ----------------------------------------------------------
class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    email: str
    password: str


class ProfileUpdate(BaseModel):
    username: Optional[str] = None
    full_name: Optional[str] = None
    title: Optional[str] = None
    specialty: Optional[str] = None
    workplace: Optional[str] = None
    personalization: Optional[str] = None


class UserOut(BaseModel):
    id: int
    email: str
    username: str
    role: str
    full_name: str = ""
    title: str = ""
    specialty: str = ""
    workplace: str = ""
    personalization: str = ""

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---- Conversations --------------------------------------------------------
class ConversationOut(BaseModel):
    id: int
    title: str
    created_at: str
    updated_at: str


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    sources: list = []
    pipeline: dict = {}
    created_at: str


# ---- Chat -----------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str
    model: Optional[str] = None
    api_key: Optional[str] = None
    conversation_id: Optional[int] = None


# ---- Documents ------------------------------------------------------------
class DocumentOut(BaseModel):
    id: int
    scope: str
    filename: str
    num_chunks: int
    active: bool
    indexed: bool
    note: str = ""
    owner_id: Optional[int] = None
    created_at: str


class DocToggle(BaseModel):
    active: bool
