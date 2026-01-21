import os
import glob
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
        
        # 檢查音訊檔案大小，給出預估時間
        try:
            file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
            estimated_minutes = file_size_mb / 10  # 粗略估計：每 10MB 約需 1 分鐘
            print(f"   📊 檔案大小: {file_size_mb:.1f}MB, 預估處理時間: {estimated_minutes:.1f} 分鐘")
        except:
            pass
        
        try:
            model = WhisperModel(
                config.whisper_model, 
                device=self.device, 
                compute_type=self.compute_type,
                download_root=MODEL_ROOT 
            )

            print(f"   🔄 開始轉錄... (這可能需要幾分鐘)")
            segments, info = model.transcribe(
                audio_path,
                beam_size=config.whisper_beam_size,
                word_timestamps=True,
                vad_filter=True,
                language=config.whisper_language
            )
            
            print(f"   📝 處理轉錄結果...")
            results = []
            segment_count = 0
            
            for seg in segments:
                results.append({
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text,
                    "words": [{"start": w.start, "end": w.end, "word": w.word} for w in seg.words] if seg.words else []
                })
                segment_count += 1
                
                # 每處理 50 個片段顯示一次進度
                if segment_count % 50 == 0:
                    print(f"   📊 已處理 {segment_count} 個片段...")
            
            print(f"   💾 儲存結果... (共 {len(results)} 個片段)")
            with open(output_json_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            
            print(f"✅ Whisper done. Saved to {output_json_path}")

        except Exception as e:
            print(f"❌ Whisper 處理失敗: {e}")
            # 如果有部分結果，嘗試儲存
            if 'results' in locals() and results:
                print(f"   🔄 嘗試儲存部分結果...")
                try:
                    with open(output_json_path, 'w', encoding='utf-8') as f:
                        json.dump(results, f, ensure_ascii=False, indent=2)
                    print(f"   ✅ 部分結果已儲存")
                except:
                    pass
            raise
        finally:
            # 徹底釋放記憶體的三連擊
            if 'model' in locals():
                del model
            gc.collect() # 強制 Python 回收記憶體物件
            if torch.cuda.is_available():
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
            print(f"   🔄 載入 Diarization 模型...")
            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=hf_token,
                cache_dir=MODEL_ROOT
            ).to(torch.device(self.device))
            
            print(f"   🔄 執行說話者分離... (這可能需要幾分鐘)")
            diarization = pipeline(audio_path)

        except Exception as e:
            print(f"❌ Pyannote loading failed: {e}")
            # 如果還缺什麼，顯示出來方便除錯
            import traceback
            traceback.print_exc()
            return

        try:
            print(f"   📝 處理分離結果...")
            diar_segments = []
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                diar_segments.append({
                    "start": turn.start,
                    "end": turn.end,
                    "speaker": speaker
                })
            
            print(f"   💾 儲存結果... (共 {len(diar_segments)} 個說話片段)")
            with open(output_json_path, 'w', encoding='utf-8') as f:
                json.dump(diar_segments, f, ensure_ascii=False, indent=2)

            print(f"✅ Diarization done. Saved to {output_json_path}")

        except Exception as e:
            print(f"❌ Diarization 結果處理失敗: {e}")
            raise
        finally:
            # 徹底釋放記憶體的三連擊
            if 'pipeline' in locals():
                del pipeline
            gc.collect() # 強制 Python 回收記憶體物件
            if torch.cuda.is_available():
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
    # ==========================================
    # 1. 設定要處理的案例資料夾
    # ==========================================
    # 從環境變數讀取案例名稱，或使用預設值
    case_name = os.getenv("CASE_NAME")
    project_folder = f"data/{case_name}"
    
    # 檢查資料夾是否存在
    if not os.path.exists(project_folder):
        print(f"❌ 錯誤: 找不到案例資料夾 {project_folder}")
        print("請確認案例名稱是否正確，或設定 CASE_NAME 環境變數")
        exit(1)
    
    print(f"🚀 Initialize AI Models...")
    print(f"📂 Target folder: {project_folder}")
    
    # 注意：模型在此初始化，避免迴圈內重複載入，節省大量時間與記憶體
    processor = PipelinePhase2()

    # ==========================================
    # 2. 自動掃描該資料夾下的所有 Chunk wav 檔
    # ==========================================
    search_pattern = os.path.join(project_folder, "chunk_*.wav")
    wav_files = glob.glob(search_pattern)
    
    if not wav_files:
        print(f"⚠️ 警告: 在 {project_folder} 中找不到任何 chunk_*.wav 檔案")
        print("請確認是否已經執行過音訊切分步驟")
        exit(1)
    
    # 排序檔案 (讓處理順序依照 chunk_1, chunk_2... 進行)
    # 這裡用了一個小技巧：依照檔名中的數字排序，避免 1, 10, 2 的順序問題
    try:
        wav_files.sort(key=lambda x: int(os.path.basename(x).split('_')[1]))
    except:
        wav_files.sort() # 如果檔名格式不標準，就用普通排序

    print(f"📂 Found {len(wav_files)} chunks in: {project_folder}")
    for wav_file in wav_files:
        print(f"   - {os.path.basename(wav_file)}")
    print("=========================================")

    # ==========================================
    # 3. 批次執行 Pipeline
    # ==========================================
    success_count = 0
    error_count = 0
    
    for target_wav in wav_files:
        filename = os.path.basename(target_wav)
        print(f"\n🔄 Processing: {filename}")
        
        # 準備輸出的 JSON 檔名 (全部放在同一層資料夾)
        base_name_path = os.path.splitext(target_wav)[0]
        json_whisper = f"{base_name_path}_whisper.json"
        json_diar = f"{base_name_path}_diar.json"
        json_final = f"{base_name_path}_aligned.json"
        
        # ---------------------------------------
        # 解析 Offset (時間偏移量)
        # ---------------------------------------
        # 檔名格式假設: chunk_{index}_{start_ms}_{end_ms}.wav
        # 例如: chunk_2_531989_1100278.wav -> start_ms = 531989
        try:
            # 去除副檔名 -> chunk_2_531989_1100278
            # split('_') -> ['chunk', '2', '531989', '1100278']
            # 取倒數第二個 [-2] -> 531989
            parts = os.path.splitext(filename)[0].split('_')
            if len(parts) >= 4:  # 確保有足夠的部分
                start_ms = int(parts[-2])
                offset_sec = start_ms / 1000.0
                print(f"   ⏱️ Offset detected: {offset_sec}s (Start: {start_ms}ms)")
            else:
                print(f"   ⚠️ Warning: Unexpected filename format, using offset 0")
                offset_sec = 0.0
        except Exception as e:
            print(f"   ⚠️ Warning: Could not parse time from filename, default offset to 0. ({e})")
            offset_sec = 0.0

        # ---------------------------------------
        # 執行 AI 處理
        # ---------------------------------------
        try:
            # 1. Whisper 轉錄
            if not os.path.exists(json_whisper):
                processor.run_whisper(target_wav, json_whisper)
            else:
                print("   ⏭️ Whisper output exists, skipping...")

            # 2. Pyannote 說話者分理
            if not os.path.exists(json_diar):
                processor.run_diarization(target_wav, json_diar)
            else:
                print("   ⏭️ Diarization output exists, skipping...")

            # 3. 強制執行 Alignment (因為這步最快，且通常需要重新計算 offset)
            processor.run_alignment(json_whisper, json_diar, json_final, offset_sec)
            
            print(f"   ✅ Done: {filename}")
            success_count += 1
            
        except Exception as e:
            print(f"   ❌ Error processing {filename}: {e}")
            import traceback
            traceback.print_exc()
            error_count += 1

    print(f"\n🎉 Processing completed!")
    print(f"   ✅ Success: {success_count} files")
    print(f"   ❌ Errors: {error_count} files")