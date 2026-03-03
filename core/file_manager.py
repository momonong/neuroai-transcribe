"""
檔案管理模組 - 統一處理所有檔案路徑和儲存邏輯 (Refactored for 3-Tier Structure)
core 位於專案根目錄，base_dir = 專案根
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
        """
        初始化檔案管理器
        Args:
            base_dir: 專案根目錄；若為 None 則自動偵測（core 的上一層 = 專案根）
        """
        if base_dir is None:
            # core 位於專案根目錄下，故 parent.parent = 專案根
            current_file = Path(__file__).resolve()
            self.base_dir = current_file.parent.parent
        else:
            self.base_dir = Path(base_dir)
            
        # 定義資料夾根目錄
        self.data_dir = self.base_dir / "data"
        
        # 確保 data 資料夾存在
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    # ==========================================
    # 核心路徑取得方法 (配合三層架構)
    # ==========================================
    
    def get_case_dir(self, case_name: str) -> Path:
        """取得案例根目錄 data/{case_name}"""
        return self.data_dir / case_name

    def get_source_dir(self, case_name: str) -> Path:
        """取得原始檔目錄 data/{case_name}/source"""
        return self.get_case_dir(case_name) / "source"

    def get_intermediate_dir(self, case_name: str) -> Path:
        """取得中間產物目錄 data/{case_name}/intermediate"""
        return self.get_case_dir(case_name) / "intermediate"

    def get_output_dir(self, case_name: str) -> Path:
        """取得成品目錄 data/{case_name}/output"""
        return self.get_case_dir(case_name) / "output"
    
    # ==========================================
    # 具體檔案路徑生成
    # ==========================================

    def get_chunk_file_path(self, chunk_id: int, start_ms: int, end_ms: int, 
                            case_name: str, suffix: str = "") -> Path:
        """
        生成 chunk 檔案路徑
        位置：data/{case_name}/intermediate/chunk_X.wav
        """
        intermediate_dir = self.get_intermediate_dir(case_name)
        intermediate_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"chunk_{chunk_id}_{start_ms}_{end_ms}{suffix}.wav"
        return intermediate_dir / filename
    
    def get_output_file_path(self, case_name: str, filename: str) -> Path:
        """
        生成輸出檔案路徑
        位置：data/{case_name}/output/{filename}
        """
        output_dir = self.get_output_dir(case_name)
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / filename

    # ==========================================
    # 案例管理 logic
    # ==========================================
    
    def create_case(self, video_path: str, case_name: Optional[str] = None) -> str:
        """
        建立新案例並初始化三層資料夾結構
        """
        video_path_obj = Path(video_path)
        
        if case_name is None:
            case_name = video_path_obj.stem
        
        # 1. 建立目錄結構
        case_dir = self.get_case_dir(case_name)
        source_dir = self.get_source_dir(case_name)
        inter_dir = self.get_intermediate_dir(case_name)
        out_dir = self.get_output_dir(case_name)
        
        for d in [case_dir, source_dir, inter_dir, out_dir]:
            d.mkdir(parents=True, exist_ok=True)
            
        # 2. 將影片複製或移動到 source 資料夾
        target_video_path = source_dir / video_path_obj.name
        
        if video_path_obj.resolve() != target_video_path.resolve():
            try:
                if video_path_obj.exists():
                    print(f"📦 Copying video to source dir: {target_video_path}")
                    shutil.copy2(video_path_obj, target_video_path)
                else:
                    print(f"⚠️ Warning: Original video not found at {video_path}")
            except Exception as e:
                print(f"❌ Failed to copy video: {e}")

        # 3. 建立設定檔
        case_config = {
            "case_name": case_name,
            "original_filename": video_path_obj.name,
            "created_at": datetime.now().isoformat(),
            "status": "created",
            "paths": {
                "source": str(source_dir.relative_to(self.base_dir)),
                "intermediate": str(inter_dir.relative_to(self.base_dir)),
                "output": str(out_dir.relative_to(self.base_dir))
            }
        }
        
        self.save_json(case_config, case_dir / "case.json", backup=False)
        return case_name

    # ==========================================
    # 影片與檔案搜尋
    # ==========================================

    def find_video_files(self, pattern: Optional[str] = None) -> List[Dict[str, Any]]:
        """搜尋系統中所有案例的影片"""
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
                        if file_path.suffix.lower() not in video_extensions:
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

    def get_chunk_json_files(self, case_name: str, file_type: str = "all") -> List[str]:
        """從 intermediate 資料夾讀取 JSON"""
        inter_dir = self.get_intermediate_dir(case_name)
        if not inter_dir.exists():
            return []
            
        files = []
        for file_path in inter_dir.glob("*.json"):
            fname = file_path.name
            
            if file_type == "flagged":
                if "flagged" in fname: files.append(fname)
            elif file_type == "corrected":
                if "corrected" in fname: files.append(fname)
            elif file_type == "aligned":
                if "aligned" in fname: files.append(fname)
            else:
                files.append(fname)
                
        files.sort()
        return files

    # ==========================================
    # 通用工具
    # ==========================================
    
    def save_json(self, data: Any, file_path: Path, backup: bool = True) -> bool:
        """通用儲存 JSON"""
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
        """通用讀取 JSON"""
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                return None
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ Load JSON Error: {e}")
            return None

    # ==========================================
    # 進度狀態管理
    # ==========================================

    def save_status(self, case_name: str, step: str, progress: int, message: str = ""):
            """儲存目前的 Pipeline 進度到 status.json"""
            status_file = self.get_source_dir(case_name).parent / "status.json"
            data = {
                "case_name": case_name,
                "step": step,
                "progress": progress,
                "message": message,
                "timestamp": time.time()
            }
            try:
                with open(status_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
            except Exception as e:
                print(f"⚠️ Failed to save status: {e}")

    def get_status(self, case_name: str) -> Dict:
        """讀取目前的進度"""
        status_file = self.get_source_dir(case_name).parent / "status.json"
        if not status_file.exists():
            return {"progress": 0, "step": "Init", "message": "Waiting..."}
        try:
            with open(status_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"progress": 0, "step": "Error", "message": "Cannot read status"}

    # ==========================================
    # 資料集合併 + 下載
    # ==========================================

    def merge_chunks(self, case_name: str, suffix: str) -> List[Dict]:
        """合併指定案例的所有 Chunk 資料"""
        inter_dir = self.get_intermediate_dir(case_name)
        if not inter_dir.exists():
            print(f"❌ [Merge] Directory not found: {inter_dir}")
            return []

        all_files = list(inter_dir.glob("*.json"))
        target_key = suffix.replace(".json", "") 
        
        files = []
        for f in all_files:
            if f.name.endswith(suffix):
                files.append(f)
            elif target_key in f.name and "json" in f.suffix:
                files.append(f)

        if not files:
            print(f"⚠️ [Merge] No files found matching '{suffix}'.")
            if "edited" in suffix:
                print("   ↪ Falling back to '_flagged_for_human.json'")
                return self.merge_chunks(case_name, "_flagged_for_human.json")
            return []

        def sort_key(f):
            try:
                parts = f.name.split('_')
                for p in parts:
                    if p.isdigit():
                        return int(p)
                return 0
            except Exception:
                return 0
        files.sort(key=sort_key)
        
        print(f"📦 [Merge] Found {len(files)} files for {suffix}. Merging...")

        merged_data = []
        for f in files:
            try:
                data = self.load_json(f)
                items_to_add = []
                
                if isinstance(data, list):
                    items_to_add = data
                elif isinstance(data, dict):
                    for key in ["segments", "data", "results", "chunks"]:
                        if key in data and isinstance(data[key], list):
                            items_to_add = data[key]
                            break
                
                if items_to_add:
                    merged_data.extend(items_to_add)
                else:
                    print(f"   ⚠️ {f.name} is valid JSON but contains no list data (Structure: {type(data)})")

            except Exception as e:
                print(f"⚠️ [Merge] Error reading {f.name}: {e}")
        
        print(f"✅ [Merge] Total merged items: {len(merged_data)}")
        return merged_data


# 建立全域實例（使用 core.config 的 project_root 可選，這裡自動偵測專案根）
file_manager = FileManager()
