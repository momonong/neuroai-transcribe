# backend/Dockerfile
FROM python:3.10-slim

# 設定工作目錄
WORKDIR /app/backend

# 複製 requirements.txt 並安裝套件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 由於我們在 docker-compose 中會用 volume 掛載程式碼，這裡不需要 COPY 其他檔案