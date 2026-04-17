# 使用驗證成功的最新官方 GPU 推理映像檔
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

# 1. 設定環境變數：確保輸出即時顯示，並將工作目錄加入路徑
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

# 2. 安裝系統套件
# 增加 libsndfile1 (soundfile 依賴) 與 ffmpeg
RUN printf 'Acquire::Retries "5";\nAcquire::https::Timeout "240";\nAcquire::http::Timeout "240";' > /etc/apt/apt.conf.d/80-retries && \
    apt-get update --fix-missing && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# 3. 複製依賴清單並安裝
# 僅安裝 Python 應用層套件，不碰 Base Image 預裝好的 torch/cuda
COPY core/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. 複製整個專案
COPY . .

# 5. 曝露 FastAPI 埠號
EXPOSE 8003

# 6. 啟動指令：使用 module 方式啟動核心服務
CMD ["uvicorn", "core.main:app", "--host", "0.0.0.0", "--port", "8003"]