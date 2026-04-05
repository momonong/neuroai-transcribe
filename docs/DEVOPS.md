
## Docker images update  

同時打上 latest 和 version 兩個標籤
> `vX.X` is the version tag, make sure to change it.
```bash
docker build -t momonong/neuroai-backend:latest -t momonong/neuroai-backend:vX.X -f backend/Dockerfile .
```

將兩個標籤推上雲端
```bash
docker push momonong/neuroai-backend:latest
docker push momonong/neuroai-backend:vX.X
```

同時打上 latest 和 version 兩個標籤
> `vX.X` is the version tag, make sure to change it.
```bash
docker build -t momonong/neuroai-frontend:latest -t momonong/neuroai-frontend:vX.X ./frontend
```

將兩個標籤推上雲端
```bash
docker push momonong/neuroai-frontend:latest
docker push momonong/neuroai-frontend:vX.X
```

##  Workstation upate
```bash
docker compose pull  
docker compose up -d  
```

---

## 語者後端環境變數（與主流程）

執行 `core.run_pipeline` 時，語者步驟由 `DIARIZATION_BACKEND` 決定（預設 `whisper_bilstm`）。`whisper_bilstm` 路徑需 `core/speaker_bilstm/`、`SPEAKER_MODEL_PATH` 與對應依賴；若改用 `pyannote` 才需要 `HF_TOKEN`。`placeholder` 僅供銜接測試（產物非真實語者）。另請留意 `whisper_bilstm` 會與主線 ASR 並存載入 Whisper，GPU/VRAM 壓力通常較高。LLM 目前保留在 Flag 階段供品質/行為標記用途。詳見 `docs/PIPELINE.md` 第 3、4 節。

