# 扁平化資料夾結構遷移完成

## 概述

成功將 NeuroAI Transcribe 系統從巢狀資料夾結構遷移到扁平化結構，簡化了資料管理和存取邏輯。

## 結構變更

### 舊結構
```
data/
├── ASD/
│   ├── 20250324-20054665XXX/
│   ├── 20250421-19777382CCC/
│   └── 20250526-19801830ZZZ/
├── temp_chunks/
├── output/
└── text/
```

### 新結構
```
data/
├── 20250324-20054665XXX/     # 直接在 data/ 下
├── 20250421-19777382CCC/
├── 20250526-19801830ZZZ/
├── temp_chunks/              # 系統資料夾
├── db/                       # 系統資料夾
└── text/                     # 系統資料夾
```

## 程式碼變更

### 後端變更

#### 1. 配置模組 (`backend/core/config.py`)
- 移除 `asd_dir` 和 `output_dir`
- 新增 `db_dir` 和 `text_dir`
- 更新 `get_case_dir()` 方法取代 `get_project_dir()`

#### 2. 檔案管理器 (`backend/core/file_manager.py`)
- 更新資料夾結構定義
- 修改影片搜尋邏輯，直接掃描案例資料夾
- 將「專案管理」改為「案例管理」
- 新增案例自動偵測功能

#### 3. 主程式 (`backend/main.py`)
- 更新 `/api/testers` 端點，返回案例清單而非測試者清單
- 修改 `/api/videos` 邏輯，適應新的扁平結構
- 更新上傳 API，使用 `case_name` 參數

#### 4. 核心模組更新
- `split.py`: 支援案例名稱參數
- `pipeline.py`: 更新範例路徑

### 前端變更

#### 1. API 整合 (`frontend/src/hooks/useTranscript.ts`)
- 更新上傳功能，使用 `case_name` 而非 `tester_name`
- 更新註解，說明現在處理的是案例清單

#### 2. 使用者介面 (`frontend/src/App.tsx`)
- 上傳對話框改為「案例名稱」輸入
- 更新相關文字和提示

## 遷移工具

### 1. 自動遷移腳本 (`backend/scripts/migrate_to_flat_structure.py`)
- 自動將 `data/ASD/` 下的資料夾移到 `data/` 根目錄
- 安全檢查，避免覆蓋現有資料
- 可選擇刪除空的 ASD 資料夾

### 2. 測試工具
- `backend/scripts/test_new_structure.py`: 測試新結構的配置和檔案管理
- `backend/scripts/test_api_integration.py`: 測試 API 整合和資料夾掃描

## 優點

1. **簡化結構**: 減少一層巢狀，更直觀
2. **易於管理**: 案例直接在 data/ 下，方便存取
3. **向後相容**: 自動偵測現有資料，無需手動配置
4. **靈活性**: 支援任意案例名稱格式

## 測試結果

✅ 後端服務正常啟動 (http://localhost:8001)  
✅ 前端服務正常啟動 (http://localhost:5174)  
✅ API 端點正常回應  
✅ 資料夾掃描正確  
✅ 檔案讀取功能正常  

## 使用方式

### 啟動服務
```bash
# 後端
python backend/main.py

# 前端
cd frontend
npm run dev
```

### 遷移現有資料
```bash
python backend/scripts/migrate_to_flat_structure.py
```

### 測試系統
```bash
python backend/scripts/test_api_integration.py
```

## 注意事項

1. 系統資料夾 (`temp_chunks`, `db`, `text`) 會被自動排除在案例清單外
2. 上傳功能現在使用案例名稱而非測試者名稱
3. 如果沒有提供案例名稱，系統會自動生成 `YYYYMMDD-HHMM-檔名` 格式
4. 現有的 JSON 檔案和影片檔案都能正常讀取和播放

## 後續建議

1. 可考慮在案例資料夾內建立子資料夾來組織不同類型的檔案
2. 可新增案例標籤或分類功能
3. 可考慮實作案例匯出/匯入功能

---

遷移完成時間: 2026-01-20  
版本: v2.0 - 扁平化結構