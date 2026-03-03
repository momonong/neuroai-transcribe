# backend/Dockerfile
# Build context: 專案根目錄 (docker-compose 指定 context: .)
# 映像內含 backend + core，並安裝完整依賴以支援 API 與 pipeline
FROM python:3.10-slim

WORKDIR /app

# 先安裝依賴（專案根 requirements.txt 含 backend + core）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製程式碼（執行時可用 volume 覆蓋以熱更新）
COPY backend/ ./backend/
COPY core/ ./core/

# 後端工作目錄與啟動方式由 docker-compose 指定
# working_dir: /app/backend, command: uvicorn main:app ...
# 並設定 PYTHONPATH=/app 使 import core 可找到 /app/core
