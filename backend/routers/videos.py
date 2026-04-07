"""

GET /api/videos, GET /api/cases（依專案與 ProjectUserLink 隔離）

PATCH /api/cases/{case_name} 更新任務狀態與負責人

"""

from __future__ import annotations



from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy import select

from sqlalchemy.orm import Session



from database import get_db

from deps import assert_project_member, assert_user_can_access_case, get_current_user

from models import Project, ProjectUserLink, Task, TaskStatus, User

from schemas import TaskUpdate

from services.video_service import list_videos_for_case



router = APIRouter(prefix="/api", tags=["videos"])





def _tasks_for_project_member(

    db: Session,

    user_id: int,

    project_id: int,

) -> list[Task]:

    assert_project_member(db, user_id, project_id)

    return list(

        db.scalars(

            select(Task)

            .distinct()

            .join(ProjectUserLink, Task.project_id == ProjectUserLink.project_id)

            .where(

                ProjectUserLink.user_id == user_id,

                Task.project_id == project_id,

            )

            .order_by(Task.case_name),

        ).all()

    )





def _assignee_real_name(db: Session, task: Task) -> str | None:

    if task.assignee_id is None:

        return None

    u = db.get(User, task.assignee_id)

    if u is None or not u.is_active:
        return None

    return u.real_name





def _task_media_row(db: Session, task: Task) -> dict | None:

    """每個 case 只回傳一筆影片（避免同案多檔案造成下拉重複）。"""

    status_val = task.status.value if isinstance(task.status, TaskStatus) else str(task.status)

    assignee_name = _assignee_real_name(db, task)

    vids = list_videos_for_case(task.case_name)

    if not vids:

        return None

    v = sorted(vids, key=lambda x: x["path"])[0]

    return {

        "path": v["path"],

        "name": v["name"],

        "case_name": task.case_name,

        "status": status_val,

        "assignee_id": task.assignee_id,

        "assignee_real_name": assignee_name,

    }





@router.get("/videos")

def get_videos(

    project_id: int,

    db: Session = Depends(get_db),

    user: User = Depends(get_current_user),

):

    tasks = _tasks_for_project_member(db, user.id, project_id)

    out: list[dict] = []

    for t in tasks:

        row = _task_media_row(db, t)

        if row:

            out.append(row)

    out.sort(key=lambda x: x["name"], reverse=True)

    return out





@router.get("/cases")

def get_cases(

    project_id: int,

    db: Session = Depends(get_db),

    user: User = Depends(get_current_user),

):

    tasks = _tasks_for_project_member(db, user.id, project_id)

    return [

        {

            "case_name": t.case_name,

            "status": t.status.value if isinstance(t.status, TaskStatus) else str(t.status),

            "assignee_id": t.assignee_id,

            "assignee_real_name": _assignee_real_name(db, t),

        }

        for t in tasks

    ]





@router.patch("/cases/{case_name}")

def patch_case_task(

    case_name: str,

    body: TaskUpdate,

    db: Session = Depends(get_db),

    user: User = Depends(get_current_user),

):

    task = assert_user_can_access_case(db, user, case_name)

    data = body.model_dump(exclude_unset=True)

    if not data:

        raise HTTPException(status_code=400, detail="沒有要更新的欄位")


    if "project_id" in data:

        new_pid = data["project_id"]

        if new_pid is None:

            raise HTTPException(status_code=400, detail="project_id 不可為空")

        if new_pid != task.project_id:

            target = db.get(Project, new_pid)

            if target is None:

                raise HTTPException(status_code=404, detail="目標專案不存在")

            assert_project_member(db, user.id, new_pid)

            task.project_id = new_pid

            if task.assignee_id is not None:

                still_member = db.scalar(

                    select(ProjectUserLink).where(

                        ProjectUserLink.project_id == new_pid,

                        ProjectUserLink.user_id == task.assignee_id,

                    )

                )

                if still_member is None:

                    task.assignee_id = None


    if "status" in data:

        task.status = data["status"]


    if "assignee_id" in data:

        aid = data["assignee_id"]

        if aid is not None:

            assignee_user = db.get(User, aid)

            if assignee_user is None or not assignee_user.is_active:

                raise HTTPException(status_code=400, detail="負責人必須為已啟用之專案成員")

            link = db.scalar(

                select(ProjectUserLink).where(

                    ProjectUserLink.project_id == task.project_id,

                    ProjectUserLink.user_id == aid,

                )

            )

            if link is None:

                raise HTTPException(status_code=400, detail="負責人必須為專案成員")

        task.assignee_id = aid



    db.commit()

    db.refresh(task)

    return {

        "case_name": task.case_name,

        "status": task.status.value if isinstance(task.status, TaskStatus) else str(task.status),

        "assignee_id": task.assignee_id,

        "assignee_real_name": _assignee_real_name(db, task),

        "project_id": task.project_id,

    }
