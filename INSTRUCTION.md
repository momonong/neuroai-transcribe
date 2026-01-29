# 🧠 NeuroAI Transcribe - 部署指南 (Deployment Guide)

本指南說明如何將 **NeuroAI 系統** 部署到一台新的機器上（支援高機密性／離線運作環境）。  
本專案採用 **Docker Compose** 進行部署，並透過掛載本地模型檔案的方式，減少映像檔體積並支援離線推論。

---

## 📋 目錄
1. [硬體與系統需求](#1-硬體與系統需求)
2. [打包與傳輸檔案](#2-打包與傳輸檔案)
3. [新電腦環境設定](#3-新電腦環境設定)
4. [啟動與安裝](#4-啟動與安裝)
5. [常見問題排除](#5-常見問題排除)

---

## 1. 硬體與系統需求

在目標電腦（新電腦）上，必須滿足以下條件：

- **作業系統**: Windows 10/11 (推薦使用 WSL2) 或 Linux (Ubuntu 20.04+)。
- **GPU**: NVIDIA 顯示卡（VRAM 建議 8GB 以上，以執行 Whisper Large & Gemma）。
- **硬碟空間**: 至少預留 50GB（用於存放模型與 Docker 映像檔）。
- **必要軟體**:
  1. **NVIDIA Graphics Driver**：請更新到最新版。
  2. **Docker Desktop**（Windows）或 **Docker Engine**（Linux）。
  3. **NVIDIA Container Toolkit**：讓 Docker 能調用顯卡資源。
      - *Windows 使用者*: 在 Docker Desktop 設定中勾選「Use the WSL 2 based engine」。
      - *Linux 使用者*: 需額外安裝 `nvidia-container-toolkit`。

---

## 2. 打包與傳輸檔案

請從開發機（舊電腦）將專案複製到外部儲存裝置（如隨身碟、NAS）。

### ✅ 必須複製的資料夾與檔案

以下為需完整保留的目錄結構：

---

**📁 專案結構**
```text
NeuroAI-Transcribe/
├── backend/                # 後端原始碼
│   ├── core/
│   │   └── workers/        # 確保 worker scripts (run_whisper.py, run_diar.py) 都在
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/               # 前端原始碼
│   ├── src/
│   ├── package.json
│   └── Dockerfile
├── model_cache/            # [重要] 預先下載好的 AI 模型
│   ├── hub/                # HuggingFace 模型 (Pyannote, Whisper...)
│   └── gemma...            # LLM 模型檔案 (.gguf)
├── docker-compose.yml      # 部署設定檔
└── .env                    # 環境變數設定 (含 API Token)
```
---

### ❌ 不需要複製的檔案  
（可排除以節省傳輸時間）

- `frontend/node_modules`（Docker 會重新安裝）
- `backend/venv`（Docker 內有獨立環境）
- `backend/__pycache__`
- `.git`（除非需要在新電腦進行版控）

---

## 3. 新電腦環境設定

### 🔹 步驟 A：放置檔案
將專案資料夾複製到新電腦的任意位置，例如：

- Windows: `D:\Projects\NeuroAI`
- Linux: `~/projects/neuroai`

### 🔹 步驟 B：檢查設定檔 (.env)
打開專案根目錄下的 `.env` 檔案，確認以下設定是否符合新電腦環境：

```ini
# 確認 Port 是否衝突 (預設後端 8001, LLM 8000)
HOST_BACKEND_PORT=8001
HOST_LLM_PORT=8000

# 確認模型路徑 (如果是整個資料夾一起複製，保持預設即可)
MODEL_CACHE_DIR=./model_cache

# HuggingFace Token (必須保留)
HF_TOKEN=hf_xxxxxx...
```

---

## 4. 啟動與安裝

⚠️ **重要提示：第一次啟動需連網**  
雖然本系統設計為可離線執行，但第一次部署時 Docker 需要：
- 下載基礎映像檔（Python, Node.js）
- 安裝程式依賴（`pip install`, `npm install`）

請確保新電腦在第一次執行時已連接網際網路。

### 🖥️ 執行指令

開啟終端機 (Terminal / PowerShell / CMD)，進入專案目錄：

```bash
cd path/to/NeuroAI
```

執行 Docker Compose 建置與啟動：

```bash
docker-compose up --build
```

### ⏱️ 等待安裝完成

第一次執行會花費較長時間（約 10–20 分鐘），因為需要下載 PyTorch (2GB+) 並編譯前端程式。

當終端機出現以下訊息時，代表啟動成功：

```
llm-server | ... HTTP server listening  
backend    | ... Application startup complete
```

### 🌐 開始使用

打開瀏覽器並輸入以下網址：  
👉 [http://localhost:5173](http://localhost:5173)

> 注意：基於安全性設定，此網頁僅能從 **本機開啟**，無法從區域網路其他裝置連入。

---

## 5. 常見問題排除

### Q1: 啟動時顯示 "driver: nvidia" 錯誤？
**原因**：Docker 抓不到顯卡。  
**解法**：確認新電腦已安裝 NVIDIA 驅動程式，且 Docker Desktop 已啟用 GPU 支援（WSL2 模式）。

---

### Q2: 執行 Pipeline 時顯示 "CUDA out of memory"？
**原因**：顯卡記憶體不足。  
**解法**：

- 確保沒有其他程式占用顯卡。
- 專案已內建「斷點續傳」與「進程隔離」功能，可直接重新執行 Pipeline，系統會自動跳過已完成的步驟並繼續處理剩餘部分。

---

### Q3: 如何關閉系統？
在執行 `docker-compose up` 的終端機中按下 **Ctrl + C** 等待容器優雅關閉。  
若要移除所有容器，執行：

```bash
docker-compose down
```

---

### Q4: 之後可以斷網使用嗎？
可以。  
只要第一次 `docker-compose up --build` 成功執行過，且未刪除 Docker Image 或 Cache，  
之後拔掉網路線，系統依然可以正常讀取本地的 `model_cache` 進行運作。
