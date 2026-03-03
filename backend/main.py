import os
import sys
import io
import json
import glob
import shutil
import urllib.parse
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path

# 從 backend/ 執行時，將專案根加入 path，才能 import core（core 在專案根 core/）
_backend_dir = Path(__file__).resolve().parent
_project_root = _backend_dir.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.file_manager import file_manager

# 不在此 import run_pipeline，改由子流程執行，避免 main 載入 torch/whisper 等 AI 依賴

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


def _run_pipeline_in_subprocess(video_path: str, case_name: str) -> None:
    """在子流程執行 core pipeline，避免 main 載入 torch/whisper。供 background_tasks 呼叫。"""
    import subprocess
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    subprocess.run(
        [sys.executable, "-m", "core.run_pipeline", video_path, "--case", case_name],
        cwd=str(PROJECT_ROOT),
        env=env,
    )

# CORS 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 掛載靜態檔案 (前端播放影片用)
# http://localhost:8001/static/CaseName/video.mp4
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
    suggested_correction: Optional[str] = None # 確保後端接收前端傳回的資料結構完整

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
    修正：同時支援 data/CaseName/Video.mp4 (舊) 與 data/CaseName/source/Video.mp4 (新)
    """
    video_files = []
    # 支援常見音視訊格式
    extensions = [".mp4", ".MP4", ".mov", ".MOV", ".avi", ".AVI"]
    
    if not os.path.exists(DATA_DIR):
        return video_files
    
    # 排除的系統資料夾
    IGNORE_DIRS = {"temp_chunks", "db", "text", "__pycache__", "output"}

    # 1. 掃描 data 資料夾底下的每一層 (Case資料夾)
    with os.scandir(DATA_DIR) as it:
        for entry in it:
            if entry.is_dir() and entry.name not in IGNORE_DIRS:
                case_name = entry.name
                case_path = entry.path
                
                # === 核心修改：定義搜尋路徑 (優先找 source，也找根目錄) ===
                search_targets = []
                
                # 1. 新架構: data/Case/source
                source_dir = os.path.join(case_path, "source")
                if os.path.exists(source_dir):
                    search_targets.append(source_dir)
                
                # 2. 舊架構: data/Case
                search_targets.append(case_path)

                # 用來避免重複 (如果同一個檔案被掃到兩次)
                seen_files = set()

                for target_dir in search_targets:
                    if not os.path.exists(target_dir): continue

                    for f in os.listdir(target_dir):
                        if any(f.endswith(ext) for ext in extensions):
                            # 排除掉 chunk_ 開頭的音檔
                            if f.startswith("chunk_"):
                                continue
                            
                            if f in seen_files:
                                continue
                            seen_files.add(f)
                            
                            # 取得絕對路徑
                            full_path = os.path.join(target_dir, f)
                            
                            # 計算相對路徑 (給前端 /static/ 使用)
                            # 如果在 source 裡，rel_path 會變成 "CaseName/source/video.mp4"
                            # 如果在根目錄，rel_path 會變成 "CaseName/video.mp4"
                            rel_path = os.path.relpath(full_path, DATA_DIR).replace("\\", "/")
                            
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
                cases.append(entry.name)
    
    cases.sort(reverse=True)
    return cases

@app.get("/api/temp/chunks")
def list_chunks(case: Optional[str] = None):
    """
    列出 JSON 檔案 (智慧篩選版)。
    邏輯：針對每個 Chunk ID，只回傳「最高優先級」的單一檔案。
    修正後優先級: edited > flagged > verified > aligned
    """
    json_files = []
    
    if case:
        search_path = os.path.join(DATA_DIR, case, "**", "chunk_*.json") # 使用 recursive glob 比較保險，但目前結構應該只有一層
        # 修正：目前的 intermediate 都在 data/Case/intermediate，所以我們要找那裡
        # 或是之前的邏輯是 data/Case/chunk_*.json (舊結構)
        # 讓我們同時支援兩者
        
        # 策略：先掃 data/Case/intermediate (新結構)
        inter_path = os.path.join(DATA_DIR, case, "intermediate", "chunk_*.json")
        files_inter = glob.glob(inter_path)
        
        # 再掃 data/Case (舊結構，如果有)
        root_path = os.path.join(DATA_DIR, case, "chunk_*.json")
        files_root = glob.glob(root_path)
        
        all_files = files_inter + files_root
    else:
        # 搜尋全部 (開發用)
        all_files = glob.glob(os.path.join(DATA_DIR, "*", "intermediate", "chunk_*.json")) + \
                    glob.glob(os.path.join(DATA_DIR, "*", "chunk_*.json"))
    
    # 1. 收集所有 chunk 檔案，並分組
    chunk_groups = {}
    
    for f in all_files:
        filename = os.path.basename(f)
        
        # 排除非目標檔案
        if "whisper" in filename or "diar" in filename:
            continue
            
        # 解析 Chunk ID
        parts = filename.split('_')
        if len(parts) < 2: continue
        
        # 取得 Case Name (稍微複雜因為有 intermediate 層)
        # f = .../data/CaseName/intermediate/chunk... -> dirname -> dirname -> basename
        # f = .../data/CaseName/chunk... -> dirname -> basename
        parent_dir = os.path.dirname(f)
        if os.path.basename(parent_dir) == "intermediate":
             case_name = os.path.basename(os.path.dirname(parent_dir))
        else:
             case_name = os.path.basename(parent_dir)

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
        elif "stitched" in filename: # 新增：支援我們剛剛做出來的 stitched 檔案
            chunk_groups[unique_key]["stitched"] = f
        elif "aligned" in filename:
            chunk_groups[unique_key]["aligned"] = f
            
    # 2. 挑選最佳檔案 (Winner Takes All)
    for key, variants in chunk_groups.items():
        best_file = None
        
        # 🔥 優先順序調整 🔥
        if "edited" in variants:
            best_file = variants["edited"]      # 🥇 1. 已編輯
        elif "flagged" in variants:
            best_file = variants["flagged"]     # 🥈 2. 需審核 (AI 標記)
        elif "stitched" in variants:
             best_file = variants["stitched"]   # 🥉 3. 已修復 (AI Stitching 結果) <--- 新增
        elif "verified" in variants:
            best_file = variants["verified"]    # 4. 舊版驗證
        elif "aligned" in variants:
            best_file = variants["aligned"]     # 5. 原始檔
            
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
            return 0

    json_files.sort(key=sort_key)
    return {"files": json_files}

@app.get("/api/temp/chunk/{filename:path}")
def get_chunk(filename: str):
    """
    讀取專案資料 (智慧優先級版)。
    """
    try:
        # 1. 取得絕對路徑
        request_path = get_real_path(filename)
        directory = os.path.dirname(request_path)
        request_fname = os.path.basename(request_path)
        
        # 2. 還原「核心檔名」 (移除所有可能的後綴)
        core_name = request_fname.replace("_flagged_for_human.json", "")\
                                 .replace("_edited.json", "")\
                                 .replace("_verified_dataset.json", "")\
                                 .replace("_stitched.json", "")\
                                 .replace("_aligned.json", "")\
                                 .replace(".json", "")
        
        # 移除可能殘留的後綴
        for suffix in ["_whisper", "_aligned", "_diar"]:
            if core_name.endswith(suffix):
                core_name = core_name.replace(suffix, "")

        # 3. 定義各版本的候選路徑
        candidate_edited = os.path.join(directory, f"{core_name}_edited.json")
        candidate_flagged = os.path.join(directory, f"{core_name}_flagged_for_human.json")
        candidate_stitched = os.path.join(directory, f"{core_name}_stitched.json") # 新增
        candidate_verified = os.path.join(directory, f"{core_name}_verified_dataset.json")
        candidate_aligned = os.path.join(directory, f"{core_name}_aligned.json")
        
        # 4. 依照優先權決定最終要讀取哪個檔案
        target_path = None
        
        if os.path.exists(candidate_edited):
            target_path = candidate_edited
            print(f"📖 Priority Load: Edited ({os.path.basename(target_path)})")
        elif os.path.exists(candidate_flagged):
            target_path = candidate_flagged
            print(f"📖 Priority Load: Flagged ({os.path.basename(target_path)})")
        elif os.path.exists(candidate_stitched):
            target_path = candidate_stitched
            print(f"📖 Priority Load: Stitched ({os.path.basename(target_path)})")
        elif os.path.exists(candidate_verified):
            target_path = candidate_verified
        elif os.path.exists(candidate_aligned):
            target_path = candidate_aligned
        else:
            target_path = request_path
            print(f"📖 Fallback Load: {os.path.basename(target_path)}")

        if not os.path.exists(target_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        # 5. 讀取檔案內容
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # ========================================================
        # 6. 媒體配對邏輯 (Media Discovery) - 改良版
        # ========================================================
        # directory 指向的是 intermediate，我們需要往上找 source 或根目錄
        # 結構 A: data/Case/intermediate/chunk.json -> 影片在 data/Case/source/
        # 結構 B: data/Case/chunk.json -> 影片在 data/Case/
        
        case_root = os.path.dirname(directory) # 假設 directory 是 intermediate，上一層是 Case
        if os.path.basename(directory) != "intermediate":
             case_root = directory # 如果 json 本來就在根目錄
             
        # 搜尋候選影片目錄
        media_search_dirs = [
            os.path.join(case_root, "source"), # 優先找 source
            case_root # 次要找根目錄
        ]
        
        target_media = None
        media_folder_found = None
        
        for search_dir in media_search_dirs:
            if not os.path.exists(search_dir): continue
            
            files = os.listdir(search_dir)
            mp4_files = [f for f in files if f.lower().endswith(('.mp4', '.mov', '.avi'))]
            
            if mp4_files:
                mp4_files.sort(key=len) 
                target_media = mp4_files[0]
                media_folder_found = search_dir
                break # 找到就跳出
        
        # 7. 組裝回傳資料
        processed_data = data if isinstance(data, dict) else {
            "segments": data, 
            "speaker_mapping": {}, 
            "file_type": "original"
        }
        
        if target_media and media_folder_found:
            # 計算相對於 DATA_DIR 的路徑給前端
            # 例如: Case/source/video.mp4
            full_media_path = os.path.join(media_folder_found, target_media)
            media_rel_path = os.path.relpath(full_media_path, DATA_DIR).replace("\\", "/")
            processed_data['media_file'] = media_rel_path
            
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
    """
    try:
        # 1. 解析原始路徑
        full_path = get_real_path(payload.filename)
        directory = os.path.dirname(full_path)
        filename = os.path.basename(full_path)
        
        # 2. 建構目標檔名 (強制結尾為 _edited.json)
        core_name = filename.replace("_flagged_for_human.json", "")\
                            .replace("_edited.json", "")\
                            .replace("_aligned.json", "")\
                            .replace("_stitched.json", "")\
                            .replace("_verified_dataset.json", "")\
                            .replace(".json", "")
        
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
        
        # 5. 回傳新的相對路徑
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
async def upload_video_endpoint(
    background_tasks: BackgroundTasks,  # ★ 注入 BackgroundTasks
    file: UploadFile = File(...), 
    case_name: str = Form(...)
):
    try:
        # 1. 儲存原始檔案
        file_ext = os.path.splitext(file.filename)[1]
        safe_filename = f"{case_name}{file_ext}"
        save_path = os.path.join(DATA_DIR, case_name, "source", safe_filename)
        
        # 確保目錄存在
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 2. 在背景用子流程執行 pipeline，main 不載入 core.run_pipeline（不帶入 torch/whisper）
        background_tasks.add_task(_run_pipeline_in_subprocess, save_path, case_name)
        
        return {"status": "processing_started", "case_name": case_name, "message": "Pipeline started in background"}

    except Exception as e:
        print(f"Upload Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/status/{case_name}")
