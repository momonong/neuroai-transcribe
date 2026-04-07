"""
POST /api/auth/register, POST /api/auth/login
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models import Project, ProjectUserLink, User
from schemas import LoginBody, RegisterBody
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


@router.post("/login")
def login(body: LoginBody, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")
    token = create_access_token(str(user.id), {"username": user.username})
    return {"access_token": token, "token_type": "bearer"}
