import os
import gc
import json
import torch
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

# 將 backend 目錄加入 sys.path 以解決 core 模組導入問題
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
    """
    NeuroAI 自動化轉錄流程控制器
    負責串接：切分 -> 辨識(Whisper+Diarization) -> 合併 -> 異常標記
    """

    def __init__(self):
        self.processor: Optional[PipelinePhase2] = None

    def run(self, video_path: str, case_name: Optional[str] = None) -> Optional[str]:
        """
        執行完整 Pipeline
        """
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
            aligned_segments = self._step_2_process(chunk_metadata, case_name)
            
            # --- Phase 3: 句子修復 (加入斷點續傳) ---
            # 修改點：傳入 case_name 以便檢查檔案是否存在
            stitched_data = self._step_3_stitch(aligned_segments, case_name)
            
            # 儲存中間產物 (分 Chunk)
            # 即使是讀取快取，這裡重跑一次存檔也沒關係 (很快)，確保檔案一致性
            if stitched_data:
                self._save_stitched_intermediate(stitched_data, chunk_metadata, case_name)
            
            # --- Phase 4: 異常標記 ---
            final_data = self._step_4_flag(stitched_data, case_name) # 也傳入 case_name 給 Phase 4 擴充用

            # --- Final: 輸出 ---
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

    # ====================================================
    # 內部步驟 (Private Methods)
    # ====================================================

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

    # 👇👇👇 修改重點：加入檢查邏輯 👇👇👇
    def _step_3_stitch(self, segments: List[Dict], case_name: str) -> List[Dict]:
        print("\n🔗 --- Phase 3: Stitching ---")
        
        # 1. 檢查是否存在已修復的完整檔案
        inter_dir = file_manager.get_intermediate_dir(case_name)
        full_stitched_path = inter_dir / "full_stitched_transcript.json"
        
        if full_stitched_path.exists():
            print(f"   ⏩ Found existing stitched data: {full_stitched_path.name}")
            print(f"   ⏩ Skipping LLM processing.")
            return file_manager.load_json(full_stitched_path)

        # 2. 如果不存在，才執行 LLM
        if not segments:
            print("   ⚠️ No segments to stitch.")
            return []
        
        stitched = run_stitching_logic(segments)
        print(f"   ✅ Stitched {len(segments)} segments into {len(stitched)} sentences.")
        return stitched
    # 👆👆👆 修改結束 👆👆👆

    def _save_stitched_intermediate(self, stitched_data: List[Dict], chunk_metadata: List[Dict], case_name: str):
        print(f"   💾 Saving intermediate stitched files (per chunk)...")
        inter_dir = file_manager.get_intermediate_dir(case_name)
        
        full_path = inter_dir / "full_stitched_transcript.json"
        file_manager.save_json(stitched_data, full_path, backup=False)

        for meta in chunk_metadata:
            wav_path = meta['file_path']
            base_name = os.path.splitext(os.path.basename(wav_path))[0]
            start_sec = meta['start_time_ms'] / 1000.0
            end_sec = meta.get('end_time_ms', float('inf')) / 1000.0
            
            chunk_sentences = [
                s for s in stitched_data 
                if s['start'] >= start_sec and s['start'] < end_sec
            ]
            
            if chunk_sentences:
                chunk_json_path = inter_dir / f"{base_name}_stitched.json"
                file_manager.save_json(chunk_sentences, chunk_json_path, backup=False)

    def _step_4_flag(self, segments: List[Dict], case_name: str) -> List[Dict]:
        print("\n🚩 --- Phase 4: Anomaly Detection ---")
        
        # 這裡也可以考慮加斷點續傳，看你的需求
        # 如果 output/transcript.json 已經存在且完整，其實也可以跳過
        # 但因為 Phase 4 通常是最後一步，保留重跑彈性通常比較好
        
        if not segments:
            return []
            
        final_data = run_anomaly_detector(segments)
        flag_count = sum(1 for s in final_data if s.get('flags'))
        print(f"   ✅ Detection complete. Found {flag_count} flagged sentences.")
        return final_data

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