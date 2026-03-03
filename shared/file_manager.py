"""
檔案管理模組 - 統一處理路徑與儲存邏輯 (data/{case}/source|intermediate|output)
供 backend 使用；base_dir = 專案根（在 Docker 中為 /app）
"""
import os
import json
import shutil
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime


class FileManager:
    """統一的檔案管理器"""

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir is None:
            current_file = Path(__file__).resolve()
            self.base_dir = current_file.parent.parent  # shared/ 的上一層
        else:
            self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def get_case_dir(self, case_name: str) -> Path:
        return self.data_dir / case_name

    def get_source_dir(self, case_name: str) -> Path:
        return self.get_case_dir(case_name) / "source"

    def get_intermediate_dir(self, case_name: str) -> Path:
        return self.get_case_dir(case_name) / "intermediate"

    def get_output_dir(self, case_name: str) -> Path:
        return self.get_case_dir(case_name) / "output"

    def get_output_file_path(self, case_name: str, filename: str) -> Path:
        output_dir = self.get_output_dir(case_name)
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / filename

    def create_case(self, video_path: str, case_name: Optional[str] = None) -> str:
        video_path_obj = Path(video_path)
        if case_name is None:
            case_name = video_path_obj.stem
        case_dir = self.get_case_dir(case_name)
        source_dir = self.get_source_dir(case_name)
        inter_dir = self.get_intermediate_dir(case_name)
        out_dir = self.get_output_dir(case_name)
        for d in [case_dir, source_dir, inter_dir, out_dir]:
            d.mkdir(parents=True, exist_ok=True)
        target_video_path = source_dir / video_path_obj.name
        if video_path_obj.resolve() != target_video_path.resolve():
            try:
                if video_path_obj.exists():
                    shutil.copy2(video_path_obj, target_video_path)
            except Exception as e:
                print(f"❌ Failed to copy video: {e}")
        case_config = {
            "case_name": case_name,
            "original_filename": video_path_obj.name,
            "created_at": datetime.now().isoformat(),
            "status": "created",
        }
        self.save_json(case_config, case_dir / "case.json", backup=False)
        return case_name

    def find_video_files(self, pattern: Optional[str] = None) -> List[Dict[str, Any]]:
        video_extensions = [".mp4", ".mov", ".avi", ".mp3", ".wav", ".m4a"]
        video_files = []
        if not self.data_dir.exists():
            return video_files
        for case_dir in self.data_dir.iterdir():
            if not case_dir.is_dir() or case_dir.name.startswith("."):
                continue
            source_dir = case_dir / "source"
            search_dirs = [source_dir] if source_dir.exists() else [case_dir]
            for search_dir in search_dirs:
                for ext in video_extensions:
                    for file_path in search_dir.glob(f"*{ext}"):
                        if file_path.suffix.lower() not in [e.lower() for e in video_extensions]:
                            continue
                        if pattern and pattern.lower() not in file_path.name.lower():
                            continue
                        try:
                            video_files.append({
                                "name": file_path.name,
                                "case_name": case_dir.name,
                                "path": str(file_path),
                                "relative_path": str(file_path.relative_to(self.base_dir)).replace("\\", "/"),
                                "size": file_path.stat().st_size,
                                "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                            })
                        except Exception:
                            continue
        video_files.sort(key=lambda x: x["modified"], reverse=True)
        return video_files

    def save_json(self, data: Any, file_path: Path, backup: bool = True) -> bool:
        try:
            file_path = Path(file_path)
            if backup and file_path.exists():
                ts = int(datetime.now().timestamp())
                backup_path = file_path.with_suffix(f".bak_{ts}.json")
                file_path.rename(backup_path)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"❌ Save JSON Error: {e}")
            return False

    def load_json(self, file_path: Path) -> Optional[Any]:
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                return None
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ Load JSON Error: {e}")
            return None

    def save_status(self, case_name: str, step: str, progress: int, message: str = ""):
        status_file = self.get_source_dir(case_name).parent / "status.json"
        data = {"case_name": case_name, "step": step, "progress": progress, "message": message, "timestamp": time.time()}
        try:
            with open(status_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Failed to save status: {e}")

    def get_status(self, case_name: str) -> Dict:
        status_file = self.get_source_dir(case_name).parent / "status.json"
        if not status_file.exists():
            return {"progress": 0, "step": "Init", "message": "Waiting..."}
        try:
            with open(status_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"progress": 0, "step": "Error", "message": "Cannot read status"}

    def merge_chunks(self, case_name: str, suffix: str) -> List[Dict]:
        inter_dir = self.get_intermediate_dir(case_name)
        if not inter_dir.exists():
            return []
        target_key = suffix.replace(".json", "")
        files = []
        for f in inter_dir.glob("*.json"):
            if f.name.endswith(suffix) or (target_key in f.name and "json" in f.suffix):
                files.append(f)
        if not files:
            if "edited" in suffix:
                return self.merge_chunks(case_name, "_flagged_for_human.json")
            return []
        def sort_key(f):
            for p in f.name.split("_"):
                if p.isdigit():
                    return int(p)
            return 0
        files.sort(key=sort_key)
        merged_data = []
        for f in files:
            try:
                data = self.load_json(f)
                items = []
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    for key in ["segments", "data", "results", "chunks"]:
                        if key in data and isinstance(data[key], list):
                            items = data[key]
                            break
                merged_data.extend(items)
            except Exception:
                continue
        return merged_data


file_manager = FileManager()
