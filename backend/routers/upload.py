"""
POST /api/upload, GET /api/status/{case_name}
"""
import os
import shutil
from typing import Callable
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks

from config import DATA_DIR


def create_upload_router(run_pipeline_fn: Callable[[str, str], None]) -> APIRouter:
    """建立上傳與狀態路由，需注入子流程函式（由 main 傳入 _run_pipeline_in_subprocess）。"""
    router = APIRouter(prefix="/api", tags=["upload"])

    @router.post("/upload")
    async def upload_video_endpoint(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        case_name: str = Form(...),
    ):
        try:
            file_ext = os.path.splitext(file.filename)[1]
            safe_filename = f"{case_name}{file_ext}"
            save_path = os.path.join(DATA_DIR, case_name, "source", safe_filename)
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            background_tasks.add_task(run_pipeline_fn, save_path, case_name)
            return {"status": "processing_started", "case_name": case_name, "message": "Pipeline started in background"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/status/{case_name}")
    async def get_status(case_name: str):
        from shared.file_manager import file_manager
        return file_manager.get_status(case_name)

    return router
