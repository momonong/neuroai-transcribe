"""
FastAPI 依賴：DB Session、目前使用者、專案／案例權限。
"""
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models import ProjectUserLink, Task, User
from security import safe_decode_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail="未登入或缺少 Token")
    payload = safe_decode_token(credentials.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=401, detail="無效的 Token")
    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="無效的 Token")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="使用者不存在")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="此帳號已被停權，請聯絡管理員")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理員權限")
    return user


def assert_project_member(db: Session, user_id: int, project_id: int) -> None:
    link = db.scalar(
        select(ProjectUserLink).where(
            ProjectUserLink.user_id == user_id,
            ProjectUserLink.project_id == project_id,
        )
    )
    if link is None:
        raise HTTPException(status_code=403, detail="無權存取此專案")


def get_task_for_case(db: Session, case_name: str) -> Optional[Task]:
    return db.scalar(select(Task).where(Task.case_name == case_name))


def assert_user_can_access_case(db: Session, user: User, case_name: str) -> Task:
    task = get_task_for_case(db, case_name)
    if task is None:
        raise HTTPException(status_code=404, detail="案例不存在或無權存取")
    assert_project_member(db, user.id, task.project_id)
    return task


def user_accessible_case_names(db: Session, user_id: int) -> set[str]:
    rows = db.execute(
        select(Task.case_name)
        .join(ProjectUserLink, Task.project_id == ProjectUserLink.project_id)
        .where(ProjectUserLink.user_id == user_id)
    ).all()
    return {r[0] for r in rows}
