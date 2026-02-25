git clone https://github.com/momonong/neuroai-transcribe.git
conda create --name neuroai-transcribe 
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu129
<!-- notice that your env should include the pytorch packages -->

hf download --local-dir D:\hf_models\speaker-diarization-3.1 pyannote/speaker-diarization-3.1
hf download --local-dir D:\hf_models\whisper-large-v3 openai/whisper-large-v3
hf download --local-dir D:\hf_models\gemma-3-12b-it-qat-q4_0-gguf google/gemma-3-12b-it-qat-q4_0-gguf
choco install ffmpeg

<!-- set up the .env file -->
<!-- set up the env by running through the whole process -->
docker-compose up --build -d
<!-- go to localhose:5173 -->
