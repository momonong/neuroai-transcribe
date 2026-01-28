import os
import json
import torch
import pathlib
import gc
import time
import sys
from typing import List, Dict

from .config import config

# --- RTX 5090 / PyTorch Patch (保留) ---
try:
    original_load = torch.load
    def permissive_load(*args, **kwargs):
        if 'weights_only' not in kwargs:
            kwargs['weights_only'] = False
        return original_load(*args, **kwargs)
    torch.load = permissive_load

    import pyannote.audio.core.task
    from torch.torch_version import TorchVersion
    target_classes = ["Specifications", "Problem", "Resolution"]
    safe_list = [TorchVersion, pathlib.PosixPath, pathlib.WindowsPath]
    for name in target_classes:
        if hasattr(pyannote.audio.core.task, name):
            cls = getattr(pyannote.audio.core.task, name)
            safe_list.append(cls)
    if hasattr(torch.serialization, "add_safe_globals"):
        torch.serialization.add_safe_globals(safe_list)
except ImportError:
    pass
except Exception as e:
    print(f"⚠️ Patch warning: {e}")

from faster_whisper import WhisperModel
from pyannote.audio import Pipeline

class PipelinePhase2:
    def __init__(self):
        self.device = config.device
        self.compute_type = config.compute_type

    # ==========================================
    # 🚀 核心改動：批次處理 Whisper
    # ==========================================
    def run_whisper_batch(self, tasks: List[Dict]):
        """
        一次性處理所有檔案的 Whisper 轉錄
        tasks: list of {'wav': path, 'json': path}
        """
        print(f"\n🎧 [Batch Whisper] Starting batch for {len(tasks)} files...", flush=True)
        
        # 過濾掉已經跑過的
        todo_tasks = [t for t in tasks if not os.path.exists(t['json'])]
        if not todo_tasks:
            print("   ⏩ All Whisper tasks completed. Skipping.", flush=True)
            return

        model = None
        try:
            print(f"   🔄 Loading Whisper Model ({config.whisper_model})...", flush=True)
            model = WhisperModel(
                config.whisper_model, 
                device=self.device, 
                compute_type=self.compute_type,
                download_root=config.model_cache_dir 
            )

            for idx, task in enumerate(todo_tasks):
                wav_path = task['wav']
                json_path = task['json']
                print(f"   [{idx+1}/{len(todo_tasks)}] Transcribing: {os.path.basename(wav_path)}", flush=True)
                
                segments, info = model.transcribe(
                    wav_path,
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
                        "words": [{"start": w.start, "end": w.end, "word": w.word} for w in seg.words] if seg.words else []
                    })
                
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)

        except Exception as e:
            print(f"   ❌ Batch Whisper Failed: {e}", flush=True)
            raise e
        finally:
            if model:
                del model
            self._clear_gpu()
            print("   🧹 Whisper Model Unloaded.", flush=True)

    # ==========================================
    # 🚀 核心改動：批次處理 Pyannote
    # ==========================================
    def run_diarization_batch(self, tasks: List[Dict]):
        """
        一次性處理所有檔案的 Pyannote 分離
        tasks: list of {'wav': path, 'json': path}
        """
        print(f"\n🗣️ [Batch Diarization] Starting batch for {len(tasks)} files...", flush=True)

        todo_tasks = [t for t in tasks if not os.path.exists(t['json'])]
        if not todo_tasks:
            print("   ⏩ All Diarization tasks completed. Skipping.", flush=True)
            return

        pipeline = None
        try:
            print(f"   🔄 Loading Pyannote Model...", flush=True)
            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=config.hf_token,
                cache_dir=config.model_cache_dir
            ).to(torch.device(self.device))

            for idx, task in enumerate(todo_tasks):
                wav_path = task['wav']
                json_path = task['json']
                print(f"   [{idx+1}/{len(todo_tasks)}] Diarizing: {os.path.basename(wav_path)}", flush=True)
                
                diarization = pipeline(wav_path)

                diar_segments = []
                for turn, _, speaker in diarization.itertracks(yield_label=True):
                    diar_segments.append({
                        "start": turn.start,
                        "end": turn.end,
                        "speaker": speaker
                    })
                
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(diar_segments, f, ensure_ascii=False, indent=2)

        except Exception as e:
            print(f"   ❌ Batch Diarization Failed: {e}", flush=True)
            raise e
        finally:
            if pipeline:
                del pipeline
            self._clear_gpu()
            print("   🧹 Pyannote Model Unloaded.", flush=True)

    # Alignment 其實不需要批次 (因為它是 CPU 快算)，但為了統一介面可以留著
    def run_alignment(self, whisper_json, diar_json, final_output_path, chunk_offset_sec=0):
        # ... (這裡保持原樣，不需要改) ...
        try:
            if not os.path.exists(whisper_json) or not os.path.exists(diar_json):
                # 如果前兩個步驟失敗，這步直接跳過，不報錯，避免 crash
                print(f"   ⚠️ Missing input for alignment: {os.path.basename(final_output_path)}")
                return

            with open(whisper_json, 'r', encoding='utf-8') as f: w_segs = json.load(f)
            with open(diar_json, 'r', encoding='utf-8') as f: d_segs = json.load(f)
                
            aligned_data = []
            for idx, w in enumerate(w_segs):
                w_start = w["start"]
                w_end = w["end"]
                speaker_scores = {}
                for d in d_segs:
                    inter_start = max(w_start, d["start"])
                    inter_end = min(w_end, d["end"])
                    if inter_end > inter_start:
                        spk = d["speaker"]
                        speaker_scores[spk] = speaker_scores.get(spk, 0) + (inter_end - inter_start)
                
                best_speaker = max(speaker_scores, key=speaker_scores.get) if speaker_scores else "Unknown"
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
                
        except Exception as e:
            print(f"   ❌ Alignment Failed: {e}", flush=True)

    def _clear_gpu(self):
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
        time.sleep(1) # 給 OS 一點時間回收