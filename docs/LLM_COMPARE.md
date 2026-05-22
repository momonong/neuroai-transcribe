| 項目 | 目前：Gemma‑3‑12B‑it‑QAT‑Q4_0‑GGUF | 新選項：Gemma‑4‑E4B‑it |
| --- | --- | --- |
| 參數規模 | 約 12B | 實際約 8B、有效約 4B（E4B） |
| 架構 | Dense Transformer，長上下文 | Edge 優化（MoE / PLE），偏推理與效率 |
| 量化 | GGUF Q4_0 | 官方 BF16/FP16；本地常用 Q4_K_M / Q5_K_M |
| VRAM（推論） | 權重約 6GB，含 cache 約 7–8GB | BF16 約 15GB；Q4_K_M 約 5GB |
| 推理能力 | GPQA 約 34–35% | GPQA 約 57–58%，明顯領先 |
| 長文本 | Context 可到 128K | 多實作約 32K，可配合 RAG |
| 多模態 | 目前 QAT GGUF 多為 text-only | 原生支援 text / vision / audio |
| 適合任務 | 長篇 guideline 解析、大 context summarization | 多步推理、agentic tool-use、臨床規則檢查 |
| 本地部署 | 24GB 可同時跑 LLM + Whisper | 8B + Q4_K_M 更省 VRAM、推理更強 |
