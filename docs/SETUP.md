```
git clone https://github.com/momonong/neuroai-transcribe.git
conda create --name neuroai-transcribe
pip install -r requirements.txt
```
或僅編輯介面：pip install -r backend/requirements.txt
從專案根執行時需讓 Python 找到 core：設定 PYTHONPATH=. 或 pip install -e .

模型下載 (依需求)
```
hf download --local-dir ... pyannote/speaker-diarization-3.1
hf download --local-dir ... openai/whisper-large-v3
```
```
choco install ffmpeg
```

設定 .env 後啟動
```
docker-compose up --build -d
```
瀏覽 http://localhost:5173
