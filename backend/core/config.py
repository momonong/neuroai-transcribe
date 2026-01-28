"""
配置管理模組 - 統一管理所有設定
"""
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()


class Config:
    """應用程式配置類別"""
    
    def __init__(self):
        # ==========================================
        # 1. 基礎路徑設定
        # ==========================================
        # 專案根目錄 (backend/ 的上一層)
        self.backend_dir = Path(__file__).parent.parent
        self.project_root = self.backend_dir.parent
        
        # 資料根目錄 (只定義根在哪，不定義內部結構)
        self.data_dir = self.project_root / "data"
        
        # 模型快取目錄 (這是全域的，不隨案子變動，所以放這裡)
        self.model_cache_dir = os.getenv("MODEL_CACHE_DIR", str(self.project_root / "models"))
        
        # 全域資料庫或字典檔目錄 (如果有的話)
        self.db_dir = self.data_dir / "db"
        
        # ==========================================
        # 2. AI & 外部服務設定
        # ==========================================
        self.hf_token = os.getenv("HF_TOKEN")
        
        # LLM 配置
        self.llm_api_url = os.getenv("LLM_API_URL", "http://localhost:8000/v1")
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "sk-local")
        
        # Docker 環境檢測
        self.is_docker = os.path.exists("/.dockerenv")
        if self.is_docker:
            self.llm_api_url = self.llm_api_url.replace("localhost", "host.docker.internal")
        
        # ==========================================
        # 3. 演算法參數預設值
        # ==========================================
        self.default_num_chunks = int(os.getenv("DEFAULT_NUM_CHUNKS", "4"))
        self.silence_thresh = int(os.getenv("SILENCE_THRESH", "-40"))
        self.min_silence_len = int(os.getenv("MIN_SILENCE_LEN", "1000"))
        
        # Whisper 配置
        self.whisper_model = os.getenv("WHISPER_MODEL", "large-v3")
        self.whisper_language = os.getenv("WHISPER_LANGUAGE", "zh")
        self.whisper_beam_size = int(os.getenv("WHISPER_BEAM_SIZE", "5"))
        
        # GPU 配置
        self.device = "cuda" if os.getenv("USE_GPU", "true").lower() == "true" else "cpu"
        self.compute_type = os.getenv("COMPUTE_TYPE", "float16")
        
        # 測試者名稱 (用於隱藏敏感資訊)
        self.tester_name = os.getenv("TESTER_NAME")
        
        # 初始化時確保基礎設施存在
        self._ensure_directories()
    
    def _ensure_directories(self):
        """確保所有必要的「全域」目錄存在"""
        # 注意：這裡不再建立 temp_chunks，因為那是跟著案子走的
        directories = [
            self.data_dir,
            self.db_dir,
            Path(self.model_cache_dir)
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    def get_safe_filename(self, file_path: str) -> str:
        """用於 Log 顯示，隱藏敏感資訊 (Utility function)"""
        if self.tester_name and self.tester_name in file_path:
            return file_path.replace(self.tester_name, "[Name]")
        return file_path
    
    def to_dict(self) -> dict:
        """轉換為字典格式，方便除錯"""
        return {
            "project_root": str(self.project_root),
            "data_dir": str(self.data_dir),
            "model_cache_dir": self.model_cache_dir,
            "device": self.device,
            "whisper_model": self.whisper_model,
            "llm_api_url": self.llm_api_url,
            "is_docker": self.is_docker
        }


# 建立全域配置實例
config = Config()

# 設定環境變數 (供 HuggingFace 函式庫使用)
os.environ["HF_HOME"] = config.model_cache_dir
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"