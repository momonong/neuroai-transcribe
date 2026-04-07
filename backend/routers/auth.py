"""
POST /api/auth/register, POST /api/auth/login, GET /api/auth/me, PATCH /api/auth/me/password
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from deps import get_current_user
from models import Project, ProjectUserLink, User
from schemas import LoginBody, PasswordChange, RegisterBody
from security import create_access_token, hash_password, verify_password

USERNAME_TAKEN_MSG = "此帳號已被註冊，請換一個帳號"

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register")
def register(body: RegisterBody, db: Session = Depends(get_db)):
    exists = db.scalar(select(User).where(User.username == body.username))
    if exists:
        raise HTTPException(status_code=400, detail=USERNAME_TAKEN_MSG)
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        real_name=body.real_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    default_project = db.scalar(
        select(Project).where(Project.name == "預設專案 (Default Project)")
    )
    if default_project is not None:
        db.add(ProjectUserLink(user_id=user.id, project_id=default_project.id))
        db.commit()

    return {"id": user.id, "username": user.username, "real_name": user.real_name}


DEACTIVATED_MSG = "此帳號已被停權，請聯絡管理員"


@router.get("/me")
def read_me(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "username": user.username,
        "real_name": user.real_name,
        "role": user.role,
        "is_active": user.is_active,
    }


OLD_PASSWORD_WRONG_MSG = "舊密碼錯誤"


@router.patch("/me/password")
def change_my_password(
    body: PasswordChange,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail=OLD_PASSWORD_WRONG_MSG)
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True}


@router.post("/login")
def login(body: LoginBody, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")
    if not user.is_active:
        raise HTTPException(status_code=401, detail=DEACTIVATED_MSG)
    token = create_access_token(
        str(user.id),
        {"username": user.username, "role": user.role},
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role,
        "user_id": user.id,
        "username": user.username,
        "real_name": user.real_name,
    }
