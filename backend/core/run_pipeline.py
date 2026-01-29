import os
import json
import sys
from pathlib import Path
from typing import Optional, List, Dict

# 將 backend 目錄加入 sys.path
backend_dir = str(Path(__file__).resolve().parent.parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from core.config import config
from core.file_manager import file_manager
from core.split import SmartAudioSplitter
from core.pipeline import PipelinePhase2
from core.stitch import run_stitching_logic
from core.flag import run_anomaly_detector

class NeuroAIPipeline:
    def __init__(self):
        self.processor = PipelinePhase2()

    def run(self, video_path: str, case_name: Optional[str] = None) -> Optional[str]:
        case_name = file_manager.create_case(video_path, case_name)
        print(f"🚀 [Pipeline] Start: {case_name}")

        try:
            # Phase 1: Split
            chunk_metadata = self._step_1_split(video_path, case_name)
            if not chunk_metadata: return None

            # Phase 2: Process (Monolithic)
            self._step_2_process(chunk_metadata, case_name)
            
            # Phase 3 & 4: Stitch & Flag
            final_data = self._step_3_4_process_per_chunk(chunk_metadata, case_name)

            output_path = file_manager.get_output_file_path(case_name, "transcript.json")
            file_manager.save_json(final_data, output_path, backup=True)
            
            print(f"\n✅ [Pipeline] Complete! Output: {output_path}")
            return str(output_path)

        except Exception as e:
            print(f"\n❌ [Pipeline] Failed: {e}")
            return None

    def _step_1_split(self, video_path: str, case_name: str) -> List[Dict]:
        print("\n✂️ --- Phase 1: Audio Splitting ---")
        inter_dir = file_manager.get_intermediate_dir(case_name)
        splitter = SmartAudioSplitter(output_dir=str(inter_dir))
        return splitter.split_audio(video_path, num_chunks=config.default_num_chunks)

    def _step_2_process(self, chunk_metadata: List[Dict], case_name: str):
        print("\n🤖 --- Phase 2: Batch Processing ---")
        inter_dir = file_manager.get_intermediate_dir(case_name)
        
        whisper_tasks = []
        diar_tasks = []
        align_tasks = []

        for meta in chunk_metadata:
            wav = meta['file_path']
            base = os.path.splitext(os.path.basename(wav))[0]
            offset = meta['start_time_ms'] / 1000.0
            
            j_w = inter_dir / f"{base}_whisper.json"
            j_d = inter_dir / f"{base}_diar.json"
            j_a = inter_dir / f"{base}_aligned.json"
            
            whisper_tasks.append({'wav': str(wav), 'json': str(j_w)})
            diar_tasks.append({'wav': str(wav), 'json': str(j_d)})
            align_tasks.append({'w': str(j_w), 'd': str(j_d), 'out': str(j_a), 'offset': offset})

        # 直接呼叫函式，不搞 worker 了
        self.processor.run_whisper_batch(whisper_tasks)
        self.processor.run_diarization_batch(diar_tasks)
        
        print("\n🔗 [Batch Alignment]...")
        for t in align_tasks:
            self.processor.run_alignment(t['w'], t['d'], t['out'], t['offset'])

    def _step_3_4_process_per_chunk(self, chunk_metadata: List[Dict], case_name: str) -> List[Dict]:
        print("\n🧠 --- Phase 3 & 4: Stitch -> Flag ---")
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
                print("      ⏩ Found flagged file.")
                final_results.extend(file_manager.load_json(flagged))
                continue

            stitched_data = []
            if stitched.exists():
                print("      ⏩ Found stitched file.")
                stitched_data = file_manager.load_json(stitched)
            elif aligned.exists():
                raw = file_manager.load_json(aligned)
                if raw:
                    print("      🧵 Stitching...")
                    try:
                        stitched_data = run_stitching_logic(raw)
                        file_manager.save_json(stitched_data, stitched, backup=False)
                    except Exception as e:
                        print(f"      ❌ Stitch failed: {e}")
                        stitched_data = raw

            if stitched_data:
                print("      🚩 Flagging...")
                flagged_data = run_anomaly_detector(stitched_data)
                file_manager.save_json(flagged_data, flagged, backup=False)
                final_results.extend(flagged_data)

        return final_results

def run_pipeline(video_path: str):
    pipeline = NeuroAIPipeline()
    return pipeline.run(video_path)

if __name__ == "__main__":
    import argparse
    import sys
    parser = argparse.ArgumentParser()
    parser.add_argument("video_path")
    parser.add_argument("--case", default=None)
    args = parser.parse_args()

    if run_pipeline(args.video_path):
        print("\n✅ Success!")
    else:
        print("\n❌ Failed (Try running again for resume)")
        sys.exit(1)