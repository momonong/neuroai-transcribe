# 個案分析報告：subject06

## 1. 聲學與環境品質 (Acoustic & Environment Profiling)
- **訊噪比 (SNR):** 16.25 dB (🟢 良好)
- **能量爆發 (Energy Bursts):** 0.0200 (🔴 高 - 可能包含尖叫或音訊剪輯失真)
- **頻譜質心混亂度 (Chaos Ratio):** 0.1500 (重疊語音或干擾指標)

## 2. 語者特徵與發聲行為 (Speaker Characteristics & Vocalizations)
- **語音佔比 (Speech Ratio):** 46.33% (整體說話時間比例)
- **語音破碎度 (Fragmentation Ratio):** 61.96% (短於 1.5 秒的語句比例)
- **音高變異性 (Pitch Std Dev):** 113.72 Hz (🟢 正常範圍)

## 3. 互動與語意動態 (Interaction & Overlapping Dynamics)
- **長沈默 (>2s):** 112 次 (反映互動延遲或無反應)
- **平均語句長度:** 1.53 秒

## 4. 下游影響與分析洞察 (Downstream Impact & Insights)
- **整體品質評分 (對 ASR/Diarization 友善度):** 6/10
- **主要風險:** ⚠️ 轉錄失敗或 VAD 遺漏風險極高。
- **處理建議:** 建議使用標準處理管線。

---
*由自動化 EDA 模組生成*
