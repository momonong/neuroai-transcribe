
## Docker images update  

Go to `.env` to update the `IMAGE_TAG`.
NOTE: We need to update 2 times, version tag and latest tag.

```bash
docker compose build
docker compose push
```

---

## 語者後端環境變數（與主流程）

執行 `core.run_pipeline` 時，語者步驟由 `DIARIZATION_BACKEND` 決定（預設 `whisper_bilstm`）。`whisper_bilstm` 路徑需 `core/speaker_bilstm/`、`SPEAKER_MODEL_PATH` 與對應依賴；若改用 `pyannote` 才需要 `HF_TOKEN`。`placeholder` 僅供銜接測試（產物非真實語者）。另請留意 `whisper_bilstm` 會與主線 ASR 並存載入 Whisper，GPU/VRAM 壓力通常較高。LLM 目前保留在 Flag 階段供品質/行為標記用途。詳見 `docs/PIPELINE.md` 第 3、4 節。
