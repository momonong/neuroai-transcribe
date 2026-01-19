# 檔案管理系統優化報告

## 問題分析

原本的檔案管理存在以下問題：

1. **硬編碼路徑**: `core/` 模組中有很多硬編碼的路徑，如 `"data/temp_chunks"`
2. **路徑管理混亂**: `main.py` 和 `core/` 模組對於資料夾的定義不一致
3. **檔案搜尋邏輯粗糙**: `find_video_file` 函數過於暴力，直接抓第一個 MP4
4. **缺乏統一配置**: 各模組各自管理設定，容易不一致
5. **專案管理不完善**: 沒有清楚的專案概念和組織結構

## 解決方案

### 1. 建立統一的檔案管理器 (`core/file_manager.py`)

**功能特色：**
- 自動偵測專案根目錄
- 統一的路徑生成方法
- 智慧影片檔案搜尋和匹配
- JSON 檔案管理 (載入/儲存/備份)
- 專案生命週期管理

**主要方法：**
```python
# 路徑管理
file_manager.get_project_dir(project_name)
file_manager.get_temp_chunks_dir(project_name)
file_manager.get_output_file_path(project_name, filename)

# 影片檔案管理
file_manager.find_video_files(pattern)
file_manager.find_best_video_match(reference_name)

# JSON 檔案管理
file_manager.save_json(data, file_path, backup=True)
file_manager.load_json(file_path)
file_manager.get_chunk_json_files(project_name, file_type)

# 專案管理
file_manager.create_project(video_path, project_name)
file_manager.get_project_list()
```

### 2. 建立統一的配置系統 (`core/config.py`)

**配置項目：**
- 路徑配置 (資料目錄、模型快取等)
- AI 模型配置 (Whisper、Pyannote 參數)
- LLM 配置 (API URL、金鑰)
- 音訊處理配置 (切分參數、靜音檢測)
- GPU 配置 (設備、計算類型)
- Docker 環境自動檢測

**使用方式：**
```python
from core.config import config

# 使用配置
model = WhisperModel(config.whisper_model, device=config.device)
chunks_dir = config.get_temp_chunks_dir(project_name)
```

### 3. 更新核心模組

**`core/ai_engine.py` 改進：**
- 使用檔案管理器處理所有路徑
- 支援專案概念，自動建立專案結構
- 統一的檔案儲存和備份機制

**`core/split.py` 改進：**
- 移除硬編碼路徑
- 支援可選的輸出目錄參數
- 整合配置系統

**`core/pipeline.py` 改進：**
- 使用統一配置
- 自動環境檢測 (Docker/本地)
- 標準化的模型參數

### 4. 更新 API 服務 (`main.py`)

**改進項目：**
- 使用檔案管理器替代硬編碼路徑
- 智慧影片檔案匹配
- 新增專案管理 API
- 統一的錯誤處理

**新增 API：**
```
GET  /api/projects          # 取得專案清單
POST /api/projects/create   # 建立新專案
GET  /api/videos           # 改進的影片清單 (含元資料)
```

## 新的目錄結構

```
project/
├── data/                          # 統一的資料目錄
│   ├── ASD/                      # 原始影片檔案
│   ├── temp_chunks/              # 全域暫存 chunks
│   └── output/                   # 專案輸出目錄
│       └── {project_name}/       # 個別專案
│           ├── project.json      # 專案設定
│           ├── temp_chunks/      # 專案專用 chunks
│           ├── transcript.json   # 最終結果
│           └── raw_aligned_transcript.json  # 原始結果
├── backend/
│   ├── core/
│   │   ├── file_manager.py      # 🆕 檔案管理器
│   │   ├── config.py            # 🆕 配置管理
│   │   ├── ai_engine.py         # ✅ 已更新
│   │   ├── split.py             # ✅ 已更新
│   │   └── pipeline.py          # ✅ 已更新
│   ├── main.py                  # ✅ 已更新
│   └── test_file_manager.py     # 🆕 測試腳本
└── frontend/                    # 前端不變
```

## 使用範例

### 1. 建立新專案並執行轉錄

```python
from core.ai_engine import run_neuroai_pipeline

# 自動建立專案
result_path = run_neuroai_pipeline(
    video_path="/path/to/video.mp4",
    project_name="my_project"  # 可選，會自動生成
)
```

### 2. 管理現有專案

```python
from core.file_manager import file_manager

# 列出所有專案
projects = file_manager.get_project_list()

# 取得專案檔案
project_dir = file_manager.get_project_dir("my_project")
chunks = file_manager.get_chunk_json_files("my_project", "flagged")
```

### 3. 智慧影片搜尋

```python
# 搜尋所有影片
videos = file_manager.find_video_files()

# 根據 JSON 檔名找最佳匹配影片
best_match = file_manager.find_best_video_match("chunk_1_0_123_flagged.json")
```

## 優化效果

### ✅ 解決的問題

1. **統一路徑管理**: 所有路徑都通過檔案管理器統一處理
2. **智慧檔案匹配**: 根據檔名關鍵字智慧匹配影片檔案
3. **專案組織**: 清楚的專案概念，每個轉錄任務都有獨立的工作空間
4. **配置統一**: 所有設定都在 `config.py` 中統一管理
5. **自動備份**: JSON 檔案儲存時自動建立備份
6. **環境適應**: 自動檢測 Docker 環境並調整配置

### 🚀 新增功能

1. **專案管理**: 完整的專案生命週期管理
2. **智慧搜尋**: 根據內容智慧匹配相關檔案
3. **自動配置**: 根據環境自動調整設定
4. **錯誤恢復**: 備份機制確保資料安全
5. **測試支援**: 內建測試腳本驗證功能

### 📈 效能提升

1. **減少硬編碼**: 提高程式碼可維護性
2. **統一介面**: 降低模組間耦合度
3. **自動化**: 減少手動配置需求
4. **標準化**: 統一的檔案命名和組織規則

## 遷移指南

### 對現有程式碼的影響

1. **`scripts/` 目錄**: 保持不變，繼續作為一次性測試腳本
2. **現有資料**: 自動相容，無需手動遷移
3. **API 介面**: 向後相容，新增功能不影響現有前端

### 建議的使用方式

1. **新專案**: 使用 `run_neuroai_pipeline()` 並指定專案名稱
2. **現有資料**: 可繼續使用，或透過 API 建立專案進行管理
3. **配置調整**: 透過 `.env` 檔案調整設定，無需修改程式碼

## 測試驗證

執行測試腳本驗證功能：

```bash
cd backend
python test_file_manager.py
```

測試項目包括：
- 配置載入
- 目錄建立
- 影片搜尋
- JSON 檔案管理
- 專案管理

## 總結

這次優化徹底解決了檔案管理的混亂問題，建立了一個統一、智慧、可擴展的檔案管理系統。主要改進包括：

1. **統一性**: 所有檔案操作都通過統一介面
2. **智慧性**: 自動匹配和環境檢測
3. **可維護性**: 清楚的模組分離和配置管理
4. **可擴展性**: 易於新增功能和適應新需求
5. **穩定性**: 備份機制和錯誤處理

現在你的系統有了清楚的檔案組織結構，可以更容易地管理和維護轉錄專案！