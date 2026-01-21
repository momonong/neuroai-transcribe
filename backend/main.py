import os
import json
import glob
import shutil
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI()

# ==========================================
# 1. 設定 & 初始化 (路徑修正核心)
# ==========================================

# 取得當前檔案 (backend/main.py) 的絕對路徑
CURRENT_FILE = os.path.abspath(__file__)
# 取得 backend 資料夾路徑
BACKEND_DIR = os.path.dirname(CURRENT_FILE)
# 取得專案根目錄 (backend 的上一層)
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)

# 設定 DATA_DIR 為 專案根目錄下的 data
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

# 確保資料夾存在
os.makedirs(DATA_DIR, exist_ok=True)

print(f"🚀 Server started.")
print(f"📂 Project Root: {PROJECT_ROOT}")
print(f"📂 Data Directory: {DATA_DIR}")

# CORS 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 掛載靜態檔案 (前端播放影片用)
app.mount("/static", StaticFiles(directory=DATA_DIR), name="static")


# ==========================================
# 2. 資料結構 (Pydantic Models)
# ==========================================

class TranscriptSegment(BaseModel):
    sentence_id: float
    start: float
    end: float
    speaker: str
    text: str
    verification_score: float = 1.0
    status: str = "reviewed"
    needs_review: bool = False
    review_reason: Optional[str] = None

class SavePayload(BaseModel):
    filename: str  # 相對路徑 (CaseName/chunk_x.json)
    speaker_mapping: Dict[str, str]
    segments: List[TranscriptSegment]

# ==========================================
# 3. 輔助函式
# ==========================================

def get_real_path(relative_path: str):
    """將前端傳來的相對路徑轉換為系統絕對路徑"""
    if ".." in relative_path:
        raise ValueError("Invalid path: '..' is not allowed")
    return os.path.join(DATA_DIR, relative_path)

# ==========================================
# 4. API 實作
# ==========================================

@app.get("/api/videos")
def get_videos():
    """
    掃描所有影片，供前端下拉選單使用
    修正：掃描 data/CaseName/Video.mp4
    """
    video_files = []
    # 支援常見音視訊格式
    extensions = [".mp4", ".MP4"]
    
    if not os.path.exists(DATA_DIR):
        return video_files
    
    # 1. 掃描 data 資料夾底下的每一層 (Case資料夾)
    # 使用 os.scandir 效能較好
    with os.scandir(DATA_DIR) as it:
        for entry in it:
            if entry.is_dir() and entry.name not in ["temp_chunks", "db", "text", "__pycache__"]:
                case_name = entry.name
                case_path = entry.path
                
                # 2. 在該 Case 資料夾內找影片
                for f in os.listdir(case_path):
                    if any(f.endswith(ext) for ext in extensions):
                        # 排除掉 chunk_ 開頭的音檔，我們只列出主影片
                        if f.startswith("chunk_"):
                            continue
                            
                        # 組合相對路徑
                        rel_path = f"{case_name}/{f}"
                        display_name = f"{case_name}"
                        
                        video_files.append({
                            "path": rel_path,
                            "name": display_name
                        })

    # 依名稱排序
    video_files.sort(key=lambda x: x['name'], reverse=True)
    return video_files

@app.get("/api/cases")
def get_cases():
    """
    列出 data/ 底下的專案資料夾
    """
    cases = []
    if not os.path.exists(DATA_DIR):
        return cases
    
    # 忽略的系統資料夾
    IGNORE_DIRS = {"temp_chunks", "db", "text", "__pycache__", "output", "test-complete-pipeline"}

    with os.scandir(DATA_DIR) as it:
        for entry in it:
            if entry.is_dir() and entry.name not in IGNORE_DIRS:
                # 只要不是系統資料夾，我們就當作是案例資料夾回傳
                # 不做過度檢查，以免因為檔案格式問題導致資料夾消失
                cases.append(entry.name)
    
    cases.sort(reverse=True)
    return cases

