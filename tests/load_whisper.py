import torch
import time
import librosa
import os
from transformers import pipeline
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# 1. 設定參數與路徑
# ==========================================

# 替換成你實際的模型路徑
WHISPER_MODEL_PATH = os.getenv("WHISPER_MODEL_PATH")
# 替換成你實際的音頻檔案路徑
LONG_AUDIO_FILE_PATH = "data/20250324-20054665陳芮晞.mp3" 

TARGET_DURATION_SECONDS = 60 * 36 # 3 分鐘
DEVICE = 0 if torch.cuda.is_available() else -1 # 使用 GPU 0

# 確保路徑存在
if not os.path.isdir(WHISPER_MODEL_PATH):
    print(f"❌ 錯誤：找不到模型路徑 '{WHISPER_MODEL_PATH}'。請檢查路徑是否正確。")
    exit()

# ==========================================
# 2. 音頻載入 (僅載入前 3 分鐘)
# ==========================================
try:
    print(f"🔄 正在使用 librosa 載入音頻檔案的前 {TARGET_DURATION_SECONDS} 秒...")
    # sr=16000 是 Whisper 要求採樣率
    audio, sr = librosa.load(
        LONG_AUDIO_FILE_PATH, 
        sr=16000, 
        # duration=TARGET_DURATION_SECONDS # 關鍵：設定載入長度
    )
    actual_length = audio.shape[0] / sr
    print(f"✅ 音頻載入成功 (實際長度: {actual_length:.2f} 秒)")
except FileNotFoundError:
    print(f"❌ 錯誤：找不到音頻檔案。請將 '{LONG_AUDIO_FILE_PATH}' 替換為實際檔案路徑。")
    exit()
except Exception as e:
    print(f"❌ 載入音頻時發生錯誤: {e}")
    exit()

# ==========================================
# 3. 設定 Pipeline 與推論
# ==========================================
print(f"🔄 正在設定 Whisper Large v3 Pipeline (使用 GPU: {DEVICE})...")
try:
    # 使用 pipeline 簡化流程，並用 float16 減少 VRAM 佔用
    pipe = pipeline(
        "automatic-speech-recognition",
        model=WHISPER_MODEL_PATH,
        device=DEVICE,
        dtype=torch.float16,
        language='zh',
    )
    print("✅ Whisper Pipeline 設定成功。")
except Exception as e:
    print(f"❌ Pipeline 設定失敗: {e}")
    exit()

print("⏳ 開始推論 36 分鐘音頻...")
start_time = time.time()

# 運行推論 (使用分塊處理，避免單次輸入過大)
result = pipe(audio, chunk_length_s=30, return_timestamps=False)

end_time = time.time()
inference_time = end_time - start_time

# ==========================================
# 4. 輸出結果與性能指標
# ==========================================
print("\n--- 推論結果與資源消耗分析 ---")
print(f"✅ 推論完成！總耗時: {inference_time:.2f} 秒")
print(f"⏱️ 實際即時率 (RTF): {inference_time / actual_length:.2f}x (數值越低越好)")
print(f"📝 初步逐字稿片段: {result['text'][:200]}...")
print("-" * 50)

# 資源監控提醒
print("💡 資源消耗提醒：")
print("在模型運行時，Whisper Large v3 (FP16) 約佔用 9-11 GB VRAM。")
print(f"這個 RTF ({inference_time / actual_length:.2f}x) 數字將決定您未來 36 分鐘音頻的總處理時間：")
print(f"  預計總處理時間約為: {inference_time / actual_length * 36 * 60 / 60:.1f} 分鐘。")