# frontend/Dockerfile

# 使用 Node.js 環境
FROM node:20-slim

WORKDIR /app

# 先複製 package.json 安裝依賴 (利用 Docker Cache 加速)
COPY package*.json ./
RUN npm install

# 複製其餘程式碼
COPY . .

# [關鍵] 開發模式通常跑在 3000 或 5173 (看你是用 React CRA 還是 Vite)
# 假設你是用 Vite，通常是 5173；如果是 Next.js/CRA 是 3000
# 這裡先預設開放這兩個，之後看你實際用哪個
EXPOSE 3000 5173

# [超級關鍵] 
# 在 Docker 裡跑 dev server，必須加上 --host 0.0.0.0
# 不然它只會監聽容器內的 localhost，你的電腦會連不進去
CMD ["npm", "run", "dev", "--", "--host"]