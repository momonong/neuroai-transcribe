from __future__ import annotations

import gc
import json
import os
import pathlib
import subprocess
import sys
import time
from typing import Dict, List

import torch

try:
    from opencc import OpenCC  # type: ignore
except Exception:
    OpenCC = None  # type: ignore[assignment]

from core.config import config
from core.diarization_placeholders import write_placeholder_diar_from_whisper


def _patch_torch_load_and_safe_globals() -> None:
    """
    針對 PyTorch 2.6+ 的安全載入限制做相容修補。

    注意：此 patch 必須在需要載入 pyannote checkpoint 的情境下可用；
    若環境未安裝 pyannote，這段會被 try/except 吞掉並繼續。
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
        self.cc = OpenCC("s2twp") if OpenCC is not None else None

    def _clear_gpu(self):
        """強制清理 GPU 資源；若清理時發生錯誤僅記錄不拋出，避免 process 直接結束。"""
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
            f"\n🎧 [Batch Whisper] Starting batch for {len(tasks)} files (one subprocess per chunk)...",
            flush=True,
        )

        todo_tasks = [t for t in tasks if not os.path.exists(t["json"])]
        if not todo_tasks:
            print("   ⏩ All Whisper tasks completed. Skipping.", flush=True)
            return

        project_root = str(config.project_root)
        cmd_base = [sys.executable, "-m", "core.scripts.whisper_one_chunk"]
        timeout_sec = 600  # 單一 chunk 最長 10 分鐘

        for idx, task in enumerate(todo_tasks):
            wav_path = task["wav"]
            json_path = task["json"]
            print(
                f"   [{idx+1}/{len(todo_tasks)}] Transcribing: {os.path.basename(wav_path)}",
                flush=True,
            )
            success = False
            for attempt in range(2):
                try:
                    r = subprocess.run(
                        cmd_base + [wav_path, json_path],
                        cwd=project_root,
                        env=os.environ.copy(),
                        timeout=timeout_sec,
                        capture_output=True,
                        text=True,
                    )
                    if r.returncode == 0:
                        if r.stderr:
                            print(r.stderr, flush=True)
                        success = True
                        break
                    # 子行程可能在寫完 json 後於收尾時崩潰（如 Windows 3221226505），若輸出已存在則視為成功
                    if os.path.exists(json_path) and os.path.getsize(json_path) > 0:
                        try:
                            with open(json_path, encoding="utf-8") as f:
                                json.load(f)
                            success = True
                            print("   ✓ 輸出已寫入（子行程收尾異常，視為成功）", flush=True)
                            break
                        except Exception:
                            pass
                    print(f"   ⚠️ 子行程 exit code {r.returncode}", flush=True)
                    if r.stderr:
                        print(r.stderr, flush=True)
                except subprocess.TimeoutExpired:
                    print(f"   ⚠️ 逾時 ({timeout_sec}s)，重試 {attempt+1}/2", flush=True)
                except Exception as e:
                    print(f"   ⚠️ 執行失敗: {e}", flush=True)
            if not success:
                print(f"   ❌ 跳過（無法完成）: {os.path.basename(wav_path)}", flush=True)
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
            from core.scripts.model.whisper_bilstm_diarization import (
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

