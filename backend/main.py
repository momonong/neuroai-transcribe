import os
import json
import glob
import shutil
from datetime import datetime
from typing import List, Dict, Optional, Any

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI()

# ==========================================
# 1. 設定 & 初始化
# ==========================================

# 確保資料夾存在
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# CORS 設定 (允許前端連線)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 開發階段允許所有，生產環境建議指定 http://localhost:5173
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 掛載靜態檔案 (讓前端可以透過 /static/路徑 播放影片)
app.mount("/static", StaticFiles(directory=DATA_DIR), name="static")

print(f"🚀 Server started.")
print(f"📂 Data Root: {os.path.abspath(DATA_DIR)}")

# ==========================================
# 2. 資料結構 (Pydantic Models)
# ==========================================

class TranscriptSegment(BaseModel):
    sentence_id: float  # 使用 float (timestamp) 或 int 都可以
    start: float
    end: float
    speaker: str
    text: str
    verification_score: float = 1.0
    status: str = "reviewed"
    needs_review: bool = False
    review_reason: Optional[str] = None

class SavePayload(BaseModel):
    filename: str  # 這裡傳的是相對路徑 (例如: "Morris/20260119_Test/transcript.json")
    speaker_mapping: Dict[str, str]
    segments: List[TranscriptSegment]

# ==========================================
# 3. 輔助函式
# ==========================================

def get_real_path(relative_path: str):
    """
    將前端傳來的相對路徑轉換為系統絕對路徑，並防止路徑遍歷攻擊
    """
    if ".." in relative_path:
        raise ValueError("Invalid path: '..' is not allowed")
    return os.path.join(DATA_DIR, relative_path)

# ==========================================
# 4. API 實作
# ==========================================

@app.get("/api/testers")
def get_testers():
    """
    取得所有測試者名單 (掃描第一層資料夾)
    """
    testers = set()
    if os.path.exists(DATA_DIR):
        for name in os.listdir(DATA_DIR):
            full_path = os.path.join(DATA_DIR, name)
            # 排除系統資料夾
            if os.path.isdir(full_path) and name not in ["db", "output", "temp_chunks", "text"]:
                testers.add(name)
    return sorted(list(testers))

@app.get("/api/videos")
def get_videos():
    """
    遞迴掃描所有影片，供前端下拉選單使用
    格式: [Tester] ProjectName - VideoName.mp4
    """
    video_files = []
    # 支援常見音視訊格式
    extensions = ["**/*.mp4", "**/*.mp3", "**/*.wav", "**/*.m4a"]
    
    for ext in extensions:
        # recursive=True 讓它能掃描子資料夾
        for f in glob.glob(os.path.join(DATA_DIR, ext), recursive=True):
            # 取得相對路徑: "Morris/20260119_Proj/video.mp4"
            rel_path = os.path.relpath(f, DATA_DIR)
            
            # 解析路徑以建立友善的顯示名稱
            parts = rel_path.split(os.sep)
            if len(parts) >= 2:
                tester = parts[0]
                project = parts[1] # "Timestamp_VideoName"
                filename = parts[-1]
                display_name = f"[{tester}] {project} - {filename}"
            else:
                display_name = rel_path

            # 統一使用 forward slash (/) 避免 Windows 路徑問題
            video_files.append({
                "path": rel_path.replace("\\", "/"), 
                "name": display_name
            })
    
    # 依名稱排序 (通常時間戳記在前面，所以會有時間順序)
    video_files.sort(key=lambda x: x['name'], reverse=True)
    return video_files

@app.get("/api/temp/chunks")
def list_chunks():
    """
    列出所有可編輯的 JSON 檔案 (對應左側 Sidebar)
    """
    json_files = []
    # 搜尋所有 JSON
    for f in glob.glob(os.path.join(DATA_DIR, "**/*.json"), recursive=True):
        rel_path = os.path.relpath(f, DATA_DIR)
        
        # 過濾規則：
        # 1. 不顯示 _edited.json (因為我們選主檔時會自動讀取 edited)
        # 2. 不顯示 _gt.json (Ground Truth) - 視需求而定，目前先隱藏
        if "_edited.json" not in rel_path and "_gt.json" not in rel_path:
            # 統一轉成 forward slash
            json_files.append(rel_path.replace("\\", "/"))
            
    json_files.sort(reverse=True)
    return {"files": json_files}

