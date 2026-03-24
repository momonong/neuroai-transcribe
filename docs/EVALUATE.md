# Pipeline 稽核與 Ground Truth 評估

`core/scripts/evaluate` 提供**不需參考音檔**的中間產物檢查，以及可選的**人工稿對照**（CER / 相似度）。用於定位缺漏、Stitch 掉句、或 ASR 與最終稿落差。

## 執行方式

在**專案根目錄**執行（需能 import `core`、`shared`）：

```bash
python -m core.scripts.evaluate --case <案例名稱>
```

`<案例名稱>` 對應 `data/<案例名稱>/`（與 `run_pipeline` 的 `--case` 一致）。

### 常用參數

| 參數 | 說明 |
|------|------|
| `--case` | **必填**。案例資料夾名稱。 |
| `--json <路徑>` | 將完整報告另存為 JSON（便於留存或畫圖表）。 |
| `--ground-truth <路徑>` | 人工稿 JSON；**預設**為 `data/<case>/edited.json`。 |
| `--no-ground-truth` | 只做 intermediate 稽核，不比對人工稿。 |

範例：

```bash
python -m core.scripts.evaluate --case test
python -m core.scripts.evaluate --case test --json data/test/output/pipeline_audit.json
python -m core.scripts.evaluate --case test --ground-truth data/test/edited.json
```

### 選用依賴

- **jiwer**：安裝後才會計算以「字元當作 word」的 **CER** 及插入 / 刪除 / 替換次數。  
  `pip install jiwer`  
  未安裝時仍會輸出 **difflib** 序列相似度。

- **opencc**：若環境有 OpenCC，會額外統計「經 `s2twp` 轉換後會變更」的片段數（簡繁／異體嫌疑），供參考。

## 輸出內容概覽

### 1. Intermediate 稽核（逐 chunk）

從 `data/<case/intermediate/` 的 `chunk_*_*.wav` 推斷 chunk 列表，並檢查同幹路徑下的：

- `*_whisper.json`、`*_diar.json`、`*_aligned.json`、`*_stitched.json`、`*_flagged_for_human.json`

主要指標：

- **Whisper 時間覆蓋率**：segment 時間軸聯集長度 ÷ 由檔名推得的 chunk 時長；過低可能與 VAD、小聲語音有關。
- **時間縫隙**：chunk 內 segment 之間未被覆蓋的區間合計與最大單段縫隙（秒）。
- **Aligned**：段數、`speaker == "Unknown"` 比例。
- **Stitch ID 覆蓋**：aligned 的 `id` 是否都出現在 stitched / flagged 的 `source_ids` 聯集裡；**缺 id** 多半表示 LLM 併句漏段。
- **字元數比**：post_stitch（flagged 優先）與 aligned 總字元比，便于察覺 stitch 大幅刪改。

全案彙總包含：有無 aligned 的 chunk 數、全案 stitch 漏掉的 id 聯集、`output/transcript.json` 是否存在與片段數。

### 2. Ground truth 比對（預設開啟）

- **參考稿**：`--ground-truth` 或預設 `data/<case>/edited.json`。
- **假設稿 A — final_transcript**：`data/<case>/output/transcript.json`（與 `run_pipeline` 產物一致；頂層為 list 或含 `segments` 的 object 皆可）。
- **假設稿 B — aligned_concat_pre_stitch**：所有 chunk 的 `*_aligned.json` 依時間與 chunk 順序串成全文（**LLM stitch 前**）；若無 `intermediate` 則此項不計。

**正規化規則**（與專案內 `aaiml_paper/wer_eval.py` 風格一致，便於與既有實驗對齊）：

- 移除說話者前綴：`小孩|測試者|老師|Child|Therapist|Unknown` 加冒號形式。
- 只保留 Unicode 範圍 `\u4e00-\u9fa5`（標點與空白會去掉）。

輸出欄位：

- **reference_char_count / hypothesis_char_count**：正規化後字數。
- **difflib_sequence_ratio**：0～1，越高越接近（非標準 CER，但無 jiwer 時仍可用）。
- **jiwer_word_errors**（可選）：`cer_as_char_wer`（以字為單位的錯誤率）、`insertions`、`deletions`、`substitutions`、`hits`。

### 人工稿 JSON 格式

與後端儲存的 edited 稿相容即可，例如：

- 頂層為 **list**：每筆為含 `text`、`start` 等欄位的 segment。
- 或頂層為 **object**，且含 **`segments`** 陣列。

比對時會依 `start` 排序後將 `text` 串接成單一長字串再正規化。

## 沒有 intermediate 時

若 `data/<case>/intermediate` 目錄不存在，程式仍會回傳錯誤訊息與簡要 summary，但**仍會嘗試**做「人工稿 vs `transcript.json`」比對（若兩側檔案存在）。**aligned 全文**比對在此情境下會省略。

## 相關程式路徑

| 路徑 | 角色 |
|------|------|
| `core/scripts/evaluate/__main__.py` | `python -m core.scripts.evaluate` 入口 |
| `core/scripts/evaluate/audit.py` | CLI、掃描案例、`audit_case` |
| `core/scripts/evaluate/metrics_lib.py` | 時間軸、ID 覆蓋、GT 正規化與 CER 等純函數 |

## 解讀提示

- **aligned 與 final 的 CER 都很高**：先檢 Whisper / 對齊；若 aligned 對 GT 已較好、final 變差，則懷疑 **Stitch / Flag**。
- **Stitch 缺 id 多**：優先檢併句邏輯或 LLM 輸出是否漏帶 `source_ids`。
- **Whisper 覆蓋率低、縫隙大**：可搭配 `vad_filter`、chunk 長度、或換 ASR 模型實驗。
