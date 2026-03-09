# 前處理流程說明

專案前處理包含：整理資料夾結構、單一檔案／批次執行 pipeline（切音、Whisper、 diarization、對齊、stitch、flag）。資料放在專案根目錄底下的 `data/`（因保密需求可能在 .cursorignore，本機需自行確保路徑正確）。

## 資料夾結構

- `data/`：前處理資料根目錄（專案根目錄底下）。
- 每筆資料一個子資料夾，例如：`data/20250115-00000123張三/`。
- 每筆底下預期結構：
  - `source/`：原始影音檔（前處理前先整理到這裡）。
  - `intermediate/`：pipeline 產生的中間檔（切 chunk、Whisper、diarization、對齊等）。
  - `output/`：最終輸出（如 transcript.json）。

## 步驟一：整理資料夾（只做一次）

把「每筆資料」資料夾裡的所有檔案收進該筆的 `source/`，方便後續 pipeline 讀取。

- **腳本**：`core/scripts/data/organize_for_preprocess.py`
- **行為**：掃描 `data/` 底下每個子資料夾；若已有 `source/` 就跳過，否則建立 `source/` 並把該資料夾內所有項目移入 `source/`。
- **執行**（請在專案根目錄）：

  ```bash
  python core/scripts/data/organize_for_preprocess.py
  ```
