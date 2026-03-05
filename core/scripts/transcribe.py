import torch
import time
import librosa
import os
import json # 新增 json 模組
from transformers import pipeline
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# 1. 設定參數與路徑
# ==========================================

WHISPER_MODEL_PATH = os.getenv("WHISPER_MODEL_PATH")
LONG_AUDIO_FILE_PATH = os.getenv("AUDIO_FILE")
# 設置轉錄結果的儲存路徑 (改為 JSON 格式)
TRANSCRIPT_OUTPUT_PATH = "data/text/full_whisper_transcript_with_timestamps.json" 

TARGET_DURATION_SECONDS = 60 * 36 # 36 分鐘
DEVICE = 0 if torch.cuda.is_available() else -1 # 使用 GPU 0

if not os.path.isdir(WHISPER_MODEL_PATH):
    print(f"❌ 錯誤：找不到模型路徑 '{WHISPER_MODEL_PATH}'。請檢查路徑是否正確。")
    exit()

# ==========================================
# 2. 音頻載入 (完整載入)
# ==========================================
try:
    print(f"🔄 正在使用 librosa 載入完整的 {TARGET_DURATION_SECONDS/60:.0f} 分鐘音頻檔案...")
    audio, sr = librosa.load(
        LONG_AUDIO_FILE_PATH, 
        sr=16000, 
    )
    actual_length = audio.shape[0] / sr
    print(f"✅ 音頻載入成功 (實際長度: {actual_length:.2f} 秒)")
except Exception as e:
    print(f"❌ 載入音頻時發生錯誤: {e}")
    exit()

# ==========================================
# 3. 設定 Pipeline 與推論 (關鍵修正區塊)
# ==========================================
print(f"🔄 正在設定 Whisper Large v3 Pipeline (使用 GPU: {DEVICE})...")
try:
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

print("⏳ 開始推論 36 分鐘音頻 (含時間標記)...")
start_time = time.time()

# 關鍵修正： return_timestamps=True，並移除 chunk_length_s
result = pipe(
    audio, 
    return_timestamps=True, 
    # 不需指定 chunk_length_s
)

end_time = time.time()
inference_time = end_time - start_time

# ==========================================
# 4. 輸出結果與性能指標 (修正輸出格式)
# ==========================================
print("\n--- 推論結果與檔案儲存 ---")

# 這裡 result 是一個字典，包含 'text' 和 'chunks'
full_transcript_data = result['chunks']

# 寫入 JSON 檔案
try:
    with open(TRANSCRIPT_OUTPUT_PATH, "w", encoding="utf-8") as f:
        # 使用 json.dump 儲存帶有時間標記的結構化數據
        json.dump(full_transcript_data, f, ensure_ascii=False, indent=4)
    print(f"💾 完整結構化逐字稿已儲存至: {TRANSCRIPT_OUTPUT_PATH}")
except Exception as e:
    print(f"❌ 儲存檔案失敗: {e}")

# 性能指標
print("\n--- 性能指標 ---")
print(f"✅ 推論完成！總耗時: {inference_time:.2f} 秒")
print(f"⏱️ 實際即時率 (RTF): {inference_time / actual_length:.2f}x")
print(f"📝 初步逐字稿片段 (前 5 句):")
# 輸出前 5 句，顯示時間標記
for i, chunk in enumerate(full_transcript_data[:5]):
    start_time_s = chunk['timestamp'][0]
    end_time_s = chunk['timestamp'][1]
    print(f"  [{start_time_s:.2f}s - {end_time_s:.2f}s] {chunk['text']}")
    if i == 4: break
print("-" * 50)