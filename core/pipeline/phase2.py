from __future__ import annotations

import gc
import json
import os
import pathlib
import requests
import sys
import time
from typing import Dict, List

import torch

from core.config import config
from core.diarization_placeholders import write_placeholder_diar_from_whisper


def _patch_torch_load_and_safe_globals() -> None:
    """
    針對 PyTorch 2.6+ 的安全載入限制做相容修補。
    """
    try:
        original_load = torch.load

        def permissive_load(*args, **kwargs):
            if "weights_only" not in kwargs:
                kwargs["weights_only"] = False
            return original_load(*args, **kwargs)

        torch.load = permissive_load  # type: ignore[assignment]

        import pyannote.audio.core.task  # noqa: F401
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


class PipelinePhase2:
    def __init__(self):
        _patch_torch_load_and_safe_globals()
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.compute_type = "float16" if self.device == "cuda" else "int8"
        self.whisper_model = None
        self.diarization_pipeline = None
        # Whisper 服務化後，這裡不需要 OpenCC

    def _clear_gpu(self):
        """強制清理 GPU 資源"""
        try:
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
            time.sleep(0.5)
        except Exception as e:
            print(f"   ⚠️ _clear_gpu 時發生錯誤（已忽略）: {e}", flush=True)

    def run_whisper_batch(self, tasks: List[Dict]):
        print(
            f"\n🎧 [Batch Whisper] Calling Whisper Service for {len(tasks)} files...",
            flush=True,
        )

        todo_tasks = [t for t in tasks if not os.path.exists(t["json"])]
        if not todo_tasks:
            print("   ⏩ All Whisper tasks completed. Skipping.", flush=True)
            return

        # 取得 Whisper 服務網址，預設為 docker compose 中的服務名
        whisper_url = os.getenv("WHISPER_SERVICE_URL", "http://whisper:8002/transcribe")

        for idx, task in enumerate(todo_tasks):
            wav_path = task["wav"]
            json_path = task["json"]
            print(
                f"   [{idx+1}/{len(todo_tasks)}] Transcribing via API: {os.path.basename(wav_path)}",
                flush=True,
            )
            
            success = False
            error_msg = ""
            for attempt in range(2):
                try:
                    # 注意：這裡傳遞的是容器內路徑，Whisper 服務必須掛載相同的 data 卷
                    resp = requests.post(
                        whisper_url, 
                        json={"wav_path": str(wav_path)},
                        timeout=600
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("ok"):
                            with open(json_path, "w", encoding="utf-8") as f:
                                json.dump(data["results"], f, ensure_ascii=False, indent=2)
                            success = True
                            break
                        else:
                            error_msg = data.get("message", "Unknown error from service")
                    else:
                        error_msg = f"HTTP {resp.status_code}: {resp.text}"
                except Exception as e:
                    error_msg = str(e)
                
                print(f"   ⚠️ Attempt {attempt+1} failed: {error_msg}")
                time.sleep(2)

            if not success:
                print(f"   ❌ 嚴重錯誤：API 轉錄失敗 {os.path.basename(wav_path)}", flush=True)
                raise RuntimeError(f"Whisper API failed: {error_msg}")
                
        print("   🧹 Batch Whisper 結束.", flush=True)

    def run_diarization_batch(self, tasks: List[Dict]):
        backend = config.diarization_backend
        print(
            f"\n🗣️ [Batch Diarization] backend={backend}, {len(tasks)} file(s)...",
            flush=True,
        )

        todo_tasks = [t for t in tasks if not os.path.exists(t["json"])]
        if not todo_tasks:
            print("   ⏩ All Diarization tasks completed. Skipping.", flush=True)
            return

        if backend == "pyannote":
            self._run_diarization_pyannote(todo_tasks)
        elif backend == "placeholder":
            self._run_diarization_placeholder(todo_tasks)
        elif backend == "whisper_bilstm":
            from core.speaker_bilstm.diarization_wrapper import (
                run_whisper_bilstm_diarization_batch,
            )

            run_whisper_bilstm_diarization_batch(
                todo_tasks,
                device=self.device,
                checkpoint_path=config.speaker_model_path,
            )
        else:
            raise ValueError(f"Unknown diarization backend: {backend}")

    def _run_diarization_pyannote(self, todo_tasks: List[Dict]):
        from pyannote.audio import Pipeline

        try:
            print("   🔄 Loading Pyannote Model...", flush=True)
            self.diarization_pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=config.hf_token,
                cache_dir=config.model_cache_dir,
            ).to(torch.device(self.device))

            for idx, task in enumerate(todo_tasks):
                wav_path = task["wav"]
                json_path = task["json"]
                print(
                    f"   [{idx+1}/{len(todo_tasks)}] Diarizing: {os.path.basename(wav_path)}",
                    flush=True,
                )

                diarization = self.diarization_pipeline(wav_path)

                diar_segments = []
                for turn, _, speaker in diarization.itertracks(yield_label=True):
                    diar_segments.append(
                        {
                            "start": turn.start,
                            "end": turn.end,
                            "speaker": speaker,
                        }
                    )

                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(diar_segments, f, ensure_ascii=False, indent=2)

                is_last = idx == len(todo_tasks) - 1
                if not is_last:
                    self._clear_gpu()

        except Exception as e:
            print(f"   ❌ Batch Diarization Failed: {e}", flush=True)
            raise e
        finally:
            try:
                if self.diarization_pipeline:
                    del self.diarization_pipeline
                    self.diarization_pipeline = None
                self._clear_gpu()
                print("   🧹 Pyannote Model Unloaded.", flush=True)
            except Exception as e:
                print(
                    f"   ⚠️ Diarization 收尾清理時發生錯誤（已忽略）: {e}",
                    flush=True,
                )

    def _run_diarization_placeholder(self, todo_tasks: List[Dict]):
        label = config.speaker_placeholder_label
        for idx, task in enumerate(todo_tasks):
            wav_path = task["wav"]
            json_path = task["json"]
            print(
                f"   [{idx+1}/{len(todo_tasks)}] Placeholder diar: {os.path.basename(wav_path)}",
                flush=True,
            )
            ok = write_placeholder_diar_from_whisper(wav_path, json_path, speaker=label)
            if not ok:
                from core.diarization_placeholders import whisper_json_path_for_wav

                wj = whisper_json_path_for_wav(wav_path)
                raise RuntimeError(
                    f"placeholder diar 需要先有 Whisper 輸出: {wj}（請確認已跑完 Whisper）"
                )

    def run_alignment(self, whisper_json, diar_json, final_output_path, chunk_offset_sec=0):
        try:
            if not os.path.exists(whisper_json) or not os.path.exists(diar_json):
                return

            with open(whisper_json, "r", encoding="utf-8") as f:
                w_segs = json.load(f)
            with open(diar_json, "r", encoding="utf-8") as f:
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
                        spk = d["speaker"]
                        speaker_scores[spk] = speaker_scores.get(spk, 0) + (
                            inter_end - inter_start
                        )

                best_speaker = (
                    max(speaker_scores, key=speaker_scores.get)
                    if speaker_scores
                    else "Unknown"
                )
                aligned_data.append(
                    {
                        "id": f"chunk_{int(chunk_offset_sec)}_{idx}",
                        "start": round(w_start + chunk_offset_sec, 3),
                        "end": round(w_end + chunk_offset_sec, 3),
                        "speaker": best_speaker,
                        "text": w["text"].strip(),
                        "flag": "review_needed" if best_speaker == "Unknown" else "auto",
                    }
                )

            with open(final_output_path, "w", encoding="utf-8") as f:
                json.dump(aligned_data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            print(f"   ❌ Alignment Failed: {e}", flush=True)
