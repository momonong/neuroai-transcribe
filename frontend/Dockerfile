# frontend/Dockerfile
FROM node:20-alpine

# 設定工作目錄
WORKDIR /app/frontend

# 複製 package.json 和 package-lock.json
COPY package*.json ./

# 安裝 npm 套件
RUN npm install

# 程式碼會透過 docker-compose 掛載