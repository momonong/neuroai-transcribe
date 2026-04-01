
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

執行 `core.run_pipeline` 時，語者步驟由 `DIARIZATION_BACKEND` 決定（預設 `pyannote`）。若容器內**不**裝 Pyannote／不需 HF，可改 `placeholder` 做銜接測試（產物非真實語者）。BiLSTM 實作接線前請勿將 `whisper_bilstm` 用於正式轉錄。詳見 `docs/PIPELINE.md` 第 3、4 節。

