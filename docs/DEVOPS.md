
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

