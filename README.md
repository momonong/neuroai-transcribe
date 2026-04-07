# NeuroAI Transcribe

臨床訪談語音轉寫與校稿系統，適用於 ASD（自閉症類群障礙）診斷訪談等情境。系統結合語音辨識、說話人分離（diarization）與後處理，產出可檢視、可編輯的逐字稿。

---

## 架構總覽

專案採**關注點分離**：**網頁層**（前端 + FastAPI 後端）與 **AI 轉錄核心**（`core/`）分開維護與部署。

| 區塊 | 內容 | 預設 Docker 映像 |
|------|------|------------------|
| Web | `frontend/`（React + Vite）經 Nginx 提供靜態頁並反向代理 `/api`、`/static` → `backend/`（FastAPI） | 是（`frontend` + `backend` 兩個服務） |
| 資料 | `shared/file_manager` 約定之 `data/<案例>/`（`source/`、`intermediate/`、`output/` 等） | 以 volume 掛載 `./data` |
| AI 核心 | Whisper、faster-whisper、語者後端（預設 `whisper_bilstm`，可選 Pyannote 等）、對齊、併句（stitch）、標記（flag） | **否**（`core/` 不進後端映像，見下方） |

```
┌────────────────────────────────────────────────────────────────────┐
│  Docker Compose（適合輕量部署／僅編修介面）                           │
│  ┌──────────────┐         ┌──────────────┐                           │
│  │  Frontend    │  :80    │   Nginx      │  SPA + proxy /api、/static│
│  │  (React/Vite)│ ──────► │              │                           │
│  └──────────────┘         └──────┬───────┘                           │
│                                  │                                   │
│                                  ▼                                   │
│  ┌──────────────┐         ┌──────────────┐   ┌──────────┐            │
│  │  Backend     │ ◄────── │   shared/    │   │  data/   │            │
│  │  (FastAPI)   │         │ file_manager │   │ (volume) │            │
│  └──────────────┘         └──────────────┘   └──────────┘            │
└────────────────────────────────────────────────────────────────────┘

專案根目錄（未納入預設 backend 映像）
  core/           轉錄管線：切分、Phase2（ASR/diar/對齊）、stitch、flag、run_pipeline
  scripts/        Whisper 子行程、評估與實驗腳本（見「專案結構」）
  backend/        API 與服務層（routers / services）
  frontend/       編修介面原始碼
  shared/         路徑與檔案邏輯（後端與 core 共用）
  docs/           管線細節、部署與評估說明
```

**部署時請注意：**預設 `backend` 映像**不含** `core/` 與 GPU 重型依賴。`main.py` 會在上傳後以子程序呼叫 `python -m core.run_pipeline`；在僅含 Web 的容器內若未另行掛載或打包 `core`，該步驟會無法執行。實務上常見作法是在具 GPU 的環境手動或排程執行管線，或自建含 `core` 與 CUDA 的後端映像。詳見 `docs/INSTRUCTION.md`、`docs/PIPELINE.md`。

**管線與資料流**（兩種完整流程差異、環境變數、檔名慣例）以 [`docs/PIPELINE.md`](docs/PIPELINE.md) 為準。

---

## 快速開始

### 需求

- Docker 與 Docker Compose（僅跑 Web）
- （選用）在本機跑完整 AI 管線：Python 3.10+、NVIDIA GPU、依 `core/requirements.txt` 安裝；語者模型／Pyannote 等需依 `core/config.py` 與環境變數設定（如 `HF_TOKEN`、`DIARIZATION_BACKEND`、`SPEAKER_MODEL_PATH`）

### 使用 Docker（建議僅需編修介面時）

1. 複製專案並進入目錄  
   `git clone <repository-url> && cd neuroai-transcribe`

2. 建置並啟動  
   `docker compose up --build -d`  
   （若使用舊版 Compose，可改用 `docker-compose`。）

3. 瀏覽器開啟 **http://localhost:55688**  
   `docker-compose.yml` 將前端對應為 `55688:80`；Nginx 會把 `/api`、`/static` 轉到後端服務 `backend:8001`。

---

## 本機開發

### 後端

專案根目錄需在 `PYTHONPATH` 中，以便載入 `shared`（與生產映像中 `PYTHONPATH=/app` 一致）。

