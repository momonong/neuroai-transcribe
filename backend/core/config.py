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
        # 專案根目錄 (backend/ 的上一層)
        self.backend_dir = Path(__file__).parent.parent
        self.project_root = self.backend_dir.parent
        
        # 資料目錄配置 - 新的扁平化結構
        self.data_dir = self.project_root / "data"
        self.temp_chunks_dir = self.data_dir / "temp_chunks"
        self.db_dir = self.data_dir / "db"
        self.text_dir = self.data_dir / "text"
        
        # AI 模型配置
        self.model_cache_dir = os.getenv("MODEL_CACHE_DIR", str(self.project_root / "models"))
        self.hf_token = os.getenv("HF_TOKEN")
        
        # LLM 配置
        self.llm_api_url = os.getenv("LLM_API_URL", "http://localhost:8000/v1")
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "sk-local")
        
        # Docker 環境檢測
        self.is_docker = os.path.exists("/.dockerenv")
        if self.is_docker:
            # Docker 環境中使用 host.docker.internal
            self.llm_api_url = self.llm_api_url.replace("localhost", "host.docker.internal")
        
        # 音訊處理配置
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
        
        # 確保必要目錄存在
        self._ensure_directories()
    
    def _ensure_directories(self):
        """確保所有必要的目錄存在"""
        directories = [
            self.data_dir,
            self.temp_chunks_dir,
            self.db_dir,
            self.text_dir,
            Path(self.model_cache_dir)
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    def get_safe_filename(self, file_path: str) -> str:
        """用於 Log 顯示，隱藏敏感資訊"""
        if self.tester_name and self.tester_name in file_path:
            return file_path.replace(self.tester_name, "[Name]")
        return file_path
    
    def get_case_dir(self, case_name: str) -> Path:
        """取得案例目錄路徑 (直接在 data/ 下)"""
        case_dir = self.data_dir / case_name
        case_dir.mkdir(parents=True, exist_ok=True)
        return case_dir
    
    def get_temp_chunks_dir(self, case_name: Optional[str] = None) -> Path:
        """取得暫存 chunks 目錄"""
        if case_name:
            # 在特定案例目錄下建立 temp_chunks
            chunks_dir = self.get_case_dir(case_name) / "temp_chunks"
        else:
            # 使用全域 temp_chunks 目錄
            chunks_dir = self.temp_chunks_dir
        
        chunks_dir.mkdir(parents=True, exist_ok=True)
        return chunks_dir
    
    def to_dict(self) -> dict:
        """轉換為字典格式，方便除錯"""
        return {
            "project_root": str(self.project_root),
            "data_dir": str(self.data_dir),
            "temp_chunks_dir": str(self.temp_chunks_dir),
            "db_dir": str(self.db_dir),
            "model_cache_dir": self.model_cache_dir,
            "device": self.device,
            "compute_type": self.compute_type,
            "whisper_model": self.whisper_model,
            "llm_api_url": self.llm_api_url,
            "is_docker": self.is_docker,
            "default_num_chunks": self.default_num_chunks
        }


# 建立全域配置實例
config = Config()

# 設定環境變數 (供其他模組使用)
os.environ["HF_HOME"] = config.model_cache_dir
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"