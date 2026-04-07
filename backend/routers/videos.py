"""
GET /api/videos, GET /api/cases（依專案與 ProjectUserLink 隔離）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from deps import assert_project_member, get_current_user
from models import Task, TaskStatus, User
from services.video_service import list_videos_for_case

router = APIRouter(prefix="/api", tags=["videos"])


def _assignee_real_name(db: Session, task: Task) -> str | None:
    if task.assignee_id is None:
        return None
    u = db.get(User, task.assignee_id)
    return u.real_name if u else None


@router.get("/videos")
def get_videos(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assert_project_member(db, user.id, project_id)
    tasks = db.scalars(select(Task).where(Task.project_id == project_id)).all()
    out: list[dict] = []
    for t in tasks:
        status_val = t.status.value if isinstance(t.status, TaskStatus) else str(t.status)
        assignee_name = _assignee_real_name(db, t)
        for v in list_videos_for_case(t.case_name):
            out.append(
                {
                    "path": v["path"],
                    "name": v["name"],
                    "case_name": t.case_name,
                    "status": status_val,
                    "assignee_real_name": assignee_name,
                }
            )
    out.sort(key=lambda x: x["name"], reverse=True)
    # #region agent log
    try:
        import json
        import time
        from pathlib import Path

        _log_path = Path(__file__).resolve().parent.parent.parent / "debug-4dbe56.log"
        _payload = {
            "sessionId": "4dbe56",
            "location": "videos.py:get_videos",
            "message": "videos response",
            "hypothesisId": "H1",
            "data": {
                "project_id": project_id,
                "task_count": len(tasks),
                "row_count": len(out),
            },
            "timestamp": int(time.time() * 1000),
        }
        with open(_log_path, "a", encoding="utf-8") as _f:
            _f.write(json.dumps(_payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion
    return out


@router.get("/cases")
def get_cases(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assert_project_member(db, user.id, project_id)
    tasks = db.scalars(select(Task).where(Task.project_id == project_id)).all()
    return [
        {
            "case_name": t.case_name,
            "status": t.status.value if isinstance(t.status, TaskStatus) else str(t.status),
            "assignee_real_name": _assignee_real_name(db, t),
        }
        for t in tasks
    ]
