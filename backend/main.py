import os
import sys
from pathlib import Path

# 從 backend/ 執行時，將專案根加入 path，才能 import shared（Production 映像僅含 backend + shared）
_backend_dir = Path(__file__).resolve().parent
_project_root = _backend_dir.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import DATA_DIR, PROJECT_ROOT
from routers import videos, chunks, export, upload

app = FastAPI()

print(f"🚀 Server started.")
print(f"📂 Project Root: {PROJECT_ROOT}")
print(f"📂 Data Directory: {DATA_DIR}")


def _run_pipeline_in_subprocess(video_path: str, case_name: str) -> None:
    """在子流程執行 core pipeline，避免 main 載入 torch/whisper。供 background_tasks 呼叫。"""
    import subprocess
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    subprocess.run(
        [sys.executable, "-m", "core.run_pipeline", video_path, "--case", case_name],
        cwd=str(PROJECT_ROOT),
        env=env,
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=DATA_DIR), name="static")

app.include_router(videos.router)
app.include_router(chunks.router)
app.include_router(upload.create_upload_router(_run_pipeline_in_subprocess))
app.include_router(export.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
