import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# 從 backend/ 執行時，將專案根加入 path，才能 import shared（Production 映像僅含 backend + shared）
_backend_dir = Path(__file__).resolve().parent
_project_root = _backend_dir.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import models  # noqa: F401 — 註冊 ORM 對應
from database import SessionLocal, engine
from fastapi import FastAPI
from sqlalchemy import inspect, text
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from models import Base

from config import DATA_DIR, PROJECT_ROOT
from routers import admin, auth, chunks, export, projects, upload, videos
from sync_disk_tasks import sync_case_tasks_for_default_project


def _ensure_users_is_active_column() -> None:
    """既有資料庫補上 users.is_active（create_all 不會改欄位）。"""
    try:
        inspector = inspect(engine)
    except Exception:
        return
    if not inspector.has_table("users"):
        return
    cols = {c["name"] for c in inspector.get_columns("users")}
    if "is_active" in cols:
        return
    dialect = engine.dialect.name
    with engine.begin() as conn:
        if dialect == "sqlite":
            conn.execute(
                text("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1")
            )
        else:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT true")
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _ensure_users_is_active_column()
    db = SessionLocal()
    try:
        sync_case_tasks_for_default_project(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    yield


app = FastAPI(lifespan=lifespan)

print("Server started.")
print(f"Project Root: {PROJECT_ROOT}")
print(f"Data Directory: {DATA_DIR}")


def _trigger_core_process(video_path: str, case_name: str) -> None:
    """向 core 服務發送請求以啟動推理 Pipeline。"""
    import requests
    import logging
    
    logger = logging.getLogger("uvicorn.error")
    core_url = "http://core:8003/process"
    payload = {
        "case_name": case_name,
        "file_path": video_path
    }
    
    try:
        logger.info(f"正在觸發 Core 服務處理: {case_name}")
        response = requests.post(core_url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info(f"Core 服務已接受任務: {response.json()}")
    except Exception as e:
        logger.error(f"觸發 Core 服務失敗: {str(e)}")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=DATA_DIR), name="static")

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(projects.router)
app.include_router(videos.router)
app.include_router(chunks.router)
app.include_router(upload.create_upload_router(_trigger_core_process))
app.include_router(export.router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
