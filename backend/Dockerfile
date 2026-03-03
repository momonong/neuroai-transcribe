# Backend Production：僅打包 backend + shared，不包含 core
# build context 請用專案根目錄：docker-compose 設 context: ., dockerfile: backend/Dockerfile
FROM python:3.10-slim

WORKDIR /app

# 依賴
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# 程式碼（僅 backend 與 shared）
COPY backend/ ./backend/
COPY shared/ ./shared/

ENV PYTHONPATH=/app
WORKDIR /app/backend
EXPOSE 8001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