async def get_status(case_name: str):
    """前端透過輪詢 (Polling) 這個 API 來獲取進度"""
    status = file_manager.get_status(case_name)
    return status

@app.get("/api/export/{case_name}/{dataset_type}")
async def export_dataset(case_name: str, dataset_type: str):
    """
    匯出合併後的資料集
    """
    # 對應你的檔案後綴
    suffix_map = {
        "whisper": "_whisper.json", # Raw ASR (相對時間，僅供參考)
        "diar": "_diar.json",       # Raw Diarization
        "aligned": "_aligned.json", # 初步對齊
        "stitched": "_stitched.json", # 斷句修復後
        "flagged": "_flagged_for_human.json", # LLM 標記後
        "edited": "_edited.json"    # 人工修正版 (黃金資料)
    }
    
    suffix = suffix_map.get(dataset_type)
    if not suffix:
        raise HTTPException(status_code=400, detail="Unknown dataset type")

    # 執行合併
    merged_data = file_manager.merge_chunks(case_name, suffix)
    
    if not merged_data:
        raise HTTPException(status_code=404, detail=f"No data found for {dataset_type}")

    # 轉成 JSON String
    json_str = json.dumps(merged_data, ensure_ascii=False, indent=2)
    
    # 下載檔名範例: 20250324_陈芮晞_FULL_edited.json
    filename = f"{case_name}_FULL_{dataset_type}.json"
    encoded_filename = urllib.parse.quote(filename)
    
    return StreamingResponse(
        io.BytesIO(json_str.encode("utf-8")),
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)