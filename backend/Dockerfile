# backend/Dockerfile

# 使用 Python 3.10 (或你需要的版本)
FROM python:3.10-slim

# 設定工作目錄
WORKDIR /app

# 安裝系統依賴 (如果你的 audio 處理需要 ffmpeg 等，這裡要加)
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# 複製 requirements 並安裝
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir --default-timeout=1000 -r requirements.txt
    
# 複製剩下的程式碼
COPY . .

# 啟動指令 (注意這裡綁定 0.0.0.0，container 內部 port 設為 8000)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]