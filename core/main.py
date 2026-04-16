import os
import sys
import subprocess
import logging
from pathlib import Path
from typing import Dict

from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

# 設定 Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("core-service")

# 取得路徑
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

app = FastAPI(title="NeuroAI Core Inference Service")

# 定義 Request Body 格式
class ProcessRequest(BaseModel):
    case_name: str
    file_path: str

def run_inference_task(case_name: str, file_path: str):
    """
    實際執行 GPU 推理的任務（背景執行）。
    呼叫原本的 core.run_pipeline 模組。
    """
    logger.info(f" [Task Start] 開始處理案例: {case_name}, 檔案路徑: {file_path}")
    
    try:
        # 設定環境變數
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        
        # 指令：python -m core.run_pipeline <file_path> --case <case_name>
        cmd = [
            sys.executable, "-m", "core.run_pipeline",
            file_path,
            "--case", case_name
        ]
        
        logger.info(f" [Executing] 指令: {' '.join(cmd)}")
        
        # 執行並捕捉輸出
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=True,
            env=env
        )
        
        logger.info(f" [Task Success] 案例 {case_name} 處理完成。")
        logger.debug(f" [Output]: {result.stdout}")

    except subprocess.CalledProcessError as e:
        logger.error(f" [Task Failed] 案例 {case_name} 執行失敗。")
        logger.error(f" [Error Output]: {e.stderr}")
    except Exception as e:
        logger.error(f" [System Error] 發生未預期錯誤: {str(e)}")

@app.post("/process")
async def process_video(request: ProcessRequest, background_tasks: BackgroundTasks):
    """
    觸發轉錄推理的端點。
    驗證路徑後立刻回傳，並在背景執行運算。
    """
    case_name = request.case_name
    file_path = request.file_path

    # 1. 驗證檔案是否存在
    # 注意：file_path 應該是絕對路徑，或是相對於容器內 /app/data 的路徑
    if not os.path.exists(file_path):
        logger.warning(f" [404] 找不到檔案: {file_path}")
        raise HTTPException(status_code=404, detail=f"File not found at {file_path}")

    # 2. 加入背景任務
    background_tasks.add_task(run_inference_task, case_name, file_path)

    logger.info(f" [Accepted] 案例 {case_name} 已加入背景執行隊列。")
    
    return {
        "status": "task_accepted",
        "case_name": case_name,
        "message": "Inference started in background"
    }

@app.get("/health")
async def health_check():
    """健康檢查端點，顯示 GPU 狀態。"""
    gpu_available = os.path.exists("/dev/nvidia0")
    return {
        "status": "healthy",
        "gpu_detected": gpu_available
    }

if __name__ == "__main__":
    import uvicorn
    # 預設跑在 8003 埠
    uvicorn.run(app, host="0.0.0.0", port=8003)
