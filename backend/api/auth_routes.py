"""Router: đăng ký, đăng nhập, thông tin & cập nhật hồ sơ."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.schemas import LoginRequest, ProfileUpdate, RegisterRequest, TokenResponse, UserOut
from core import auth
from core.db import get_db
from core.models import ActivityLog, User

router = APIRouter(prefix="/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.post("/register", response_model=TokenResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    email = req.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Email không hợp lệ")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email đã được đăng ký")

    user = User(
        email=email,
        username=req.username.strip(),
        password_hash=auth.hash_password(req.password),
        role="user",
        full_name=req.username.strip(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    db.add(ActivityLog(user_id=user.id, action="register", detail=email))
    db.commit()

    token = auth.create_token(user.id, user.role)
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    email = req.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not auth.verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng")

    db.add(ActivityLog(user_id=user.id, action="login", detail=email))
    db.commit()

    token = auth.create_token(user.id, user.role)
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(auth.get_current_user)):
    return UserOut.model_validate(user)


@router.put("/me", response_model=UserOut)
def update_profile(req: ProfileUpdate, user: User = Depends(auth.get_current_user),
                   db: Session = Depends(get_db)):
    fields = ["username", "full_name", "title", "specialty", "workplace", "personalization"]
    for f in fields:
        val = getattr(req, f)
        if val is not None:
            setattr(user, f, val)
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)
