import os
import json
import sys
from pathlib import Path
import time
import traceback

# Add project root to sys.path to allow importing core and shared modules
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from typing import Optional, List, Dict

# 執行時需將專案根目錄加入 PYTHONPATH（或 pip install -e .），以便 import core

from core.config import config
from shared.file_manager import file_manager
from core.split import SmartAudioSplitter
from core.pipeline import PipelinePhase2
from core.stitch import run_stitching_logic, aligned_to_stitch_shape
from core.flag import run_anomaly_detector

_DEBUG_LOG_PATH = "debug-341068.log"


def _dbg_log(*, hypothesis_id: str, message: str, data: dict):
    # #region agent log
    try:
        payload = {
            "sessionId": "341068",
            "runId": "pre-fix",
            "hypothesisId": hypothesis_id,
            "location": "core/run_pipeline.py",
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion


class NeuroAIPipeline:
    def __init__(self):
        self.processor = PipelinePhase2()

    def run(
        self,
        video_path: str,
        case_name: Optional[str] = None,
        *,
        force_reprocess: bool = False,
        skip_stitch: Optional[bool] = None,
    ) -> Optional[str]:
        _dbg_log(
            hypothesis_id="H0",
            message="pipeline_run_enter",
            data={
                "video_path": str(video_path),
                "case_name_in": case_name,
                "force_reprocess": bool(force_reprocess),
                "skip_stitch_arg": skip_stitch,
                "env_DIARIZATION_BACKEND": os.getenv("DIARIZATION_BACKEND"),
                "config_diarization_backend": getattr(config, "diarization_backend", None),
            },
        )
        if case_name is None:
            inferred = file_manager.infer_case_name_from_video_path(video_path)
            if inferred:
                case_name = inferred
                print(f" [Pipeline] 由路徑推斷案例名稱: {case_name} (data/.../source/...)")

        case_name = file_manager.create_case(video_path, case_name)
        print(f" [Pipeline] Start: {case_name}")

        use_no_stitch = config.skip_stitch if skip_stitch is None else skip_stitch
        _dbg_log(
            hypothesis_id="H2",
            message="resolved_skip_stitch",
            data={"use_no_stitch": bool(use_no_stitch)},
        )
        if use_no_stitch:
            print(" [Pipeline] No-Stitch 模式：aligned 逐段直通，不做規則併句")

        if force_reprocess:
            n = file_manager.clear_intermediate(case_name)
            print(f" [Pipeline] --force：已清空 intermediate（{n} 個項目）")
            _dbg_log(
                hypothesis_id="H3",
                message="force_clear_intermediate",
                data={"cleared_items": int(n), "case_name": case_name},
            )
        
        file_manager.save_status(case_name, "Start", 0, "Initializing...")

        try:
            file_manager.save_status(case_name, "Splitting", 10, "Splitting audio...")
            chunk_metadata = self._step_1_split(video_path, case_name)
            _dbg_log(
                hypothesis_id="H1",
                message="after_split",
                data={
                    "chunk_count": len(chunk_metadata) if chunk_metadata else 0,
                    "case_name": case_name,
                },
            )
            if not chunk_metadata: return None

            self._step_2_process(chunk_metadata, case_name)
            _dbg_log(
                hypothesis_id="H1",
                message="after_phase2",
                data={"chunk_count": len(chunk_metadata), "case_name": case_name},
            )
            
            file_manager.save_status(
                case_name,
                "Refining",
                80,
                "Flagging (no stitch)..."
                if use_no_stitch
                else "Rule-based Stitching and Flagging...",
            )
            final_data = self._step_3_4_process_per_chunk(
                chunk_metadata, case_name, skip_stitch=use_no_stitch
            )
            _dbg_log(
                hypothesis_id="H4",
                message="after_phase3_4",
                data={
                    "final_segment_count": len(final_data) if isinstance(final_data, list) else None,
                    "case_name": case_name,
                },
            )

            output_path = file_manager.get_output_file_path(case_name, "transcript.json")
            file_manager.save_json(final_data, output_path, backup=True)
            
            print(f"\n✅ [Pipeline] Complete! Output: {output_path}")
            
            file_manager.save_status(case_name, "Done", 100, "Pipeline Completed Successfully")
            return str(output_path)

        except Exception as e:
            print(f"\n❌ [Pipeline] Failed: {e}")
            _dbg_log(
                hypothesis_id="H5",
                message="pipeline_failed_exception",
                data={
                    "case_name": case_name,
                    "exc_type": type(e).__name__,
                    "exc_message": str(e),
                    "traceback": traceback.format_exc(limit=50),
                },
            )
            file_manager.save_status(case_name, "Error", -1, str(e))
            return None

    def _step_1_split(self, video_path: str, case_name: str) -> List[Dict]:
        print("\n --- Phase 1: Audio Splitting ---")
        inter_dir = file_manager.get_intermediate_dir(case_name)
        splitter = SmartAudioSplitter(output_dir=str(inter_dir))
        return splitter.split_audio(video_path, num_chunks=config.default_num_chunks)

    def _step_2_process(self, chunk_metadata: List[Dict], case_name: str):
        print("\n --- Phase 2: Batch Processing ---")
        inter_dir = file_manager.get_intermediate_dir(case_name)
        
        whisper_tasks = []
        diar_tasks = []
        align_tasks = []
        for meta in chunk_metadata:
            wav_path = meta['file_path'] 
            base = os.path.splitext(os.path.basename(wav_path))[0]
            offset = meta['start_time_ms'] / 1000.0
            
            j_w = inter_dir / f"{base}_whisper.json"
            j_d = inter_dir / f"{base}_diar.json"
            j_a = inter_dir / f"{base}_aligned.json"
            
            whisper_tasks.append({'wav': str(wav_path), 'json': str(j_w)})
            diar_tasks.append({'wav': str(wav_path), 'json': str(j_d)})
            
            align_tasks.append({'w': str(j_w), 'd': str(j_d), 'out': str(j_a), 'offset': offset})

        file_manager.save_status(case_name, "Whisper", 20, "Running Whisper ASR...")
        self.processor.run_whisper_batch(whisper_tasks)
        
        file_manager.save_status(
            case_name,
            "Diarization",
            50,
            f"Speaker diarization ({config.diarization_backend})...",
        )
        self.processor.run_diarization_batch(diar_tasks)
        
        file_manager.save_status(case_name, "Alignment", 70, "Aligning segments...")
        print("\n [Batch Alignment]...")
        for t in align_tasks:
            self.processor.run_alignment(t['w'], t['d'], t['out'], t['offset'])

    def _step_3_4_process_per_chunk(
        self, chunk_metadata: List[Dict], case_name: str, *, skip_stitch: bool
    ) -> List[Dict]:
        phase_title = (
            "Phase 3 & 4: Passthrough -> Flag"
            if skip_stitch
            else "Phase 3 & 4: RuleStitch -> Flag"
        )
        print(f"\n --- {phase_title} ---")
        inter_dir = file_manager.get_intermediate_dir(case_name)
        final_results = []

        for i, meta in enumerate(chunk_metadata):
            wav = meta['file_path']
            base = os.path.splitext(os.path.basename(wav))[0]
            
            aligned = inter_dir / f"{base}_aligned.json"
            stitched = inter_dir / f"{base}_stitched.json"
            flagged = inter_dir / f"{base}_flagged_for_human.json"
            
            print(f"   Processing Chunk {i+1}: {base}")

            if flagged.exists():
                print("       Found flagged file.")
                final_results.extend(file_manager.load_json(flagged))
                continue

            stitched_data = []
            if aligned.exists():
                raw = file_manager.load_json(aligned)
                if raw:
                    if skip_stitch:
                        print("       No-Stitch: aligned -> stitch-shaped passthrough")
                        stitched_data = aligned_to_stitch_shape(raw)
                        file_manager.save_json(stitched_data, stitched, backup=False)
                    elif stitched.exists():
                        print("       Found stitched file.")
                        stitched_data = file_manager.load_json(stitched)
                    else:
                        print("       Rule-based Stitching...")
                        try:
                            stitched_data = run_stitching_logic(raw)
                            file_manager.save_json(stitched_data, stitched, backup=False)
                        except Exception as e:
                            print(f"      ❌ Stitch failed: {e}")
                            stitched_data = raw

            if stitched_data:
                print("       Flagging...")
                flagged_data = run_anomaly_detector(stitched_data)
                file_manager.save_json(flagged_data, flagged, backup=False)
                final_results.extend(flagged_data)

        return final_results

def run_pipeline(
    video_path: str,
    case_name: Optional[str] = None,
    *,
    force_reprocess: bool = False,
    skip_stitch: Optional[bool] = None,
):
    pipeline = NeuroAIPipeline()
    return pipeline.run(
        video_path, case_name, force_reprocess=force_reprocess, skip_stitch=skip_stitch
    )

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="轉錄流程：輸出寫入 data/<case>/。若影片在 data/<case>/source/ 下且未指定 --case，會自動使用該資料夾名稱。"
    )
    parser.add_argument("video_path", help="影片或音訊路徑")
    parser.add_argument(
        "--case",
        default=None,
        help="案例名稱（對應 data/<case>/）。省略且路徑為 data/某案/source/檔名 時會自動推斷",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="清空該案 intermediate 後重跑（避免沿用舊 whisper/stitch 結果）",
    )
    parser.add_argument(
        "--no-stitch",
        action="store_true",
        help="跳過規則併句：aligned 逐段轉成與 stitch 相同格式後只做 Flag（亦可用環境變數 SKIP_STITCH=1）",
    )
    args = parser.parse_args()

    if run_pipeline(
        args.video_path,
        args.case,
        force_reprocess=args.force,
        skip_stitch=True if args.no_stitch else None,
    ):
        print("\n✅ Success!")
    else:
        print("\n❌ Failed (Try running again for resume)")
        sys.exit(1)