@app.get("/api/temp/chunks")
def list_chunks(case: Optional[str] = None):
    """
    列出 JSON 檔案 (智慧篩選版)。
    邏輯：針對每個 Chunk ID，只回傳「最高優先級」的單一檔案。
    """
    json_files = []
    
    if case:
        search_path = os.path.join(DATA_DIR, case, "chunk_*.json")
    else:
        # 如果沒選 Case，通常不回傳，或回傳全部 (視需求)
        return {"files": []}
    
    # 1. 檔案分組：以 Chunk ID 為 Key
    # 結構: { 1: {'flagged': path, 'aligned': path}, 2: {...} }
    chunk_groups = {}
    
    for f in glob.glob(search_path):
        filename = os.path.basename(f)
        
        # 絕對排除的名單
        if "whisper" in filename or "diar" in filename:
            continue
            
        # 解析 Chunk ID
        # 檔名範例: chunk_3_1100278_1606067_flagged_for_human.json
        try:
            parts = filename.split('_')
            # parts[0]="chunk", parts[1]="3" (index)
            chunk_idx = int(parts[1])
        except:
            continue # 檔名格式不對就跳過
            
        if chunk_idx not in chunk_groups:
            chunk_groups[chunk_idx] = {}
            
        # 依據後綴分類
        if "flagged_for_human" in filename:
            chunk_groups[chunk_idx]["flagged"] = f
        elif "edited" in filename:
            chunk_groups[chunk_idx]["edited"] = f
        elif "verified_dataset" in filename:
            chunk_groups[chunk_idx]["verified"] = f
        elif "aligned" in filename:
            chunk_groups[chunk_idx]["aligned"] = f
            
    # 2. 挑選每個 Chunk 的最佳檔案 (Winner Takes All)
    # 我們將 keys 排序 (1, 2, 3, 4...) 確保列表順序
    sorted_indices = sorted(chunk_groups.keys())
    
    for idx in sorted_indices:
        variants = chunk_groups[idx]
        best_file = None
        
        # 優先順序判定
        if "flagged" in variants:
            best_file = variants["flagged"]
        elif "edited" in variants:
            best_file = variants["edited"]
        elif "verified" in variants:
            best_file = variants["verified"]
        elif "aligned" in variants:
            best_file = variants["aligned"]
            
        if best_file:
            # 轉相對路徑回傳
            rel_path = os.path.relpath(best_file, DATA_DIR)
            json_files.append(rel_path.replace("\\", "/"))
            
    return {"files": json_files}

@app.get("/api/temp/chunks")
def list_chunks(case: Optional[str] = None):
    """
    列出 JSON 檔案。
    邏輯：針對每個 Chunk ID (例如 chunk_1)，只回傳「最高優先級」的檔案。
    優先級: flagged > edited > aligned (whisper/diar 隱藏)
    """
    json_files = []
    
    if case:
        search_path = os.path.join(DATA_DIR, case, "chunk_*.json")
    else:
        search_path = os.path.join(DATA_DIR, "*", "chunk_*.json")
    
    # 1. 收集所有 chunk 檔案，並分組
    # 結構: { "chunk_1": { "flagged": path, "aligned": path ... } }
    chunk_groups = {}
    
    for f in glob.glob(search_path):
        filename = os.path.basename(f)
        
        # 排除非目標檔案
        if "whisper" in filename or "diar" in filename:
            continue
            
        # 解析 Chunk ID (假設檔名: chunk_1_0_531989_...)
        parts = filename.split('_')
        if len(parts) < 2: continue
        
        # 組合出唯一的 Key: CaseName/chunk_1
        case_name = os.path.basename(os.path.dirname(f))
        chunk_id = f"{parts[0]}_{parts[1]}" # chunk_1
        unique_key = f"{case_name}/{chunk_id}"
        
        if unique_key not in chunk_groups:
            chunk_groups[unique_key] = {}
            
        # 分類
        if "flagged_for_human" in filename:
            chunk_groups[unique_key]["flagged"] = f
        elif "edited" in filename:
            chunk_groups[unique_key]["edited"] = f
        elif "aligned" in filename:
            chunk_groups[unique_key]["aligned"] = f
            
    # 2. 挑選最佳檔案
    for key, variants in chunk_groups.items():
        best_file = None
        # 優先順序: Flagged > Edited > Aligned
        if "flagged" in variants:
            best_file = variants["flagged"]
        elif "edited" in variants:
            best_file = variants["edited"]
        elif "aligned" in variants:
            best_file = variants["aligned"]
            
        if best_file:
            rel_path = os.path.relpath(best_file, DATA_DIR)
            json_files.append(rel_path.replace("\\", "/"))
            
    # 3. 排序 (確保 chunk_1, chunk_2 順序正確)
    # 我們需要自訂排序鍵，因為字串排序 "chunk_10" 會排在 "chunk_2" 前面
    def sort_key(path):
        try:
            # path: Case/chunk_1_...
            filename = os.path.basename(path)
            parts = filename.split('_')
            return int(parts[1]) # 取 chunk 的編號來排序
        except:
            return path

    json_files.sort(key=sort_key)
    return {"files": json_files}

