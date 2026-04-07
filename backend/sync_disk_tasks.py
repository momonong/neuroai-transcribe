"""
將 DATA_DIR 下既有的 case 資料夾同步為 Task（掛在「預設專案」）。
解決僅有磁碟目錄、資料庫無對應 Task 時前端列表與預設 demo 無法出現的問題。
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import DATA_DIR, IGNORE_DIRS
from models import Project, Task, TaskStatus


def sync_case_tasks_for_default_project(db: Session) -> int:
    """
    為預設專案補上資料夾已存在但 DB 尚無的 Task。回傳新增筆數。
    """
    project = db.scalar(select(Project).where(Project.name == "預設專案 (Default Project)"))
    if project is None:
        return 0

    data_path = Path(DATA_DIR)
    if not data_path.is_dir():
        return 0

    added = 0
    for item in data_path.iterdir():
        if not item.is_dir() or item.name.startswith(".") or item.name in IGNORE_DIRS:
            continue
        case_name = item.name
        existing = db.scalar(select(Task).where(Task.case_name == case_name))
        if existing is not None:
            continue
        db.add(
            Task(
                case_name=case_name,
                status=TaskStatus.PENDING,
                project_id=project.id,
                assignee_id=None,
            )
        )
        added += 1

    if added:
        db.commit()
    return added
