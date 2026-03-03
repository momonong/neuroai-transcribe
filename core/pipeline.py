import os
import json
import torch
import gc
import time
import pathlib
from typing import List, Dict
from opencc import OpenCC

from .config import config


try:
    # 強制覆寫 torch.load，預設 weights_only=False
    original_load = torch.load
    def permissive_load(*args, **kwargs):
        if 'weights_only' not in kwargs:
            kwargs['weights_only'] = False
        return original_load(*args, **kwargs)
    torch.load = permissive_load

    # 加入安全白名單 (防止 Diarization 載入失敗)
    import pyannote.audio.core.task
    from torch.torch_version import TorchVersion
    
    safe_list = [TorchVersion, pathlib.PosixPath, pathlib.WindowsPath]
    target_classes = ["Specifications", "Problem", "Resolution"]
    for name in target_classes:
        if hasattr(pyannote.audio.core.task, name):
            safe_list.append(getattr(pyannote.audio.core.task, name))
            
    if hasattr(torch.serialization, "add_safe_globals"):
        torch.serialization.add_safe_globals(safe_list)
except Exception as e:
    print(f"⚠️ Warning: Patching torch.load failed: {e}")

# 正常 import
from faster_whisper import WhisperModel
from pyannote.audio import Pipeline

class PipelinePhase2:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.compute_type = "float16" if self.device == "cuda" else "int8"
        self.whisper_model = None
        self.diarization_pipeline = None
        self.cc = OpenCC('s2twp')

    def _clear_gpu(self):
        """強制清理 GPU 資源"""
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
        time.sleep(1)

    def run_whisper_batch(self, tasks: List[Dict]):
        print(f"\n🎧 [Batch Whisper] Starting batch for {len(tasks)} files...", flush=True)
        
        todo_tasks = [t for t in tasks if not os.path.exists(t['json'])]
        if not todo_tasks:
            print("   ⏩ All Whisper tasks completed. Skipping.", flush=True)
            return

        try:
            print(f"   🔄 Loading Whisper Model ({config.whisper_model})...", flush=True)
            self.whisper_model = WhisperModel(
                config.whisper_model, 
                device=self.device, 
                compute_type=self.compute_type,
                download_root=config.model_cache_dir,
                cpu_threads=4,
                num_workers=1
            )

            for idx, task in enumerate(todo_tasks):
                wav_path = task['wav']
                json_path = task['json']
                print(f"   [{idx+1}/{len(todo_tasks)}] Transcribing: {os.path.basename(wav_path)}", flush=True)
                
                segments, info = self.whisper_model.transcribe(
                    wav_path,
                    beam_size=config.whisper_beam_size,
                    word_timestamps=True,
                    vad_filter=True
                )
                
                results = []
                for seg in list(segments): 
                    text_traditional = self.cc.convert(seg.text.strip())
                    words_list = []
                    if seg.words:
                        for w in seg.words:
                            words_list.append({
                                "start": w.start, 
                                "end": w.end, 
                                "word": self.cc.convert(w.word)
                            })

                    results.append({
                        "start": seg.start,
                        "end": seg.end,
                        "text": text_traditional,
                        "words": words_list
                    })
                
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)
                
                self._clear_gpu()

        except Exception as e:
            print(f"   ❌ Batch Whisper Failed: {e}", flush=True)
        finally:
            if self.whisper_model:
                del self.whisper_model
                self.whisper_model = None
            self._clear_gpu()
            print("   🧹 Whisper Model Unloaded.", flush=True)

    def run_diarization_batch(self, tasks: List[Dict]):
        print(f"\n🗣️ [Batch Diarization] Starting batch for {len(tasks)} files...", flush=True)

        todo_tasks = [t for t in tasks if not os.path.exists(t['json'])]
        if not todo_tasks:
            print("   ⏩ All Diarization tasks completed. Skipping.", flush=True)
            return

        try:
            print(f"   🔄 Loading Pyannote Model...", flush=True)
            self.diarization_pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=config.hf_token,
                cache_dir=config.model_cache_dir
            ).to(torch.device(self.device))

            for idx, task in enumerate(todo_tasks):
                wav_path = task['wav']
                json_path = task['json']
                print(f"   [{idx+1}/{len(todo_tasks)}] Diarizing: {os.path.basename(wav_path)}", flush=True)
                
                diarization = self.diarization_pipeline(wav_path)

                diar_segments = []
                for turn, _, speaker in diarization.itertracks(yield_label=True):
                    diar_segments.append({
                        "start": turn.start,
                        "end": turn.end,
                        "speaker": speaker
                    })
                
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(diar_segments, f, ensure_ascii=False, indent=2)
                
                self._clear_gpu()

        except Exception as e:
            print(f"   ❌ Batch Diarization Failed: {e}", flush=True)
            raise e
        finally:
            if self.diarization_pipeline:
                del self.diarization_pipeline
                self.diarization_pipeline = None
            self._clear_gpu()
            print("   🧹 Pyannote Model Unloaded.", flush=True)

    def run_alignment(self, whisper_json, diar_json, final_output_path, chunk_offset_sec=0):
        try:
            if not os.path.exists(whisper_json) or not os.path.exists(diar_json):
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
                    "start": round(w_start + chunk_offset_sec, 3),
                    "end": round(w_end + chunk_offset_sec, 3),
                    "speaker": best_speaker,
                    "text": w["text"].strip(),
                    "flag": "review_needed" if best_speaker == "Unknown" else "auto"
                })
                
            with open(final_output_path, 'w', encoding='utf-8') as f:
                json.dump(aligned_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"   ❌ Alignment Failed: {e}", flush=True)
