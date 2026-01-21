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
    列出 JSON 檔案 (智慧篩選版)。
    邏輯：針對每個 Chunk ID，只回傳「最高優先級」的單一檔案。
    修正後優先級: edited > flagged > verified > aligned
    """
    json_files = []
    
    if case:
        search_path = os.path.join(DATA_DIR, case, "chunk_*.json")
    else:
        search_path = os.path.join(DATA_DIR, "*", "chunk_*.json")
    
    # 1. 收集所有 chunk 檔案，並分組
    chunk_groups = {}
    
    for f in glob.glob(search_path):
        filename = os.path.basename(f)
        
        # 排除非目標檔案
        if "whisper" in filename or "diar" in filename:
            continue
            
        # 解析 Chunk ID
        parts = filename.split('_')
        if len(parts) < 2: continue
        
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
        elif "verified_dataset" in filename:
            chunk_groups[unique_key]["verified"] = f
        elif "aligned" in filename:
            chunk_groups[unique_key]["aligned"] = f
            
    # 2. 挑選最佳檔案 (Winner Takes All)
    for key, variants in chunk_groups.items():
        best_file = None
        
        # 🔥 修正重點：優先順序調整 🔥
        # 只要有 "已編輯 (edited)" 版本，代表人工已經處理過，絕對優先顯示！
        if "edited" in variants:
            best_file = variants["edited"]      # 🥇 第一順位: 已編輯
        elif "flagged" in variants:
            best_file = variants["flagged"]     # 🥈 第二順位: 需審核
        elif "verified" in variants:
            best_file = variants["verified"]    # 🥉 第三順位: 已驗證資料集
        elif "aligned" in variants:
            best_file = variants["aligned"]     # 🏅 第四順位: 原始檔
            
        if best_file:
            rel_path = os.path.relpath(best_file, DATA_DIR)
            json_files.append(rel_path.replace("\\", "/"))
            
    # 3. 排序 (確保 chunk_1, chunk_2 順序正確)
    def sort_key(path):
        try:
            filename = os.path.basename(path)
            parts = filename.split('_')
            return int(parts[1]) 
        except:
            return path

    json_files.sort(key=sort_key)
    return {"files": json_files}

@app.get("/api/temp/chunk/{filename:path}")
def get_chunk(filename: str):
    """
    讀取專案資料 (智慧優先級版)。
    邏輯：不管傳入什麼檔名，一律優先尋找並回傳 '已編輯 (_edited)' 版本。
    優先級: Edited > Flagged > Verified > Aligned
    """
    try:
        # 1. 取得絕對路徑
        request_path = get_real_path(filename)
        directory = os.path.dirname(request_path)
        request_fname = os.path.basename(request_path)
        
        # 2. 還原「核心檔名」 (移除所有可能的後綴)
        # 例如: chunk_1_0_531989_flagged_for_human.json -> chunk_1_0_531989
        core_name = request_fname.replace("_flagged_for_human.json", "")\
                                 .replace("_edited.json", "")\
                                 .replace("_verified_dataset.json", "")\
                                 .replace("_aligned.json", "")\
                                 .replace(".json", "")
        
        # 移除可能殘留的後綴 (針對 whisper/diar 這種非標準結尾)
        for suffix in ["_whisper", "_aligned", "_diar"]:
            if core_name.endswith(suffix):
                core_name = core_name.replace(suffix, "")

        # 3. 定義各版本的候選路徑
        candidate_edited = os.path.join(directory, f"{core_name}_edited.json")
        candidate_flagged = os.path.join(directory, f"{core_name}_flagged_for_human.json")
        candidate_verified = os.path.join(directory, f"{core_name}_verified_dataset.json")
        candidate_aligned = os.path.join(directory, f"{core_name}_aligned.json")
        
        # 4. 依照優先權決定最終要讀取哪個檔案 (Winner Takes All)
        target_path = None
        
        if os.path.exists(candidate_edited):
            target_path = candidate_edited
            print(f"📖 Priority Load: Edited ({os.path.basename(target_path)})")
        elif os.path.exists(candidate_flagged):
            target_path = candidate_flagged
            print(f"📖 Priority Load: Flagged ({os.path.basename(target_path)})")
        elif os.path.exists(candidate_verified):
            target_path = candidate_verified
        elif os.path.exists(candidate_aligned):
            target_path = candidate_aligned
        else:
            # 如果都找不到，就嘗試讀取原本請求的檔案 (Fallback)
            target_path = request_path
            print(f"📖 Fallback Load: {os.path.basename(target_path)}")

        if not os.path.exists(target_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        # 5. 讀取檔案內容
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # ========================================================
        # 6. 媒體配對邏輯 (Media Discovery) - 維持不變 (找 MP4 優先)
        # ========================================================
        folder_path = os.path.dirname(filename)      # 相對路徑
        real_folder = os.path.dirname(target_path)   # 絕對路徑
        target_media = None
        
        # 策略 A: 找主影片 (.mp4)
        if os.path.exists(real_folder):
            files = os.listdir(real_folder)
            mp4_files = [f for f in files if f.lower().endswith('.mp4')]
            if mp4_files:
                mp4_files.sort(key=len) 
                target_media = mp4_files[0]
        
        # 策略 B: 找對應音檔 (.wav)
        if not target_media:
            # 嘗試找 chunk wav
            for ext in [".wav", ".mp3", ".m4a"]:
                candidate = f"{core_name}{ext}"
                if os.path.exists(os.path.join(real_folder, candidate)):
                    target_media = candidate
                    break
        
        # 7. 組裝回傳資料
        processed_data = data if isinstance(data, dict) else {
            "segments": data, 
            "speaker_mapping": {}, 
            "file_type": "original"
        }
        
        if target_media:
            media_rel_path = f"{folder_path}/{target_media}"
            processed_data['media_file'] = media_rel_path.replace("\\", "/")
            
        # 標記檔案類型 (給前端顯示 Chip 用)
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
    存檔 API。
    邏輯：不管來源是 aligned, flagged 還是 edited，
    存檔時一律轉存為 '_edited.json'，確保數據不丟失且有跡可循。
    """
    try:
        # 1. 解析原始路徑
        full_path = get_real_path(payload.filename)
        directory = os.path.dirname(full_path)
        filename = os.path.basename(full_path)
        
        # 2. 建構目標檔名 (強制結尾為 _edited.json)
        # 先移除所有可能的後綴，還原到核心 ID
        core_name = filename.replace("_flagged_for_human.json", "")\
                            .replace("_edited.json", "")\
                            .replace("_aligned.json", "")\
                            .replace("_verified_dataset.json", "")\
                            .replace(".json", "")
        
        # 加上 _edited 後綴
        new_filename = f"{core_name}_edited.json"
        save_path = os.path.join(directory, new_filename)
        
        # 3. 準備資料
        data_to_save = {
            "last_modified": datetime.now().isoformat(),
            "speaker_mapping": payload.speaker_mapping,
            "segments": [s.dict() for s in payload.segments],
        }
        
        # 4. 寫入檔案
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
            
        print(f"💾 Saved to: {new_filename}")
        
        # 5. 回傳新的相對路徑 (重要！讓前端可以更新狀態)
        # 計算相對路徑: CaseName/chunk_x_edited.json
        relative_path = os.path.relpath(save_path, DATA_DIR).replace("\\", "/")
        
        return {
            "status": "success", 
            "saved_to": relative_path,
            "filename": new_filename
        }
    
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