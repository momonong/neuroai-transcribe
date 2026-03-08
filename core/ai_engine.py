"""
Legacy AI Engine：使用舊版 project/chunk 結構。
主要流程請使用 core.run_pipeline.run_pipeline 或 core.overall_pipeline.OverallPipeline。
"""
import os
import glob
import json
import shutil
from typing import List, Optional

from shared.file_manager import file_manager
from .split import SmartAudioSplitter
from .pipeline import PipelinePhase2
from .stitch import run_stitching_logic
from .flag import run_anomaly_detector

def run_neuroai_pipeline(video_path: str, project_name: Optional[str] = None):
    """
    執行完整的 NeuroAI 轉錄流程（舊版 API，使用 create_case + intermediate）。
    """
    if project_name is None:
        project_name = file_manager.create_case(video_path)
    
    case_dir = file_manager.get_case_dir(project_name)
    inter_dir = file_manager.get_intermediate_dir(project_name)
    
    print(f"🚀 [AI Engine] 啟動流程: {os.path.basename(video_path)}")
    print(f"📂 [AI Engine] 專案: {project_name}")
    print(f"📁 [AI Engine] 專案路徑: {case_dir}")

    print("\n✂️ --- Phase 1: Audio Splitting ---")
    splitter = SmartAudioSplitter(output_dir=str(inter_dir))
    chunk_metadata_list = splitter.split_audio(video_path, num_chunks=4)
    
    if not chunk_metadata_list:
        print("❌ 切分失敗，流程中止。")
        return

    print("\n🤖 --- Phase 2: Whisper & Diarization ---")
    processor = PipelinePhase2()
    all_aligned_segments = []

    for chunk_meta in chunk_metadata_list:
        wav_path = chunk_meta['file_path']
        base_name = os.path.splitext(os.path.basename(wav_path))[0]
        json_whisper = os.path.join(inter_dir, f"{base_name}_whisper.json")
        json_diar = os.path.join(inter_dir, f"{base_name}_diar.json")
        json_aligned = os.path.join(inter_dir, f"{base_name}_aligned.json")
        offset_sec = chunk_meta['start_time_ms'] / 1000.0
        
        print(f"   Processing Chunk: {base_name} (Offset: {offset_sec}s)")
        processor.run_whisper_batch([{'wav': wav_path, 'json': json_whisper}])
        processor.run_diarization_batch([{'wav': wav_path, 'json': json_diar}])
        processor.run_alignment(json_whisper, json_diar, json_aligned, chunk_offset_sec=offset_sec)
        
        if os.path.exists(json_aligned):
            with open(json_aligned, 'r', encoding='utf-8') as f:
                segments = json.load(f)
                all_aligned_segments.extend(segments)

    del processor
    import torch
    import gc
    gc.collect()
    torch.cuda.empty_cache()

    raw_path = file_manager.get_output_file_path(project_name, "raw_aligned_transcript.json")
    all_aligned_segments.sort(key=lambda x: x['start'])
    file_manager.save_json(all_aligned_segments, raw_path, backup=False)

    print("\n🔗 --- Phase 3: Stitching & Correction ---")
    stitched_data = run_stitching_logic(all_aligned_segments)

    print("\n🚩 --- Phase 4: Anomaly Detection ---")
    final_data = run_anomaly_detector(stitched_data)

    final_output_path = file_manager.get_output_file_path(project_name, "transcript.json")
    file_manager.save_json(final_data, final_output_path, backup=True)

    print(f"\n✅✅✅ Pipeline Complete! Result saved to: {final_output_path}")
    return str(final_output_path)
