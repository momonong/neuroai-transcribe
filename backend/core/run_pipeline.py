import os
import gc
import json
import torch
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

# 將 backend 目錄加入 sys.path
backend_dir = str(Path(__file__).resolve().parent.parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# 引入核心模組
from core.config import config
from core.file_manager import file_manager

# 引入功能模組
from core.split import SmartAudioSplitter
from core.pipeline import PipelinePhase2
from core.stitch import run_stitching_logic
from core.flag import run_anomaly_detector

class NeuroAIPipeline:
    def __init__(self):
        self.processor: Optional[PipelinePhase2] = None

    def run(self, video_path: str, case_name: Optional[str] = None) -> Optional[str]:
        # 1. 初始化案例
        case_name = file_manager.create_case(video_path, case_name)
        
        print(f"🚀 [Pipeline] Start: {case_name}")
        print(f"📂 [Path] Source: {file_manager.get_source_dir(case_name)}")

        try:
            # --- Phase 1: 切分 ---
            chunk_metadata = self._step_1_split(video_path, case_name)
            if not chunk_metadata:
                raise ValueError("Splitting failed, no chunks generated.")

            # --- Phase 2: 辨識與對齊 ---
            self._step_2_process(chunk_metadata, case_name)
            
            # --- Phase 3 & 4: 分段修復與標記 (整合迴圈) ---
            # 這是最關鍵的修改：我們把 Stitch 和 Flag 整合在一個迴圈裡處理
            # 這樣每個 Chunk 都是獨立的：Aligned -> Stitched -> Flagged
            final_data = self._step_3_4_process_per_chunk(chunk_metadata, case_name)

            # --- Final: 輸出 ---
            # 將所有 Chunk 的結果合併存成最終的 transcript.json
            output_path = file_manager.get_output_file_path(case_name, "transcript.json")
            file_manager.save_json(final_data, output_path, backup=True)
            
            print(f"\n✅ [Pipeline] Complete! Output: {output_path}")
            return str(output_path)

        except Exception as e:
            print(f"\n❌ [Pipeline] Failed: {e}")
            import traceback
            traceback.print_exc()
            return None
        finally:
            self._cleanup_resources()

    # ... (Phase 1 和 Phase 2 的程式碼保持不變) ...
    def _step_1_split(self, video_path: str, case_name: str) -> List[Dict]:
        print("\n✂️ --- Phase 1: Audio Splitting ---")
        inter_dir = file_manager.get_intermediate_dir(case_name)
        splitter = SmartAudioSplitter(output_dir=str(inter_dir))
        chunks = splitter.split_audio(video_path, num_chunks=config.default_num_chunks)
        print(f"   ✅ Split into {len(chunks)} chunks.")
        return chunks

    def _step_2_process(self, chunk_metadata: List[Dict], case_name: str) -> List[Dict]:
        print("\n🤖 --- Phase 2: Batch Processing (Whisper -> Diarization) ---")
        if self.processor is None:
            self.processor = PipelinePhase2()
        inter_dir = file_manager.get_intermediate_dir(case_name)
        whisper_tasks = []
        diar_tasks = []
        alignment_tasks = []
        for meta in chunk_metadata:
            wav_path = meta['file_path']
            base_name = os.path.splitext(os.path.basename(wav_path))[0]
            offset_sec = meta['start_time_ms'] / 1000.0
            j_w = inter_dir / f"{base_name}_whisper.json"
            j_d = inter_dir / f"{base_name}_diar.json"
            j_a = inter_dir / f"{base_name}_aligned.json"
            whisper_tasks.append({'wav': str(wav_path), 'json': str(j_w)})
            diar_tasks.append({'wav': str(wav_path), 'json': str(j_d)})
            alignment_tasks.append({'w': str(j_w), 'd': str(j_d), 'out': str(j_a), 'offset': offset_sec})
        self.processor.run_whisper_batch(whisper_tasks)
        self.processor.run_diarization_batch(diar_tasks)
        print(f"\n🔗 [Batch Alignment] processing...", flush=True)
        all_segments = []
        for task in alignment_tasks:
            self.processor.run_alignment(task['w'], task['d'], task['out'], chunk_offset_sec=task['offset'])
            out_path = Path(task['out'])
            if out_path.exists():
                segs = file_manager.load_json(out_path)
                if segs: all_segments.extend(segs)
        raw_path = file_manager.get_output_file_path(case_name, "raw_aligned_transcript.json")
        all_segments.sort(key=lambda x: x.get('start', 0))
        file_manager.save_json(all_segments, raw_path, backup=False)
        return all_segments

    # 👇👇👇 核心修改：整合 Phase 3 & 4 為 Per-Chunk 處理 👇👇👇
    def _step_3_4_process_per_chunk(self, chunk_metadata: List[Dict], case_name: str) -> List[Dict]:
        print("\n🧠 --- Phase 3 & 4: Intelligent Processing (Stitch -> Flag) ---")
        inter_dir = file_manager.get_intermediate_dir(case_name)
        
        all_final_results = []

        for i, meta in enumerate(chunk_metadata):
            wav_path = meta['file_path']
            base_name = os.path.splitext(os.path.basename(wav_path))[0]
            
            # 定義檔案路徑
            aligned_path = inter_dir / f"{base_name}_aligned.json"
            stitched_path = inter_dir / f"{base_name}_stitched.json"
            flagged_path = inter_dir / f"{base_name}_flagged_for_human.json" # 這是我們要產生的最終分段檔
            
            print(f"   Processing Chunk {i+1}/{len(chunk_metadata)}: {base_name}")

            # 1. 檢查 Flagged 是否已存在 (最終斷點)
            if flagged_path.exists():
                print(f"      ⏩ Found flagged file. Skipping Chunk.")
                chunk_result = file_manager.load_json(flagged_path)
                all_final_results.extend(chunk_result)
                continue

            # 2. 準備 Stitched 資料
            stitched_data = []
            if stitched_path.exists():
                # 如果有 stitched 存檔，直接讀取
                print(f"      ⏩ Found stitched file. Loading...")
                stitched_data = file_manager.load_json(stitched_path)
            else:
                # 如果沒有，執行 Stitching
                if not aligned_path.exists():
                    print(f"      ⚠️ Aligned file missing. Skipping.")
                    continue
                
                raw_segments = file_manager.load_json(aligned_path)
                if not raw_segments: continue

                try:
                    print(f"      🧵 Stitching...")
                    stitched_data = run_stitching_logic(raw_segments)
                    file_manager.save_json(stitched_data, stitched_path, backup=False)
                except Exception as e:
                    print(f"      ❌ Stitching Failed: {e}")
                    # Fallback to raw
                    stitched_data = raw_segments

            # 3. 執行 Flagging (Anomaly Detection)
            if stitched_data:
                try:
                    print(f"      🚩 Flagging...")
                    flagged_data = run_anomaly_detector(stitched_data)
                    
                    # 存檔：這是給前端讀取的最終分段檔
                    file_manager.save_json(flagged_data, flagged_path, backup=False)
                    print(f"      💾 Saved: {flagged_path.name}")
                    
                    all_final_results.extend(flagged_data)
                except Exception as e:
                    print(f"      ❌ Flagging Failed: {e}")
                    # Fallback to stitched data (without flags)
                    all_final_results.extend(stitched_data)

        print(f"   ✅ All chunks processed. Total sentences: {len(all_final_results)}")
        return all_final_results
    # 👆👆👆 修改結束 👆👆👆

    def _cleanup_resources(self):
        if self.processor:
            del self.processor
            self.processor = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        print("   🧹 Resources cleaned up.")

def run_pipeline(video_path: str):
    pipeline = NeuroAIPipeline()
    return pipeline.run(video_path)

# ... (main block 保持不變) ...
if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="NeuroAI Pipeline")
    parser.add_argument("video_path", help="輸入影片檔案的路徑")
    parser.add_argument("--case", help="指定案例名稱 (可選)", default=None)
    args = parser.parse_args()

    if not os.path.exists(args.video_path):
        print(f"❌ Error: 找不到檔案: {args.video_path}")
        sys.exit(1)

    print("=" * 50)
    print(f"🎬 NeuroAI Pipeline 啟動")
    print(f"📄 目標影片: {args.video_path}")
    print("=" * 50)

    result = run_pipeline(args.video_path)

    if result:
        print("=" * 50)
        print(f"✅ 處理成功！")
        print(f"📂 輸出檔案: {result}")
        print("=" * 50)
    else:
        print("=" * 50)
        print(f"❌ 處理失敗")
        print("=" * 50)
        sys.exit(1)