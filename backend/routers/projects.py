"""
GET /api/projects/my
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from deps import get_current_user
from models import Project, ProjectUserLink, User

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("/my")
def list_my_projects(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    projects = db.scalars(
        select(Project)
        .join(ProjectUserLink, ProjectUserLink.project_id == Project.id)
        .where(ProjectUserLink.user_id == user.id)
    ).all()

    result = []
    for p in projects:
        member_rows = db.execute(
            select(User.id, User.real_name)
            .join(ProjectUserLink, ProjectUserLink.user_id == User.id)
            .where(
                ProjectUserLink.project_id == p.id,
                User.is_active.is_(True),
            )
        ).all()
        result.append(
            {
                "id": p.id,
                "name": p.name,
                "members": [{"user_id": row[0], "real_name": row[1]} for row in member_rows],
            }
        )
    return result
