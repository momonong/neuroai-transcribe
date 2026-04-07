"""
POST /api/upload, GET /api/status/{case_name}
"""
import os
import shutil
from typing import Callable

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from database import get_db
from deps import assert_project_member, assert_user_can_access_case, get_current_user, get_task_for_case
from models import Task, TaskStatus, User


def create_upload_router(run_pipeline_fn: Callable[[str, str], None]) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["upload"])

    @router.post("/upload")
    async def upload_video_endpoint(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        case_name: str = Form(...),
        project_id: int = Form(...),
        db: Session = Depends(get_db),
        user: User = Depends(get_current_user),
    ):
        assert_project_member(db, user.id, project_id)
        existing = get_task_for_case(db, case_name)
        if existing is not None and existing.project_id != project_id:
            raise HTTPException(status_code=400, detail="此案例已屬於其他專案")

        try:
            from config import DATA_DIR

            file_ext = os.path.splitext(file.filename or "")[1]
            safe_filename = f"{case_name}{file_ext}"
            save_path = os.path.join(DATA_DIR, case_name, "source", safe_filename)
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            if existing is None:
                db.add(
                    Task(
                        case_name=case_name,
                        project_id=project_id,
                        status=TaskStatus.PENDING,
                    )
                )
            db.commit()
            background_tasks.add_task(run_pipeline_fn, save_path, case_name)
            return {
                "status": "processing_started",
                "case_name": case_name,
                "message": "Pipeline started in background",
            }
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/status/{case_name}")
    async def get_status(
        case_name: str,
        db: Session = Depends(get_db),
        user: User = Depends(get_current_user),
    ):
        assert_user_can_access_case(db, user, case_name)
        from shared.file_manager import file_manager

        return file_manager.get_status(case_name)

    return router
