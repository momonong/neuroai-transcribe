import os
import glob
import json
import shutil
from typing import List

# 引入你的四個模組
from core.split import SmartAudioSplitter
from core.pipeline import PipelinePhase2
from core.stitch import run_stitching_logic
from core.flag import run_anomaly_detector

def run_neuroai_pipeline(video_path: str, project_dir: str):
    """
    執行完整的 NeuroAI 轉錄流程：
    1. Split (切分)
    2. Process (Whisper + Pyannote + Alignment)
    3. Stitch (合併句子)
    4. Flag (異常標記)
    """
    print(f"🚀 [AI Engine] 啟動流程: {os.path.basename(video_path)}")
    print(f"📂 [AI Engine] 專案路徑: {project_dir}")
    
    # 定義暫存資料夾
    chunks_dir = os.path.join(project_dir, "temp_chunks")
    os.makedirs(chunks_dir, exist_ok=True)

    # ==========================================
    # Phase 1: 切分音訊 (Splitting)
    # ==========================================
    print("\n✂️ --- Phase 1: Audio Splitting ---")
    splitter = SmartAudioSplitter(output_dir=chunks_dir)
    # split_audio 會回傳 metadata list
    chunk_metadata_list = splitter.split_audio(video_path, num_chunks=4)
    
    if not chunk_metadata_list:
        print("❌ 切分失敗，流程中止。")
        return

    # ==========================================
    # Phase 2: 辨識與對齊 (Processing)
    # ==========================================
    print("\n🤖 --- Phase 2: Whisper & Diarization ---")
    
    # 初始化處理器 (載入模型)
    processor = PipelinePhase2()
    
    all_aligned_segments = []

    # 依序處理每個 chunk
    for chunk_meta in chunk_metadata_list:
        wav_path = chunk_meta['file_path']
        base_name = os.path.splitext(os.path.basename(wav_path))[0]
        
        # 定義中間產檔名
        json_whisper = os.path.join(chunks_dir, f"{base_name}_whisper.json")
        json_diar = os.path.join(chunks_dir, f"{base_name}_diar.json")
        json_aligned = os.path.join(chunks_dir, f"{base_name}_aligned.json")
        
        # 計算偏移量 (秒)
        offset_sec = chunk_meta['start_time_ms'] / 1000.0
        
        print(f"   Processing Chunk: {base_name} (Offset: {offset_sec}s)")

        # 1. 跑 Whisper
        processor.run_whisper(wav_path, json_whisper)
        
        # 2. 跑 Pyannote
        processor.run_diarization(wav_path, json_diar)
        
        # 3. 跑對齊 (Alignment)
        processor.run_alignment(json_whisper, json_diar, json_aligned, chunk_offset_sec=offset_sec)
        
        # 4. 讀取對齊結果加入總表
        if os.path.exists(json_aligned):
            with open(json_aligned, 'r', encoding='utf-8') as f:
                segments = json.load(f)
                all_aligned_segments.extend(segments)

    # 釋放 GPU 記憶體 (重要！)
    del processor
    import torch
    import gc
    gc.collect()
    torch.cuda.empty_cache()

    # 儲存未修飾的原始轉錄檔 (備份用)
    raw_path = os.path.join(project_dir, "raw_aligned_transcript.json")
    # 依時間排序
    all_aligned_segments.sort(key=lambda x: x['start'])
    with open(raw_path, 'w', encoding='utf-8') as f:
        json.dump(all_aligned_segments, f, ensure_ascii=False, indent=2)

    # ==========================================
    # Phase 3: 句子修復 (Stitching)
    # ==========================================
    print("\n🔗 --- Phase 3: Stitching & Correction ---")
    # 呼叫 stitch.py 的邏輯
    stitched_data = run_stitching_logic(all_aligned_segments)

    # ==========================================
    # Phase 4: 異常標記 (Flagging)
    # ==========================================
    print("\n🚩 --- Phase 4: Anomaly Detection ---")
    # 呼叫 flag.py 的邏輯
    final_data = run_anomaly_detector(stitched_data)

    # ==========================================
    # Final: 輸出最終結果
    # ==========================================
    final_output_path = os.path.join(project_dir, "transcript.json")
    with open(final_output_path, 'w', encoding='utf-8') as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)

    print(f"\n✅✅✅ Pipeline Complete! Result saved to: {final_output_path}")
    
    # 清理暫存檔 (可選)
    # shutil.rmtree(chunks_dir) 
    
    return final_output_path