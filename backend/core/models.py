"""SQLAlchemy models cho web app RAG (SQLite)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def _now():
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(120), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="user")  # "user" | "admin"

    # Hồ sơ cá nhân hoá (được chèn vào prompt)
    full_name = Column(String(160), default="")
    title = Column(String(120), default="")        # Chức danh: Bác sĩ, Điều dưỡng...
    specialty = Column(String(160), default="")    # Chuyên khoa: Nội tiết, Tim mạch...
    workplace = Column(String(200), default="")
    personalization = Column(Text, default="")     # Yêu cầu riêng về cách trả lời

    created_at = Column(DateTime, default=_now)

    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="owner", cascade="all, delete-orphan",
                             foreign_keys="Document.owner_id")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), default="Cuộc trò chuyện mới")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation",
                            cascade="all, delete-orphan", order_by="Message.id")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)      # "user" | "bot"
    content = Column(Text, default="")
    sources_json = Column(Text, default="")        # JSON citations
    pipeline_json = Column(Text, default="")       # JSON pipeline meta
    created_at = Column(DateTime, default=_now)

    conversation = relationship("Conversation", back_populates="messages")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    scope = Column(String(20), nullable=False, default="user")  # "system" | "user"
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    filename = Column(String(300), nullable=False)
    stored_path = Column(String(500), default="")
    num_chunks = Column(Integer, default=0)
    active = Column(Boolean, default=True)         # có đưa vào truy xuất không
    indexed = Column(Boolean, default=False)       # đã embed vào index chưa
    note = Column(String(300), default="")
    created_at = Column(DateTime, default=_now)

    owner = relationship("User", back_populates="documents", foreign_keys=[owner_id])

    @property
    def retrieval_key(self) -> str:
        # Khoá để lọc node khi truy xuất (khớp metadata).
        return f"doc:{self.id}"


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    action = Column(String(60), nullable=False)    # "chat" | "login" | "upload" ...
    detail = Column(Text, default="")
    model = Column(String(80), default="")
    grounded_ratio = Column(Float, default=None)
    created_at = Column(DateTime, default=_now, index=True)
