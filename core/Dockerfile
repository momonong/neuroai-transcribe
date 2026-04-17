FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

# 安裝系統必備套件 (包含處理音訊的底層庫)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# 複製並安裝「去蕪存菁」依賴清單
COPY core/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製程式碼並啟動
COPY . .
EXPOSE 8003
CMD ["uvicorn", "core.main:app", "--host", "0.0.0.0", "--port", "8003"]