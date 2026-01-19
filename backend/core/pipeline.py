import os
import json
import torch
import pathlib
import warnings
import gc
from dotenv import load_dotenv

# 引入配置
from core.config import config

# --- 1. 設定環境 ---
load_dotenv()
MODEL_ROOT = config.model_cache_dir
os.environ["HF_HOME"] = MODEL_ROOT
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# --- 2. 🛡️ RTX 5090 / PyTorch 2.8+ 終極白名單補丁 ---

print(f"🔧 Applying PyTorch {torch.__version__} security patches...")

try:
    # 匯入 Pyannote 任務定義模組
    import pyannote.audio.core.task
    from torch.torch_version import TorchVersion
    
    # 定義我們需要解鎖的類別名稱清單 (這是 Pyannote 模型的核心三巨頭)
    target_classes = ["Specifications", "Problem", "Resolution"]
    
    safe_list = [TorchVersion, pathlib.PosixPath, pathlib.WindowsPath]
    
    # 動態抓取 Pyannote 的類別
    for name in target_classes:
        if hasattr(pyannote.audio.core.task, name):
            cls = getattr(pyannote.audio.core.task, name)
            safe_list.append(cls)
            print(f"   -> Found and added to safelist: {name}")
    
    # 註冊白名單
    if hasattr(torch.serialization, "add_safe_globals"):
        torch.serialization.add_safe_globals(safe_list)
        print("✅ Safe globals registered successfully.")
        
except ImportError as e:
    print(f"⚠️ Patch warning: Could not import pyannote modules ({e})")
except Exception as e:
    print(f"⚠️ Patch warning: {e}")

# 再次強制 Patch torch.load (雙重保險)
original_load = torch.load
def permissive_load(*args, **kwargs):
    if 'weights_only' not in kwargs:
        kwargs['weights_only'] = False
    return original_load(*args, **kwargs)
torch.load = permissive_load

from typing import Optional
# --- 3. 匯入重型套件 ---
from faster_whisper import WhisperModel
from pyannote.audio import Pipeline

class PipelinePhase2:
    def __init__(self, device: Optional[str] = None):
        self.device = device or config.device
        self.compute_type = config.compute_type if torch.cuda.is_available() else "int8"
        
        if not config.hf_token:
            print("⚠️ 警告: 未偵測到 HF_TOKEN，Pyannote 可能會報錯。")

    # --- Step 1: Whisper ---
    def run_whisper(self, audio_path, output_json_path):
        if os.path.exists(output_json_path):
            print(f"⏩ Whisper output exists, skipping.")
            return

        print(f"🎧 [Step 1] Running Whisper on {os.path.basename(audio_path)}...")
        model = WhisperModel(
            config.whisper_model, 
            device=self.device, 
            compute_type=self.compute_type,
            download_root=MODEL_ROOT 
        )

        segments, info = model.transcribe(
            audio_path,
            beam_size=config.whisper_beam_size,
            word_timestamps=True,
            vad_filter=True,
            language=config.whisper_language
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

        # 徹底釋放記憶體的三連擊
        del model
        gc.collect() # 強制 Python 回收記憶體物件
        torch.cuda.empty_cache() # 強制 PyTorch 釋放 VRAM
        print("🧹 VRAM cleaned.")

    # --- Step 2: Pyannote ---
    def run_diarization(self, audio_path, output_json_path):
        if os.path.exists(output_json_path):
            print(f"⏩ Diarization output exists, skipping.")
            return

        print(f"🗣️ [Step 2] Running Pyannote on {os.path.basename(audio_path)}...")
        
        hf_token = config.hf_token
        try:
            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=hf_token,
                cache_dir=MODEL_ROOT
            ).to(torch.device(self.device))
            
            diarization = pipeline(audio_path)

        except Exception as e:
            print(f"❌ Pyannote loading failed: {e}")
            # 如果還缺什麼，顯示出來方便除錯
            import traceback
            traceback.print_exc()
            return

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

        # 徹底釋放記憶體的三連擊
        del pipeline
        gc.collect() # 強制 Python 回收記憶體物件
        torch.cuda.empty_cache() # 強制 PyTorch 釋放 VRAM
        print("🧹 VRAM cleaned.")
    # --- Step 3: 邏輯對齊 ---
    def run_alignment(self, whisper_json, diar_json, final_output_path, chunk_offset_sec=0):
        print(f"🔗 [Step 3] Aligning text with speakers...")
        
        if not os.path.exists(whisper_json) or not os.path.exists(diar_json):
            print("❌ Input JSONs missing. Step 2 failed.")
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
    target_wav = "data/temp_chunks/chunk_4_1606067_2171157.wav" 
    
    base_name = os.path.splitext(target_wav)[0]
    json_whisper = f"{base_name}_whisper.json"
    json_diar = f"{base_name}_diar.json"
    json_final = f"{base_name}_aligned.json"
    
    try:
        start_ms = int(base_name.split('_')[-2]) 
        offset_sec = start_ms / 1000.0
    except:
        offset_sec = 0

    processor = PipelinePhase2()
    
    processor.run_whisper(target_wav, json_whisper)
    processor.run_diarization(target_wav, json_diar)
    processor.run_alignment(json_whisper, json_diar, json_final, offset_sec)