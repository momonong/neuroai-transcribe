import whisperx
from whisperx.diarize import DiarizationPipeline
import json
import os
import torch
import time
from dotenv import load_dotenv

# ==========================================
# 🚑【終極暴力修正】強制關閉 PyTorch 2.6+ 安全檢查
# ==========================================
# 之前的 Patch 太禮貌了，現在我們不管呼叫者要求什麼，
# 強制將 weights_only 設為 False。
original_load = torch.load

def aggressive_load(*args, **kwargs):
    # 直接覆寫，不管原本傳進來什麼
    kwargs['weights_only'] = False 
    return original_load(*args, **kwargs)

# 替換掉系統原本的 load 函數
torch.load = aggressive_load
print("🔧 已強制解除 PyTorch 模型讀取限制 (Aggressive Patch Applied)")
# ==========================================

load_dotenv()

# ... (以下接你原本的程式碼) ...


# ==========================================
# 1. 設定
# ==========================================
# 不需要指到 config.yaml 了，直接用 HuggingFace Token
HF_TOKEN = os.getenv("HF_TOKEN") 
AUDIO_FILE = os.getenv("AUDIO_FILE")
OUTPUT_JSON = "data/text/stage1_whisperx_aligned.json"

# 設定運算裝置 (5090 / 3090 / 4060 等)
device = "cuda" 
batch_size = 16 # 顯存大(24G)可以開到 16 或 32，顯存小(16G)開 8 或 4
compute_type = "float16" # 5090 絕對支援 float16

print(f"🚀 [Stage 1] 啟動感知層 (WhisperX Pipeline)...")
print(f"   - Device: {device}")
audio_file_show = AUDIO_FILE.replace(os.getenv("TESTER_NAME"), "")
print(f"   - Audio: {audio_file_show}")

start_total = time.time()

# ==========================================
# 2. Transcribe (轉錄)
# ==========================================
print("\n📝 [Step 1] 載入 Whisper 模型與轉錄...")
# model_dir 可以指定本地路徑，如果不指定它會自動管理快取
model = whisperx.load_model("large-v3", device, compute_type=compute_type, language="zh")

# 執行轉錄
audio = whisperx.load_audio(AUDIO_FILE)
result = model.transcribe(audio, batch_size=batch_size)
print(f"✅ 轉錄完成 (Segments: {len(result['segments'])})")

# ==========================================
# 3. Alignment (強制對齊 - 這是原本腳本沒有的神技)
# ==========================================
print("\n📐 [Step 2] 執行音素級強制對齊 (Phoneme Alignment)...")
# 這一步會修正 ASR 的時間戳，讓它準確到毫秒
model_a, metadata = whisperx.load_align_model(language_code=result["language"], device=device)
result = whisperx.align(result["segments"], model_a, metadata, audio, device, return_char_alignments=False)
print("✅ 對齊完成")

# ==========================================
# 4. Diarization (語者分離)
# ==========================================
print("\n👂 [Step 3] 執行語者分離 (Speaker Diarization)...")
# 這裡直接呼叫 Pyannote 3.1，不需要手動載入 config.yaml
diarize_model = DiarizationPipeline(use_auth_token=HF_TOKEN, device=device)
diarize_segments = diarize_model(audio)

# 把語者 ID 分配給剛剛轉錄好的文字
# min_speakers 和 max_speakers 可以幫助模型更準確 (通常 ASD 場景就是 2-3 人)
result = whisperx.assign_word_speakers(diarize_segments, result)
print("✅ 語者分配完成")

# ==========================================
# 5. 輸出結果與格式化
# ==========================================
print("\n🧠 [Orchestrator] 正在打包資料...")

final_corpus = []
for seg in result["segments"]:
    final_corpus.append({
        "start": round(seg["start"], 3),
        "end": round(seg["end"], 3),
        "speaker": seg.get("speaker", "UNKNOWN"), # 如果沒抓到語者會標示 UNKNOWN
        "text": seg["text"].strip()
    })

os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(final_corpus, f, ensure_ascii=False, indent=4)

print("-" * 50)
print(f"💾 [Output] 已生成對齊語料庫: {OUTPUT_JSON}")
print(f"🎉 總耗時: {time.time() - start_total:.1f} 秒")