@app.get("/api/temp/chunk/{filename:path}")
def get_chunk(filename: str):
    """
    讀取專案資料。
    邏輯：優先讀取 '_edited.json'，如果沒有則讀原始 '.json'。
    同時自動尋找同一資料夾內的影片檔。
    """
    try:
        base_path = get_real_path(filename)
        
        # 1. 決定要讀哪個檔案 (Version Control)
        edited_path = base_path.replace(".json", "_edited.json")
        target_path = edited_path if os.path.exists(edited_path) else base_path
        
        if not os.path.exists(target_path):
            raise HTTPException(status_code=404, detail="File not found")

        print(f"📖 Loading: {target_path}")
        
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 2. 自動尋找對應的媒體檔案 (Media Discovery)
        # 假設 json 與 mp4 在同一層資料夾
        folder_path = os.path.dirname(filename) # 相對資料夾路徑
        real_folder = os.path.dirname(target_path) # 絕對資料夾路徑
        
        video_path = None
        if os.path.exists(real_folder):
            for v in os.listdir(real_folder):
                if v.lower().endswith(('.mp4', '.mp3', '.wav', '.m4a')):
                    # 組合出前端需要的路徑
                    video_path = os.path.join(folder_path, v).replace("\\", "/")
                    break
        
        # 如果找到了影片，更新 JSON 裡的 media_file 欄位回傳給前端
        if video_path:
            data['media_file'] = video_path
            
        return data

    except Exception as e:
        print(f"❌ Error loading chunk: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/temp/save")
def save_chunk(payload: SavePayload):
    """
    存檔 API。
    強制儲存為 '{filename}_edited.json'，永遠不覆蓋原始檔。
    """
    try:
        original_path = get_real_path(payload.filename)
        
        # 產生儲存路徑
        save_path = original_path.replace(".json", "_edited.json")
        
        # 建構要儲存的資料結構
        data_to_save = {
            "last_modified": datetime.now().isoformat(),
            "speaker_mapping": payload.speaker_mapping,
            "segments": [s.dict() for s in payload.segments], # 將 Pydantic 物件轉 dict
            # 我們不存 media_file，因為讀取時會動態偵測，保持彈性
        }
        
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
            
        print(f"💾 Saved edited version to: {save_path}")
        return {"status": "success", "saved_to": save_path}
    
    except Exception as e:
        print(f"❌ Save error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload")
async def upload_video(
    file: UploadFile = File(...), 
    tester_name: str = Form(...)
):
    """
    上傳 API (USB 匯入功能)。
    建立結構: data/{Tester}/{Timestamp}_{VideoName}/
    並自動產生一個初始 JSON 檔。
    """
    try:
        # 1. 準備路徑名稱
        timestamp = datetime.now().strftime("%Y%m%d-%H%M")
        base_name = os.path.splitext(file.filename)[0]
        safe_base_name = base_name.replace(" ", "-") # 去除空白避免路徑問題
        
        # 專案資料夾: "20260119-1120_MyVideo"
        project_folder = f"{timestamp}_{safe_base_name}"
        
        # 完整儲存路徑: data/Tester/ProjectFolder/
        save_dir = os.path.join(DATA_DIR, tester_name, project_folder)
        os.makedirs(save_dir, exist_ok=True)
        
        # 2. 儲存影片檔案
        file_path = os.path.join(save_dir, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 3. 自動產生初始 JSON (這樣前端列表才看得到)
        json_filename = f"{safe_base_name}.json"
        json_path = os.path.join(save_dir, json_filename)
        
        initial_json = {
            "speaker_mapping": {},
            "segments": [], # 初始為空，等待 AI 處理或人工輸入
            "media_file": file.filename,
            "created_at": datetime.now().isoformat()
        }
        
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(initial_json, f, ensure_ascii=False, indent=2)
            
        print(f"✅ Uploaded and initialized: {save_dir}")
        return {"message": "Upload successful", "path": file_path}
    
    except Exception as e:
        print(f"❌ Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # 確保跑在 8001 port (對應前端設定)
    uvicorn.run(app, host="0.0.0.0", port=8001)