import os
import json
import torch
import math
from dotenv import load_dotenv

# --- 1. 設定模型路徑 (最關鍵的一步) ---
# 載入 .env (確保裡面有 HF_TOKEN)
load_dotenv()

# 設定 Pyannote (HuggingFace) 的 Cache 路徑
# Pyannote 會去這個路徑下的 "hub" 資料夾找模型
MODEL_CACHE_DIR = os.getenv("MODEL_CACHE_DIR")
os.environ["HF_HOME"] = MODEL_CACHE_DIR

# 設定 Faster-Whisper 的模型路徑
# 您的資料夾名稱是 "models--Systran--faster-whisper-large-v3"
# 這通常是 huggingface cache 的結構，但 faster-whisper 可以直接指定路徑
WHISPER_MODEL_PATH = os.path.join(MODEL_CACHE_DIR, "models--Systran--faster-whisper-large-v3")

print(f"📍 Model Root: {MODEL_CACHE_DIR}")
print(f"📍 Whisper Path: {WHISPER_MODEL_PATH}")

# 延遲 import
from faster_whisper import WhisperModel
from pyannote.audio import Pipeline

class PipelinePhase2:
    def __init__(self, device="cuda"):
        self.device = device
        self.compute_type = "float16" if torch.cuda.is_available() else "int8"
        
        # 檢查 HF_TOKEN
        if not os.getenv("HF_TOKEN"):
            print("⚠️ 警告: 未偵測到 HF_TOKEN，Pyannote 可能會報錯。")

    # --- Step 1: Whisper ---
    def run_whisper(self, audio_path, output_json_path):
        if os.path.exists(output_json_path):
            print(f"⏩ Whisper output exists, skipping.")
            return

        print(f"🎧 [Step 1] Running Whisper on {os.path.basename(audio_path)}...")
        
        # 這裡有兩個策略：
        # 1. 如果 D:\hf_models\models--Systran... 裡面是直接的模型檔 (config.json, model.bin)，直接讀取。
        # 2. 如果那是空的或結構不對，我們指回 D:\hf_models 讓它自動下載/驗證。
        
        try:
            # 嘗試直接讀取您現有的資料夾
            model = WhisperModel(
                WHISPER_MODEL_PATH, 
                device=self.device, 
                compute_type=self.compute_type,
                local_files_only=True # 強制不聯網，只讀本地
            )
            print("   (Loading from local path successfully)")
        except Exception as e:
            print(f"   ⚠️ Local load failed ({e}), falling back to standard loader...")
            # 如果失敗，改用標準讀取 (它會去 D:\hf_models 下載或找快取)
            model = WhisperModel(
                "large-v3", 
                device=self.device, 
                compute_type=self.compute_type,
                download_root=MODEL_CACHE_DIR 
            )

        segments, info = model.transcribe(
            audio_path,
            beam_size=5,
            word_timestamps=True,
            vad_filter=True,
            language="zh"
        )
        
        results = []
        for seg in segments:
            results.append({
                "start": seg.start,
                "end": seg.end,
                "text": seg.text,
                "words": [{"start": w.start, "end": w.end, "word": w.word} for w in seg.words]
            })
            
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        print(f"✅ Whisper done. Saved to {output_json_path}")
        del model
        torch.cuda.empty_cache()

    # --- Step 2: Pyannote ---
    def run_diarization(self, audio_path, output_json_path):
        if os.path.exists(output_json_path):
            print(f"⏩ Diarization output exists, skipping.")
            return

        print(f"🗣️ [Step 2] Running Pyannote on {os.path.basename(audio_path)}...")
        
        # Pyannote 的載入比較 tricky，它依賴 HF_HOME 環境變數
        # 我們在程式最上方已經設定 os.environ["HF_HOME"] = "D:\hf_models"
        
        hf_token = os.getenv("HF_TOKEN")
        try:
            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=hf_token,
                cache_dir=MODEL_CACHE_DIR # 明確指定 cache 目錄
            ).to(torch.device(self.device))
        except Exception as e:
            print(f"❌ Pyannote loading failed: {e}")
            print("請確認 D:\\hf_models 下是否有 'models--pyannote--speaker-diarization-3.1' 結構")
            return

        diarization = pipeline(audio_path)

        diar_segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            diar_segments.append({
                "start": turn.start,
                "end": turn.end,
                "speaker": speaker
            })
            
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(diar_segments, f, ensure_ascii=False, indent=2)

        print(f"✅ Diarization done. Saved to {output_json_path}")
        del pipeline
        torch.cuda.empty_cache()

    # --- Step 3: 邏輯對齊 (同前) ---
    def run_alignment(self, whisper_json, diar_json, final_output_path, chunk_offset_sec=0):
        print(f"🔗 [Step 3] Aligning text with speakers...")
        
        # 簡單檢查輸入檔是否存在
        if not os.path.exists(whisper_json) or not os.path.exists(diar_json):
            print("❌ Input JSONs missing. Please run Step 1 & 2 first.")
            return

        with open(whisper_json, 'r', encoding='utf-8') as f:
            w_segs = json.load(f)
        with open(diar_json, 'r', encoding='utf-8') as f:
            d_segs = json.load(f)
            
        aligned_data = []
        for idx, w in enumerate(w_segs):
            w_start = w["start"]
            w_end = w["end"]
            speaker_scores = {}
            for d in d_segs:
                inter_start = max(w_start, d["start"])
                inter_end = min(w_end, d["end"])
                if inter_end > inter_start:
                    duration = inter_end - inter_start
                    spk = d["speaker"]
                    speaker_scores[spk] = speaker_scores.get(spk, 0) + duration
            
            if speaker_scores:
                best_speaker = max(speaker_scores, key=speaker_scores.get)
            else:
                best_speaker = "Unknown"

            aligned_data.append({
                "id": f"chunk_{int(chunk_offset_sec)}_{idx}",
                "start": round(w_start + chunk_offset_sec, 2),
                "end": round(w_end + chunk_offset_sec, 2),
                "speaker": best_speaker,
                "text": w["text"].strip(),
                "flag": "review_needed" if best_speaker == "Unknown" else "auto"
            })
            
        with open(final_output_path, 'w', encoding='utf-8') as f:
            json.dump(aligned_data, f, ensure_ascii=False, indent=2)
        print(f"🎉 Final aligned data saved to {final_output_path}")

# --- 執行區塊 ---
if __name__ == "__main__":
    # 這裡請填入您想要處理的那個 WAV 檔案
    target_wav = "data/temp_chunks/chunk_1_0_531989.wav" 
    
    # 產生檔名
    base_name = os.path.splitext(target_wav)[0]
    json_whisper = f"{base_name}_whisper.json"
    json_diar = f"{base_name}_diar.json"
    json_final = f"{base_name}_aligned.json"
    
    # 解析 offset
    try:
        start_ms = int(base_name.split('_')[-2]) 
        offset_sec = start_ms / 1000.0
    except:
        offset_sec = 0

    processor = PipelinePhase2()
    
    # 依序執行
    processor.run_whisper(target_wav, json_whisper)
    processor.run_diarization(target_wav, json_diar)
    processor.run_alignment(json_whisper, json_diar, json_final, offset_sec)