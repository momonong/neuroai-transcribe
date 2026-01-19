"""
檔案管理模組 - 統一處理所有檔案路徑和儲存邏輯
"""
import os
import glob
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime


class FileManager:
    """統一的檔案管理器"""
    
    def __init__(self, base_dir: Optional[str] = None):
        """
        初始化檔案管理器
        
        Args:
            base_dir: 專案根目錄，預設為 backend/ 的上一層
        """
        if base_dir is None:
            # 自動偵測專案根目錄 (backend/ 的上一層)
            current_file = Path(__file__).resolve()
            backend_dir = current_file.parent.parent  # backend/core/ -> backend/ -> project/
            self.base_dir = backend_dir.parent
        else:
            self.base_dir = Path(base_dir)
            
        # 定義標準資料夾結構
        self.data_dir = self.base_dir / "data"
        self.asd_dir = self.data_dir / "ASD"
        self.temp_chunks_dir = self.data_dir / "temp_chunks"
        self.output_dir = self.data_dir / "output"
        
        # 確保資料夾存在
        self._ensure_directories()
    
    def _ensure_directories(self):
        """確保所有必要的資料夾存在"""
        directories = [
            self.data_dir,
            self.asd_dir, 
            self.temp_chunks_dir,
            self.output_dir
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    # ==========================================
    # 路徑生成方法
    # ==========================================
    
    def get_project_dir(self, project_name: str) -> Path:
        """取得專案目錄路徑"""
        project_dir = self.output_dir / project_name
        project_dir.mkdir(parents=True, exist_ok=True)
        return project_dir
    
    def get_temp_chunks_dir(self, project_name: Optional[str] = None) -> Path:
        """取得暫存 chunks 目錄"""
        if project_name:
            chunks_dir = self.get_project_dir(project_name) / "temp_chunks"
        else:
            chunks_dir = self.temp_chunks_dir
        
        chunks_dir.mkdir(parents=True, exist_ok=True)
        return chunks_dir
    
    def get_chunk_file_path(self, chunk_id: int, start_ms: int, end_ms: int, 
                           project_name: Optional[str] = None, suffix: str = "") -> Path:
        """生成 chunk 檔案路徑"""
        chunks_dir = self.get_temp_chunks_dir(project_name)
        filename = f"chunk_{chunk_id}_{start_ms}_{end_ms}{suffix}.wav"
        return chunks_dir / filename
    
    def get_output_file_path(self, project_name: str, filename: str) -> Path:
        """取得輸出檔案路徑"""
        return self.get_project_dir(project_name) / filename
    
    # ==========================================
    # 影片檔案管理
    # ==========================================
    
    def find_video_files(self, pattern: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        搜尋影片檔案
        
        Args:
            pattern: 搜尋模式，如檔名的一部分
            
        Returns:
            影片檔案清單，包含路徑和元資料
        """
        video_extensions = ["*.mp4", "*.MP4", "*.mov", "*.MOV", "*.avi", "*.AVI"]
        video_files = []
        
        for ext in video_extensions:
            # 遞迴搜尋 ASD 目錄
            pattern_path = self.asd_dir / "**" / ext
            files = glob.glob(str(pattern_path), recursive=True)
            
            for file_path in files:
                file_path = Path(file_path)
                
                # 如果有指定模式，進行過濾
                if pattern and pattern.lower() not in file_path.name.lower():
                    continue
                
                # 計算相對於 data 目錄的路徑
                try:
                    relative_path = file_path.relative_to(self.data_dir)
                    # 轉換為 URL 友善的路徑 (使用正斜線)
                    url_path = str(relative_path).replace("\\", "/")
                    
                    video_files.append({
                        "name": file_path.name,
                        "path": url_path,
                        "full_path": str(file_path),
                        "size": file_path.stat().st_size if file_path.exists() else 0,
                        "modified": datetime.fromtimestamp(
                            file_path.stat().st_mtime
                        ).isoformat() if file_path.exists() else None
                    })
                except ValueError:
                    # 檔案不在 data 目錄下，跳過
                    continue
        
        # 按修改時間排序 (最新的在前)
        video_files.sort(key=lambda x: x["modified"] or "", reverse=True)
        return video_files
    
    def find_best_video_match(self, reference_name: str) -> Optional[str]:
        """
        根據參考名稱找到最佳匹配的影片
        
        Args:
            reference_name: 參考名稱 (如 JSON 檔名)
            
        Returns:
            最佳匹配的影片相對路徑，如果沒找到則返回 None
        """
        video_files = self.find_video_files()
        
        if not video_files:
            return None
        
        # 提取參考名稱中的關鍵字 (移除常見的後綴)
        clean_ref = reference_name.lower()
        for suffix in ["_flagged_for_human", "_corrected", "_aligned", "_whisper", "_diar"]:
            clean_ref = clean_ref.replace(suffix, "")
        clean_ref = clean_ref.replace(".json", "").replace(".wav", "")
        
        # 嘗試找到名稱匹配的影片
        for video in video_files:
            video_name = video["name"].lower()
            # 移除副檔名進行比較
            video_base = os.path.splitext(video_name)[0]
            
            # 檢查是否有共同的關鍵字
            if any(part in video_base for part in clean_ref.split("_") if len(part) > 2):
                return video["path"]
        
        # 如果沒有找到匹配的，返回最新的影片
        return video_files[0]["path"]
    
    # ==========================================
    # JSON 檔案管理
    # ==========================================
    
    def save_json(self, data: Any, file_path: Path, backup: bool = True) -> bool:
        """
        儲存 JSON 檔案
        
        Args:
            data: 要儲存的資料
            file_path: 檔案路徑
            backup: 是否建立備份
            
        Returns:
            是否成功儲存
        """
        try:
            # 如果檔案已存在且需要備份
            if backup and file_path.exists():
                backup_path = file_path.with_suffix(f".backup_{int(datetime.now().timestamp())}.json")
                file_path.rename(backup_path)
            
            # 儲存新檔案
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            return True
            
        except Exception as e:
            print(f"❌ 儲存 JSON 失敗: {e}")
            return False
    
    def load_json(self, file_path: Path) -> Optional[Any]:
        """載入 JSON 檔案"""
        try:
            if not file_path.exists():
                return None
                
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
                
        except Exception as e:
            print(f"❌ 載入 JSON 失敗: {e}")
            return None
    
    def get_chunk_json_files(self, project_name: Optional[str] = None, 
                           file_type: str = "flagged") -> List[str]:
        """
        取得 chunk JSON 檔案清單
        
        Args:
            project_name: 專案名稱
            file_type: 檔案類型 ("flagged", "corrected", "all")
            
        Returns:
            檔案名稱清單
        """
        chunks_dir = self.get_temp_chunks_dir(project_name)
        
        if not chunks_dir.exists():
            return []
        
        files = []
        for file_path in chunks_dir.glob("*.json"):
            filename = file_path.name
            
            if file_type == "flagged" and "_flagged_for_human.json" in filename:
                if "_corrected" not in filename:  # 排除已修正的版本
                    files.append(filename)
            elif file_type == "corrected" and "_corrected.json" in filename:
                files.append(filename)
            elif file_type == "all":
                files.append(filename)
        
        # 按 chunk ID 排序
        try:
            files.sort(key=lambda x: int(x.split('_')[1]))
        except:
            files.sort()
            
        return files
    
    # ==========================================
    # 專案管理
    # ==========================================
    
    def create_project(self, video_path: str, project_name: Optional[str] = None) -> str:
        """
        建立新專案
        
        Args:
            video_path: 影片檔案路徑
            project_name: 專案名稱，如果不提供則自動生成
            
        Returns:
            專案名稱
        """
        if project_name is None:
            # 從影片檔名生成專案名稱
            video_name = Path(video_path).stem
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            project_name = f"{video_name}_{timestamp}"
        
        project_dir = self.get_project_dir(project_name)
        
        # 建立專案設定檔
        project_config = {
            "project_name": project_name,
            "video_path": video_path,
            "created_at": datetime.now().isoformat(),
            "status": "created"
        }
        
        config_path = project_dir / "project.json"
        self.save_json(project_config, config_path, backup=False)
        
        return project_name
    
    def get_project_list(self) -> List[Dict[str, Any]]:
        """取得所有專案清單"""
        projects = []
        
        if not self.output_dir.exists():
            return projects
        
        for project_dir in self.output_dir.iterdir():
            if project_dir.is_dir():
                config_path = project_dir / "project.json"
                config = self.load_json(config_path)
                
                if config:
                    projects.append({
                        "name": project_dir.name,
                        "config": config,
                        "path": str(project_dir)
                    })
        
        # 按建立時間排序
        projects.sort(key=lambda x: x["config"].get("created_at", ""), reverse=True)
        return projects


# 建立全域實例
file_manager = FileManager()