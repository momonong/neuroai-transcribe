# NeuroAI Transcribe - 當前管線架構 (Current Pipeline)

本文件紀錄 NeuroAI Transcribe 專案**當前實際運行**的語音轉錄與處理管線。若要查看未來的理想架構與目標，請參考 [`PIPELINE_GOAL.md`](./PIPELINE_GOAL.md)。

## 1. 系統概覽 (System Overview)
目前的轉錄流程主要由 `core/overall_pipeline.py` (以及 `core/run_pipeline.py`) 作為中樞進行排程，採用「分段處理、個別推論、後端對齊、規則併句」的策略。主要目標是能夠穩定地處理長達 40 分鐘的臨床評估影片，並藉由切片 (Chunking) 機制來控制記憶體消耗（解決 GPU OOM 卡死問題）。

## 2. 微服務與目錄架構 (Microservices Architecture)
- **`core/`**: 系統的核心中樞，負責執行端到端的資料管線，包含切分音訊、呼叫推論 API、對齊結果以及規則併句。
- **`services/`**: 獨立封裝的 AI 服務。目前 Whisper 語音辨識已經服務化 (透過 HTTP API 呼叫)，確保與主排程解耦並有獨立環境。
- **`backend/` & `frontend/`**: 處理使用者介面、影片上傳以及檢視轉錄結果的後端 API 與前端 React 畫面。
- **`models/` & `data/`**: 共用掛載目錄，分離龐大的模型權重以及高機敏的臨床原始音訊與中介檔案。

## 3. 端到端資料流與管線步驟 (End-to-End Data Pipeline)

以下為目前系統**實際執行**的資料流：

```mermaid
graph TD
    subgraph Phase 1: 音訊切分 (Audio Splitting)
        A[輸入影片 /data/source/] --> B(SmartAudioSplitter)
        B --> C[產生多個 chunk_*.wav 片段]
    end
    
    subgraph Phase 2: AI 推論與對齊 (AI Processing)
        C --> D(Whisper HTTP API)
        C --> E(Diarization: Pyannote/BiLSTM/Placeholder)
        D --> F[_whisper.json]
        E --> G[_diar.json]
        F --> H(Alignment: 透過時間軸交疊比對)
        G --> H
        H --> I[產生各片段的 _aligned.json]
    end
    
    subgraph Phase 3: 合併與規則併句 (Merge & Stitch)
        I --> J(合併所有 _aligned.json)
        J --> K{是否啟用規則併句?}
        K -- Yes --> L(run_stitching_logic)
        K -- No --> M(跳過併句, 維持原始段落)
    end
    
    subgraph Phase 4: 異常標記與輸出 (Flagging & Output)
        L --> N(run_anomaly_detector)
        M --> N
        N --> O[標註 needs_review = True]
        O --> P[輸出最終 final_transcript.json]
    end
```

### Phase 1: 音訊切分 (Audio Splitting)
- **工具**: `SmartAudioSplitter` (`core/split.py`)
- **動作**: 為了防止處理 40 分鐘完整音訊時導致 GPU 記憶體不足，系統會先將長音訊切割成多個較短的片段（例如 4 個 Chunk），儲存於 `intermediate` 目錄中。

### Phase 2: AI 推論與對齊 (AI Processing)
- **工具**: `PipelinePhase2` (`core/pipeline/phase2.py`)
- **動作**: 針對每個 Chunk，系統分別進行以下處理：
  1. **Whisper (ASR)**: 呼叫 `services/whisper` 提供的 HTTP API 進行語音辨識，產出包含文字與時間軸的 `_whisper.json`。
  2. **Diarization (語者分離)**: 根據設定 (`config.diarization_backend`)，使用 Pyannote、自訂的 Whisper BiLSTM 或 Placeholder 進行語者分離，產出純語者標籤與時間軸的 `_diar.json`。
  3. **Alignment (對齊)**: 結合 `_whisper.json` 與 `_diar.json`。利用兩者時間軸的交疊程度 (Overlap)，將每一句 Whisper 辨識的文字分配給佔比最長的語者 (Speaker)，並加上整體時間偏移量 (Offset)，最終輸出 `_aligned.json`。

### Phase 3: 合併與規則併句 (Merge & Stitch)
- **合併 (Merge)**: 系統將所有 Chunk 的 `_aligned.json` 依照時間順序讀取並組合成單一序列。
- **規則併句 (Stitch)**: 
  - **工具**: `run_stitching_logic` (`core/stitch.py`)
  - **動作**: 檢查相鄰的段落，如果屬於同一個語者，且語句停頓時間在閾值內，則將它們合併成一個較長的句子。若使用者設定 `skip_stitch` (No-Stitch)，則會跳過此步驟保持原始片段。

### Phase 4: 異常標記與輸出 (Flagging & Output)
- **異常標記 (Flagging)**: 
  - **工具**: `run_anomaly_detector` (`core/flag.py`)
  - **動作**: 基於靜態規則分析句子。如果發現句子內含有不確定性、標籤未知、或是異常特徵，則會將該段落標記為 `needs_review: True`，以提醒臨床人員後續需人工確認。
- **最終輸出**: 產出 `final_transcript.json`，其中包含影片資訊、整體統計（總段落數、需檢查段落數）以及完整的對話陣列，供前端介面載入與編輯。

## 4. 當前待優化點 (Areas for Optimization)
*   目前的 Alignment 是基於**純時間軸交疊比對**的硬性規則 (Hard rule)，這在遇到交疊語音或短促音時容易產生誤差。未來將改由 Agentic 語意修正來取代/強化這部分的邏輯（見 `PIPELINE_GOAL.md`）。
*   目前的語者標籤仍為盲目標籤 (如 `SPEAKER_00`)，未具備自動辨識 Tester 與 Child 的能力，且尚未處理「媽媽語」造成的聲學混淆。
*   臨床特徵分析（如仿說、換輪延遲等）尚未整合進主幹自動化管線中。