@app.get("/api/temp/chunk/{filename:path}")
def get_chunk(filename: str):
    """
    讀取專案資料 (Version Control Logic)
    修正：優先鎖定主影片 (MP4)，保持前端播放器不跳動。
    """
    try:
        base_path = get_real_path(filename)
        
        # 1. 決定要讀哪個檔案 (Version Control)
        flagged_path = base_path.replace(".json", "_flagged_for_human.json")
        edited_path = base_path.replace(".json", "_edited.json")
        
        target_path = base_path # 預設讀原始檔
        
        if os.path.exists(flagged_path):
            target_path = flagged_path
            print(f"📖 Loading flagged: {os.path.basename(flagged_path)}")
        elif os.path.exists(edited_path):
            target_path = edited_path
            print(f"📖 Loading edited: {os.path.basename(edited_path)}")
        else:
            print(f"📖 Loading original: {os.path.basename(base_path)}")
        
        if not os.path.exists(target_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # ========================================================
        # 2. 媒體配對邏輯 (Media Discovery) - 關鍵修正處
        # ========================================================
        # 目標：不管選哪個 chunk，都優先回傳該資料夾的主影片 (.mp4)
        # 這樣前端播放器才不會因為切換 chunk 而重整
        
        folder_path = os.path.dirname(filename)      # 相對路徑 (CaseName)
        real_folder = os.path.dirname(target_path)   # 絕對路徑
        
        target_media = None
        
        # 策略 A: 先找該資料夾內的 MP4 (主影片)
        if os.path.exists(real_folder):
            # 取得該資料夾內所有檔案
            files = os.listdir(real_folder)
            # 優先找 .mp4 或 .MP4
            mp4_files = [f for f in files if f.lower().endswith('.mp4')]
            
            if mp4_files:
                # 簡單邏輯：通常最大的那個就是主影片，或者直接取第一個
                # 這裡我們取檔案名稱最短的，通常主影片檔名比較乾淨，或者取第一個
                mp4_files.sort(key=len) 
                target_media = mp4_files[0]
        
        # 策略 B: 如果真的沒有 MP4，才退而求其次去找對應的 chunk 音檔 (.wav)
        if not target_media:
            json_fname = os.path.basename(target_path)
            core_name = json_fname.replace("_flagged_for_human.json", "")\
                                  .replace("_edited.json", "")\
                                  .replace(".json", "")
            
            # 移除後綴以還原 chunk 名稱
            for suffix in ["_whisper", "_aligned", "_diar"]:
                if core_name.endswith(suffix):
                    core_name = core_name.replace(suffix, "")

            # 找同名的 wav
            for ext in [".wav", ".mp3", ".m4a"]:
                candidate = f"{core_name}{ext}"
                if os.path.exists(os.path.join(real_folder, candidate)):
                    target_media = candidate
                    break
        
        # 3. 處理回傳資料
        processed_data = data if isinstance(data, dict) else {
            "segments": data, 
            "speaker_mapping": {}, 
            "file_type": "original"
        }
        
        # 只有在找到媒體檔時才更新 media_file
        if target_media:
            # 組合相對路徑: CaseName/Video.mp4
            media_rel_path = f"{folder_path}/{target_media}"
            processed_data['media_file'] = media_rel_path.replace("\\", "/")
            
        # 標記檔案類型
        if "_flagged_for_human" in target_path:
            processed_data['file_type'] = 'flagged'
        elif "_edited" in target_path:
            processed_data['file_type'] = 'edited'
        else:
            processed_data['file_type'] = 'original'
            
        return processed_data

    except Exception as e:
        print(f"❌ Error loading chunk: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/temp/save")
def save_chunk(payload: SavePayload):
    """
    存檔 API (強制存為 _edited.json)
    """
    try:
        original_path = get_real_path(payload.filename)
        
        # 移除可能存在的 _flagged 或 _edited 後綴，確保檔名乾淨
        clean_path = original_path.replace("_flagged_for_human.json", ".json")\
                                  .replace("_edited.json", ".json")
        
        # 產生儲存路徑
        save_path = clean_path.replace(".json", "_edited.json")
        
        data_to_save = {
            "last_modified": datetime.now().isoformat(),
            "speaker_mapping": payload.speaker_mapping,
            "segments": [s.dict() for s in payload.segments],
        }
        
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
            
        print(f"💾 Saved: {os.path.basename(save_path)}")
        return {"status": "success", "saved_to": save_path}
    
    except Exception as e:
        print(f"❌ Save error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...), case_name: str = Form(...)):
    """
    上傳新影片並建立案例資料夾
    """
    try:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M")
        base_name = os.path.splitext(file.filename)[0]
        safe_base_name = base_name.replace(" ", "-")
        
        if not case_name.strip():
            case_name = f"{timestamp}-{safe_base_name}"
        
        # 儲存到 data/CaseName/
        save_dir = os.path.join(DATA_DIR, case_name)
        os.makedirs(save_dir, exist_ok=True)
        
        file_path = os.path.join(save_dir, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        print(f"✅ Uploaded to: {save_dir}")
        return {"message": "Success", "path": file_path}
    
    except Exception as e:
        print(f"❌ Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # 確保 reload=True 在開發時很好用，會自動偵測程式碼變更重啟
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)