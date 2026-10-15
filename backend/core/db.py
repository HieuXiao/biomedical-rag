"""Khởi tạo SQLite + session + seed dữ liệu ban đầu."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.models import Base, User, Document

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = _BACKEND_ROOT / "data" / "app.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Thư mục lưu file tài liệu người dùng upload.
UPLOAD_DIR = _BACKEND_ROOT / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Sentinel cho khối Vector DB gốc (các node phác đồ có sẵn, không có doc_key).
BASE_INDEX_MARKER = "__base_index__"

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from core import auth  # import trễ để tránh vòng import (auth cần get_db)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Seed admin mặc định.
        admin_email = os.getenv("ADMIN_EMAIL", "admin@medrag.local")
        if not db.query(User).filter(User.email == admin_email).first():
            admin = User(
                email=admin_email,
                username="Administrator",
                password_hash=auth.hash_password(os.getenv("ADMIN_PASSWORD", "admin123")),
                role="admin",
                full_name="Quản trị hệ thống",
                title="Admin",
            )
            db.add(admin)
            db.commit()
            print(f"[DB] Seed admin: {admin_email} (mật khẩu mặc định: admin123 — hãy đổi)")

        # Seed tài liệu hệ thống gốc (khối Vector DB có sẵn: phác đồ ĐTĐ).
        if not db.query(Document).filter(Document.stored_path == BASE_INDEX_MARKER).first():
            base_doc = Document(
                scope="system",
                owner_id=None,
                filename="phac-do-dai-thao-duong.pdf",
                stored_path=BASE_INDEX_MARKER,
                num_chunks=48,
                active=True,
                indexed=True,
                note="Phác đồ Đái tháo đường típ 2 (Bộ Y tế) — tài liệu gốc hệ thống",
            )
            db.add(base_doc)
            db.commit()
            print("[DB] Seed tài liệu hệ thống gốc: phac-do-dai-thao-duong.pdf")
    finally:
        db.close()
