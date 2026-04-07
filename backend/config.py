"""
後端路徑與常數設定。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# 取得當前檔案 (backend/config.py) 的絕對路徑
_CURRENT_FILE = os.path.abspath(__file__)
# 取得 backend 資料夾路徑
BACKEND_DIR = os.path.dirname(_CURRENT_FILE)
# 取得專案根目錄 (backend 的上一層)
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)

# 設定 DATA_DIR 為專案根目錄下的 data
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

# 確保資料夾存在
os.makedirs(DATA_DIR, exist_ok=True)

# 掃描影片與 cases 時要排除的資料夾名稱
IGNORE_DIRS = {"temp_chunks", "db", "text", "__pycache__", "output", "test-complete-pipeline"}

# PostgreSQL（docker-compose 內為 db:5432；本機開發可設 DATABASE_URL 指向 localhost）
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://neuroai:neuroai_secret@localhost:5432/neuroai_db",
)

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))


def get_real_path(relative_path: str) -> str:
    """將前端傳來的相對路徑轉換為系統絕對路徑。"""
    if ".." in relative_path:
        raise ValueError("Invalid path: '..' is not allowed")
    return os.path.join(DATA_DIR, relative_path)
