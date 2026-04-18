"""
配置管理模組 - 統一管理所有設定
core 位於專案根目錄，project_root = core 的上一層
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
        # 專案根目錄：core/ 的上一層（core 現位於專案根目錄下）
        _core_dir = Path(__file__).resolve().parent
        self.project_root = _core_dir.parent
        
        # backend 目錄（供需要時使用）
        self.backend_dir = self.project_root / "backend"
        
        # 資料根目錄 (只定義根在哪，不定義內部結構)
        self.data_dir = self.project_root / "data"
        
        # 模型快取目錄 (這是全域的，不隨案子變動，所以放這裡)
        self.model_cache_dir = os.getenv("MODEL_CACHE_DIR", str(self.project_root / "models"))
        
        # ==========================================
        # 2. AI & 外部服務設定
        # ==========================================
        self.hf_token = os.getenv("HF_TOKEN")
        
        # LLM 配置
        self.llm_api_url = os.getenv("LLM_API_URL", "http://localhost:8000/v1")
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "sk-local")
        self.llm_model_name = os.getenv("LLM_MODEL_NAME", "gemma-3-12b")
        
        # Docker 環境檢測：將 localhost 或 127.0.0.1 替換為 Docker 橋接主機 IP
        self.is_docker = os.path.exists("/.dockerenv")
        if self.is_docker:
            for host in ["localhost", "127.0.0.1"]:
                if host in self.llm_api_url:
                    self.llm_api_url = self.llm_api_url.replace(host, "host.docker.internal")
                    break
        
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

        # 語者／diarization：whisper_bilstm（預設）| pyannote | placeholder（依 Whisper 段寫假 diar）
        _db = os.getenv("DIARIZATION_BACKEND", "whisper_bilstm").strip().lower()
        if _db in ("pyannote", "hf", "huggingface"):
            self.diarization_backend = "pyannote"
        elif _db in ("whisper_bilstm", "bilstm", "custom_speaker", "speaker_model"):
            self.diarization_backend = "whisper_bilstm"
        elif _db in ("placeholder", "noop", "stub"):
            self.diarization_backend = "placeholder"
        else:
            print(
                f"⚠️ 未知的 DIARIZATION_BACKEND={_db!r}，改用 pyannote",
                flush=True,
            )
            self.diarization_backend = "pyannote"
        self.speaker_model_path = os.getenv(
            "SPEAKER_MODEL_PATH",
            str(self.project_root / "models" / "whisper_medium_bilstm_best.pt"),
        )
        self.speaker_placeholder_label = os.getenv(
            "SPEAKER_PLACEHOLDER_LABEL", "PLACEHOLDER_SPEAKER"
        )
        _labels = os.getenv("SPEAKER_CLASS_LABELS", "").strip()
        self.speaker_class_labels = [
            x.strip() for x in _labels.split(",") if x.strip()
        ] if _labels else []
        
        # GPU 配置
        self.device = "cuda" if os.getenv("USE_GPU", "true").lower() == "true" else "cpu"
        self.compute_type = os.getenv("COMPUTE_TYPE", "float16")

        # 跳過規則併句：aligned 逐段直通 Flag（環境變數 SKIP_STITCH=true/1）
        self.skip_stitch = os.getenv("SKIP_STITCH", "").lower() in ("1", "true", "yes")
        # Rule-based stitch 合併閾值（秒）
        self.stitch_merge_max_gap_sec = float(
            os.getenv("STITCH_MERGE_MAX_GAP_SEC", "1.5")
        )
        # 單句最大字數限制
        self.stitch_max_chars = int(os.getenv("STITCH_MAX_CHARS", "80"))
        # 軟性字數限制（達到此長度後會更嚴格檢查停頓）
        self.stitch_soft_max_chars = int(os.getenv("STITCH_SOFT_MAX_CHARS", "40"))
        # 軟性停頓門檻（達到軟性字數後的停頓門檻，秒）
        self.stitch_soft_gap_sec = float(os.getenv("STITCH_SOFT_GAP_SEC", "0.5"))
        
        # 測試者名稱 (用於隱藏敏感資訊)
        self.tester_name = os.getenv("TESTER_NAME")
        
        # 初始化時確保基礎設施存在
        self._ensure_directories()
    
    def _ensure_directories(self):
        """確保所有必要的「全域」目錄存在"""
        directories = [
            self.data_dir,
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
            "is_docker": self.is_docker,
            "skip_stitch": self.skip_stitch,
            "stitch_merge_max_gap_sec": self.stitch_merge_max_gap_sec,
            "diarization_backend": self.diarization_backend,
            "speaker_model_path": self.speaker_model_path,
            "speaker_placeholder_label": self.speaker_placeholder_label,
            "speaker_class_labels": self.speaker_class_labels,
        }


# 建立全域配置實例
config = Config()

# 設定環境變數 (供 HuggingFace 函式庫使用)
os.environ["HF_HOME"] = config.model_cache_dir
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
