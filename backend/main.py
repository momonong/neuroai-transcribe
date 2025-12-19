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

app = FastAPI()

# ==========================================
# 1. 設定 & 初始化
# ==========================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")          # 指向 backend/data
ASD_DIR = os.path.join(DATA_DIR, "ASD")            # 指向 backend/data/ASD
TEMP_CHUNKS_DIR = os.path.join(DATA_DIR, "temp_chunks")

# 確保資料夾存在
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(ASD_DIR, exist_ok=True)
os.makedirs(TEMP_CHUNKS_DIR, exist_ok=True)

# ★★★ 修改 1: 掛載整個 data 資料夾 ★★★
# 這樣前端可以存取 /static/temp_chunks/xxx 也可以存取 /static/ASD/xxx
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
    暴力版：完全忽略 JSON 檔名，直接回傳 ASD 資料夾內的第一個 MP4。
    """
    print(f"🔍 [Video Search] Looking for ANY MP4 in {ASD_DIR}...")
    
    # 搜尋 ASD 資料夾下所有的 MP4 (包含子目錄)
    video_candidates = glob.glob(os.path.join(ASD_DIR, "**", "*.[mM][pP]4"), recursive=True)
    
    if video_candidates:
        # 直接拿第一個找到的影片
        found_video = video_candidates[0]
        
        # 計算相對於 data 資料夾的路徑
        # 例如: found_video = .../backend/data/ASD/2025.../video.mp4
        # DATA_DIR = .../backend/data
        # relative_path = ASD/2025.../video.mp4
        relative_path = os.path.relpath(found_video, DATA_DIR)
        
        # ★★★ 關鍵：Windows 反斜線 (\) 必須換成 URL 正斜線 (/) ★★★
        relative_path = relative_path.replace("\\", "/")
        
        print(f"✅ [Video Found] Path: {relative_path}")
        return relative_path

    print("❌ [Video Search] No MP4 found in ASD directory.")
    return None

# ==========================================
# 4. API 實作
# ==========================================

@app.get("/api/temp/chunks")
def get_temp_chunks():
    """取得所有待校對 Chunk (不包含已修正的 _corrected)"""
    if not os.path.exists(TEMP_CHUNKS_DIR):
        return {"files": []}
    
    # 只列出 _flagged_for_human.json，過濾掉 _corrected.json 以免列表重複
    files = [f for f in os.listdir(TEMP_CHUNKS_DIR) 
             if f.endswith("_flagged_for_human.json") and "_corrected" not in f]
    
    try:
        files.sort(key=lambda x: int(x.split('_')[1])) 
    except:
        files.sort()
    return {"files": files}

@app.get("/api/temp/chunk/{filename}")
def get_chunk_data(filename: str):
    file_path = os.path.join(TEMP_CHUNKS_DIR, filename)
    
    # 優先讀取 "_corrected" 版本 (如果有的話，讓使用者繼續編輯修正版)
    # 但為了比較模型效果，你可能想看原始版。
    # 這裡邏輯維持：讀取你點選的那個檔案。
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="JSON not found")
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

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
    ★★★ 修改 2: 另存新檔邏輯 ★★★
    原始: chunk_1_0_xxx_flagged_for_human.json
    存檔: chunk_1_0_xxx_corrected.json
    這樣原始檔案不會被動到。
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

    save_path = os.path.join(TEMP_CHUNKS_DIR, new_filename)
    
    save_content = {
        "original_source": original_name,
        "updated_at": datetime.now().isoformat(),
        "speaker_mapping": req.speaker_mapping,
        "segments": req.segments
    }
    
    try:
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(save_content, f, ensure_ascii=False, indent=2)
        
        print(f"💾 Saved to new file: {new_filename}")
        return {
            "status": "success", 
            "message": f"已另存為新檔案: {new_filename}",
            "new_filename": new_filename
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Save failed: {str(e)}")

@app.get("/api/videos")
def get_all_videos():
    """
    列出 ASD 資料夾下所有的 MP4 檔案，供前端選擇
    """
    video_list = []
    print(f"🔍 Scanning for videos in {ASD_DIR}...")
    
    # 遞迴搜尋所有 .mp4 / .mov
    candidates = glob.glob(os.path.join(ASD_DIR, "**", "*.[mM][pP]4"), recursive=True)
    candidates += glob.glob(os.path.join(ASD_DIR, "**", "*.[mM][oO][vV]"), recursive=True)
    
    for full_path in candidates:
        # 轉成相對路徑 (相對於 backend/data)
        # 例如: ASD/20250421-xxx/video.mp4
        try:
            rel_path = os.path.relpath(full_path, DATA_DIR)
            rel_path = rel_path.replace("\\", "/") # Windows 修正
            
            # 取得顯示名稱 (只有檔名，不含路徑，方便閱讀)
            display_name = os.path.basename(full_path)
            
            video_list.append({
                "path": rel_path,
                "name": display_name
            })
        except Exception as e:
            print(f"Error parsing path {full_path}: {e}")
            
    return video_list

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)