# 使用官方 GPU 推理映像檔 (PyTorch + CUDA)
FROM pytorch/pytorch:2.2.0-cuda12.1-cudnn8-runtime

# 設定環境變數
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 設定工作目錄
WORKDIR /app

# 安裝系統套件 (ffmpeg 用於音影片處理, build-essential 用於編譯某些套件)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 複製依賴清單並安裝
# 注意：這裡複製 core/requirements.txt
COPY core/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製整個專案內容 (包含 core/, shared/ 等，以支援跨資料夾 import)
COPY . .

# 曝露 FastAPI 埠號
EXPOSE 8003

# 啟動指令：執行 core 資料夾下的 main.py
CMD ["uvicorn", "core.main:app", "--host", "0.0.0.0", "--port", "8003"]
