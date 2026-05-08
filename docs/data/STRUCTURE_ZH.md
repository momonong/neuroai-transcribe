# 資料目錄結構說明 (Data Directory Structure)

本文件說明 `data/` 目錄的組織結構與檔案用途。為了保護隱私，所有敏感個案資料均已進行去識別化處理。

## 1. 根目錄結構
```text
data/
├── subject01/               # 去識別化後的個案資料夾 (subject01 ~ subject21)
├── ...
├── default_demo/            # 用於演示的非敏感資料集
└── data_anonymization_mapping.csv  # 原始名稱與匿名 ID 的對照表 (僅限內部使用)
```

## 2. 個案資料夾內部結構 (以 subject01 為例)
每個個案資料夾均包含三個主要子目錄與元數據檔案：

### 📁 `source/` (原始輸入資料)
包含未經處理的原始影音檔案與參考轉錄稿：
- `subject01.MP4`: 原始錄影檔案。
- `subject01.mp3` / `subject01.wav`: 從影片中提取的原始音訊。
- `GTruth.srt`: 地面真值 (Ground Truth) 轉錄稿，用於評估模型準確度。
- `Aegisub.srt`: 額外的轉錄參考檔案。

### 📁 `intermediate/` (中間處理產物)
包含處理流程各個階段生成的暫存檔案：
- `chunk_X_Y_Z.wav`: 切分後的音訊區塊。
- `chunk_X_Y_Z_whisper.json`: Whisper ASR 的原始輸出。
- `chunk_X_Y_Z_diar.json`: 語者分割 (Diarization) 的結果。
- `chunk_X_Y_Z_aligned.json`: 文字與時間戳記對齊後的結果。
- `chunk_X_Y_Z_stitched.json`: 多個處理步驟整合後的片段。
- `chunk_X_Y_Z_flagged_for_human.json`: 標記為需要人工校閱的片段。

### 📁 `output/` (最終輸出結果)
- `transcript.json`: 整合後的全段轉錄內容，包含語者標籤、文字、時間戳記與驗證分數。

### 📄 元數據檔案
- `case.json`: 個案基本資訊（如原始檔名、建立時間等）。
- `status.json`: 紀錄該個案目前的處理進度（如 `created`, `processing`, `completed`）。

## 3. 處理流程概要
1. **輸入**: 將檔案放入 `source/`。
2. **處理**: 系統自動將音訊切片並存入 `intermediate/` 進行並行處理（ASR, Diarization, Alignment）。
3. **整合**: 系統將所有中間片段整合成最終報告，存於 `output/transcript.json`。

---
*更新日期：2026-05-08*
