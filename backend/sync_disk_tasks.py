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


from sqlalchemy import update


def sync_all_cases(db: Session) -> dict:
    """
    雙向同步：
    1. 掃描磁碟：若有新資料夾則加入「預設專案」。
    2. 檢查資料庫：若資料夾已消失，將任務移至「Deleted tasks」。
    """
    # --- 1. 處理新資料夾 ---
    default_project = db.scalar(select(Project).where(Project.name == "預設專案 (Default Project)"))
    if default_project is None:
        # 如果預設專案不存在，先建立
        default_project = Project(name="預設專案 (Default Project)", description="自動掃描發現的新案源。")
        db.add(default_project)
        db.flush()

    data_path = Path(DATA_DIR)
    added_count = 0
    disk_case_names = set()
    
    if data_path.is_dir():
        for item in data_path.iterdir():
            if not item.is_dir() or item.name.startswith(".") or item.name in IGNORE_DIRS:
                continue
            case_name = item.name
            disk_case_names.add(case_name)
            
            existing = db.scalar(select(Task).where(Task.case_name == case_name))
            if existing is None:
                db.add(
                    Task(
                        case_name=case_name,
                        status=TaskStatus.PENDING,
                        project_id=default_project.id,
                    )
                )
                added_count += 1

    # --- 2. 處理資料庫中的孤兒任務 ---
    recycle_bin_name = "Deleted tasks"
    recycle_bin = db.scalar(select(Project).where(Project.name == recycle_bin_name))
    if recycle_bin is None:
        recycle_bin = Project(name=recycle_bin_name, description="存放被刪除專案或磁碟路徑遺失的任務。")
        db.add(recycle_bin)
        db.flush()

    # 找出所有在資料庫中但不在磁碟上的任務，且目前不屬於回收站的
    orphan_tasks = db.scalars(
        select(Task).where(
            Task.case_name.notin_(disk_case_names),
            Task.project_id != recycle_bin.id
        )
    ).all()
    
    moved_count = len(orphan_tasks)
    for task in orphan_tasks:
        task.project_id = recycle_bin.id

    db.commit()
    return {"added": added_count, "moved_to_recycle_bin": moved_count}


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
