import os
import shutil
import json
import glob
from datetime import datetime
from typing import List, Optional, Dict

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# 引入檔案管理器
from core.file_manager import file_manager

app = FastAPI()

# ==========================================
# 1. 設定 & 初始化
# ==========================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], # 允許前端的網址
    allow_credentials=True,
    allow_methods=["*"], # 允許所有方法 (GET, POST...)
    allow_headers=["*"], # 允許所有 Header
)

# 使用檔案管理器的路徑
DATA_DIR = str(file_manager.data_dir)
ASD_DIR = str(file_manager.asd_dir)
TEMP_CHUNKS_DIR = str(file_manager.temp_chunks_dir)

# 掛載靜態檔案
app.mount("/static", StaticFiles(directory=DATA_DIR), name="static")

print(f"🚀 Server started.")
print(f"📂 Data Root: {DATA_DIR}")
print(f"🎥 Static Mount: /static -> {DATA_DIR}")

# ==========================================
# 2. 資料結構
# ==========================================

class TranscriptSegment(BaseModel):
    start: float
    end: float
    speaker: str
    text: str
    verification_score: float = 0.0
    status: str = "ok"
    sentence_id: int
    needs_review: bool = False
    review_reason: Optional[str] = None

class SaveRequest(BaseModel):
    filename: str
    speaker_mapping: Dict[str, str] = {}
    segments: List[dict]

# ==========================================
# 3. 核心邏輯
# ==========================================

# main.py 修改 find_video_file 函式

# main.py

def find_video_file(base_filename: str):
    """
    使用檔案管理器智慧搜尋影片檔案
    """
    print(f"🔍 [Video Search] Looking for video matching: {base_filename}")
    
    # 使用檔案管理器的智慧匹配功能
    video_path = file_manager.find_best_video_match(base_filename)
    
    if video_path:
        print(f"✅ [Video Found] Path: {video_path}")
        return video_path
    
    print("❌ [Video Search] No matching video found.")
    return None

# ==========================================
# 4. API 實作
# ==========================================

@app.get("/api/temp/chunks")
def get_temp_chunks():
    """取得所有待校對 Chunk (不包含已修正的 _corrected)"""
    files = file_manager.get_chunk_json_files(file_type="flagged")
    return {"files": files}

@app.get("/api/temp/chunk/{filename}")
def get_chunk_data(filename: str):
    file_path = file_manager.temp_chunks_dir / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="JSON not found")
    
    try:
        data = file_manager.load_json(file_path)
        if data is None:
            raise HTTPException(status_code=500, detail="Failed to load JSON")

        # 1. 計算 Offset (時間偏移)
        parts = filename.split('_')
        offset_seconds = 0.0
        try:
            start_ms = int(parts[2]) # 假設檔名格式 chunk_ID_START_END...
            offset_seconds = start_ms / 1000.0
        except:
            pass

        # 2. 尋找影片 (使用新的搜尋邏輯)
        media_file_relative_path = find_video_file(filename)

        # 3. 回傳
        return {
            "media_file": media_file_relative_path, # 前端會接在 /static/ 後面
            "video_offset": offset_seconds,
            "segments": data if isinstance(data, list) else data.get("segments", []),
            "speaker_mapping": data.get("speaker_mapping", {}) if isinstance(data, dict) else {}
        }

    except Exception as e:
        print(f"❌ Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/temp/save")
def save_chunk_data(req: SaveRequest):
    """
    使用檔案管理器儲存修正後的資料
    """
    
    # 產生新檔名
    original_name = req.filename
    if "_flagged_for_human" in original_name:
        new_filename = original_name.replace("_flagged_for_human.json", "_corrected.json")
    else:
        # 如果已經是其他名字，就加上 _corrected (避免重複加可以用檢查)
        if "_corrected" not in original_name:
            new_filename = original_name.replace(".json", "_corrected.json")
        else:
            new_filename = original_name # 已經是修正版，就覆蓋修正版

    save_path = file_manager.temp_chunks_dir / new_filename
    
    save_content = {
        "original_source": original_name,
        "updated_at": datetime.now().isoformat(),
        "speaker_mapping": req.speaker_mapping,
        "segments": req.segments
    }
    
    success = file_manager.save_json(save_content, save_path, backup=False)
    
    if success:
        print(f"💾 Saved to new file: {new_filename}")
        return {
            "status": "success", 
            "message": f"已另存為新檔案: {new_filename}",
            "new_filename": new_filename
        }
    else:
        raise HTTPException(status_code=500, detail="Save failed")

@app.get("/api/videos")
def get_all_videos():
    """
    使用檔案管理器列出所有影片檔案
    """
    video_list = file_manager.find_video_files()
    return video_list

@app.get("/api/projects")
def get_projects():
    """取得所有專案清單"""
    projects = file_manager.get_project_list()
    return {"projects": projects}

@app.post("/api/projects/create")
def create_project(video_path: str, project_name: Optional[str] = None):
    """建立新專案"""
    try:
        # 檢查影片檔案是否存在
        full_video_path = file_manager.data_dir / video_path
        if not full_video_path.exists():
            raise HTTPException(status_code=404, detail="Video file not found")
        
        project_name = file_manager.create_project(str(full_video_path), project_name)
        
        return {
            "status": "success",
            "project_name": project_name,
            "message": f"專案 {project_name} 建立成功"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)