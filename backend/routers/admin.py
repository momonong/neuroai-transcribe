"""
管理員 API：專案與使用者／專案成員管理、帳號啟停。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from deps import require_admin
from models import Project, ProjectUserLink, User
from schemas import AdminCreateProjectBody, AdminUpdateProjectBody

router = APIRouter(prefix="/api/admin", tags=["admin"])

DUPLICATE_PROJECT_NAME_MSG = "專案名稱已存在"


@router.get("/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    users = db.scalars(select(User).order_by(User.id)).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "real_name": u.real_name,
            "is_active": u.is_active,
        }
        for u in users
    ]


@router.get("/projects")
def list_projects(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    projects = db.scalars(select(Project).order_by(Project.id)).all()
    out = []
    for p in projects:
        links = db.scalars(
            select(ProjectUserLink).where(ProjectUserLink.project_id == p.id)
        ).all()
        out.append(
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "user_ids": [L.user_id for L in links],
            }
        )
    return out


@router.post("/projects")
def create_project(
    body: AdminCreateProjectBody,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="專案名稱不可為空白")
    exists = db.scalar(select(Project).where(Project.name == name))
    if exists is not None:
        raise HTTPException(status_code=400, detail=DUPLICATE_PROJECT_NAME_MSG)
    p = Project(name=name, description=body.description)
    db.add(p)
    db.commit()
    db.refresh(p)
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "user_ids": [],
    }


@router.patch("/projects/{project_id}")
def update_project(
    project_id: int,
    body: AdminUpdateProjectBody,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    p = db.get(Project, project_id)
    if p is None:
        raise HTTPException(status_code=404, detail="專案不存在")
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="沒有要更新的欄位")
    if "name" in data:
        name = data["name"].strip()
        if not name:
            raise HTTPException(status_code=400, detail="專案名稱不可為空白")
        dup = db.scalar(
            select(Project).where(Project.name == name, Project.id != project_id)
        )
        if dup is not None:
            raise HTTPException(status_code=400, detail=DUPLICATE_PROJECT_NAME_MSG)
        p.name = name
    if "description" in data:
        p.description = data["description"]
    db.commit()
    db.refresh(p)
    user_ids = [
        L.user_id
        for L in db.scalars(
            select(ProjectUserLink).where(ProjectUserLink.project_id == p.id)
        ).all()
    ]
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "user_ids": user_ids,
    }


@router.delete("/projects/{project_id}")
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    p = db.get(Project, project_id)
    if p is None:
        raise HTTPException(status_code=404, detail="專案不存在")
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.post("/projects/{project_id}/users/{user_id}")
def add_user_to_project(
    project_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="專案不存在")
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="使用者不存在")
    existing = db.scalar(
        select(ProjectUserLink).where(
            ProjectUserLink.project_id == project_id,
            ProjectUserLink.user_id == user_id,
        )
    )
    if existing is not None:
        return {
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "user_ids": [
                L.user_id
                for L in db.scalars(
                    select(ProjectUserLink).where(ProjectUserLink.project_id == project_id)
                ).all()
            ],
        }
    db.add(ProjectUserLink(user_id=user_id, project_id=project_id))
    db.commit()
    user_ids = [
        L.user_id
        for L in db.scalars(
            select(ProjectUserLink).where(ProjectUserLink.project_id == project_id)
        ).all()
    ]
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "user_ids": user_ids,
    }


@router.delete("/projects/{project_id}/users/{user_id}")
def remove_user_from_project(
    project_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    link = db.scalar(
        select(ProjectUserLink).where(
            ProjectUserLink.project_id == project_id,
            ProjectUserLink.user_id == user_id,
        )
    )
    if link is None:
        raise HTTPException(status_code=404, detail="使用者不在此專案中")
    db.delete(link)
    db.commit()
    return {"ok": True}


@router.patch("/users/{user_id}/activate")
def activate_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="使用者不存在")
    target.is_active = True
    db.commit()
    db.refresh(target)
    return {
        "id": target.id,
        "username": target.username,
        "real_name": target.real_name,
        "is_active": target.is_active,
    }


@router.patch("/users/{user_id}/deactivate")
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="不可停權自己的帳號")
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="使用者不存在")
    target.is_active = False
    db.commit()
    db.refresh(target)
    return {
        "id": target.id,
        "username": target.username,
        "real_name": target.real_name,
        "is_active": target.is_active,
    }