```bash
cd neuroai-transcribe
pip install -r backend/requirements.txt
export PYTHONPATH="$(pwd)"   # Windows PowerShell: $env:PYTHONPATH = (Get-Location).Path
cd backend
uvicorn main:app --host 0.0.0.0 --port 8001
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

開發伺服器預設 **http://localhost:5173**，並將 `/api`、`/static` 代理到 **8001**（見 `frontend/vite.config.ts`）。

### AI 管線（core）

```bash
cd neuroai-transcribe
pip install -e .                    # 以 pyproject.toml 註冊 core 套件（可選但建議）
pip install -r core/requirements.txt
export PYTHONPATH="$(pwd)"
python -m core.run_pipeline <影片路徑> --case <案例名稱>
```

`core/run_pipeline.py` 為後端預設觸發的入口；另有一條合併策略不同的 `core/overall_pipeline.py`，差異說明見 `docs/PIPELINE.md`。

**關於 `scripts/`：**`core/pipeline/phase2.py` 會以子程序執行 `python -m core.scripts.whisper_one_chunk`。目前倉庫內對應實作位於專案根的 **`scripts/`** 目錄；若執行時出現 `No module named 'core.scripts'`，需將該目錄調整為可匯入的 `core.scripts` 套件路徑（例如配置為 `core/scripts` 並含 `__init__.py`），或依團隊內部約定修正 `PYTHONPATH`／安裝方式。

### 開發依賴

根目錄 `requirements-dev.txt` 目前主要列出 `pytest`；其餘說明可參考 `docs/SETUP.md`。

---

## 專案結構

```
neuroai-transcribe/
├── pyproject.toml          # pip install -e . 時註冊 core 套件
├── requirements-dev.txt    # 開發／測試（如 pytest）
├── docker-compose.yml      # frontend + backend；data 掛載、後端環境變數
├── .dockerignore           # backend 建置時排除 core、frontend、data 等
│
├── frontend/               # React + Vite
│   ├── src/
│   ├── nginx.conf          # 正式環境：SPA + 反向代理 /api、/static
│   ├── Dockerfile
│   └── package.json
│
├── backend/                # FastAPI
│   ├── main.py             # 應用程式入口、靜態掛載、router 註冊、可選子程序跑管線
│   ├── config.py           # DATA_DIR、PROJECT_ROOT、IGNORE_DIRS
│   ├── schemas.py
│   ├── requirements.txt
│   ├── Dockerfile          # 僅複製 backend/ + shared/
│   ├── routers/            # videos, chunks, export, upload
│   └── services/           # chunk_service, video_service
│
├── shared/                 # 與後端、core 共用
│   └── file_manager.py     # 案例目錄、status、合併 chunk、影片掃描等
│
├── core/                   # AI 管線（預設不進 Docker 後端映像）
│   ├── config.py           # Whisper、diarization 後端、chunk 參數、.env
│   ├── run_pipeline.py     # NeuroAIPipeline 主入口（後端上傳後預設呼叫）
│   ├── overall_pipeline.py # 另一套「全流程」合併策略（見 PIPELINE.md）
│   ├── split.py            # SmartAudioSplitter
│   ├── ai_engine.py
│   ├── diarization_placeholders.py
│   ├── pipeline/           # phase2.py：Whisper / diar / 對齊（PipelinePhase2）
│   ├── stitching/          # 規則併句實作
│   ├── stitch.py           # 轉接至 core.stitching（相容舊 import）
│   ├── flagging/             # LLM 異常標記等
│   ├── flag.py             # 轉接至 core.flagging
│   ├── speaker_bilstm/     # 預設語者後端推論相關
│   ├── requirements.txt
│   └── __init__.py
│
├── scripts/                # Whisper chunk 子行程、模型與評估工具、批次與遷移腳本
│   ├── whisper_one_chunk.py
│   ├── model/
│   ├── evaluate/
│   └── …
│
├── data/                   # 案例資料（多為 .gitignore）；Docker 掛載至容器內 /app/data
└── docs/                   # PIPELINE、INSTRUCTION、SETUP、評估與遷移說明等
```

---

## 功能摘要

### 網頁介面（Docker 或本機後端 + 前端）

- 依案例列出／選擇影片；上傳影片並建立案例
- 讀取、編輯、儲存逐字稿 chunk
- 輪詢處理進度：`GET /api/status/{case_name}`
- 匯出合併後資料集（whisper、diar、aligned、stitched、flagged、edited）
- 透過 `/static/` 播放掛載於 `data/` 的媒體

### AI 管線（需在含 `core` 與依賴的環境執行）

- 音訊切 chunk（`core/split.py`）
- 每 chunk：ASR、語者分離、對齊（`core/pipeline/phase2.py`）
- 併句與標記（`core/stitching/`、`core/flagging/`）
- 單一入口：`python -m core.run_pipeline`；行為與環境變數見 `docs/PIPELINE.md`

---

## API 摘要

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/videos` | 列出影片（供前端選擇） |
| GET | `/api/cases` | 列出 `data/` 下案例資料夾 |
| GET | `/api/temp/chunks` | 列出 transcript chunk 檔（可選 `?case=`） |
| GET | `/api/temp/chunk/{filename}` | 取得單一 chunk JSON |
| POST | `/api/temp/save` | 儲存編輯後內容 |
| POST | `/api/upload` | 上傳影片（表單欄位 `case_name`） |
| GET | `/api/status/{case_name}` | 讀取處理狀態 |
| GET | `/api/export/{case_name}/{dataset_type}` | 匯出資料集（如 `edited`、`flagged`） |
| — | `/static/` | 靜態檔案（影片等），對應 `data/` |

---

## 映像建置與推送

- 範例映像名稱見 `docker-compose.yml`（如 `momonong/neuroai-backend:latest`、`momonong/neuroai-frontend:latest`）。
- 建置後推送：  
  `docker push momonong/neuroai-backend:latest`  
  `docker push momonong/neuroai-frontend:latest`
- 離線部署與完整步驟見 **`docs/INSTRUCTION.md`**；維運相關見 **`docs/DEVOPS.md`**。

---

## 臨床使用聲明

本系統用於輔助訪談逐字稿產製與校閱，**不能**取代專業判斷。使用時請遵守所在地醫療與個資法規。

---

## 授權與支援

- 使用方式請遵循專案授權與研究倫理要求。
- 技術問題可於倉庫開 issue；管線與目錄慣例請優先查閱 **`docs/PIPELINE.md`**。
