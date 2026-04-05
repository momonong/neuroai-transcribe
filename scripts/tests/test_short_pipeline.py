#!/usr/bin/env python3
"""
測試完整流程 - 使用現有的 chunk 檔案
"""
import sys
import os
from pathlib import Path

# 確保專案根在 path，以便 import core
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(backend_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

def test_with_existing_chunks():
    """使用現有的 chunk 檔案測試後續流程"""
    print("🧪 測試完整流程 (使用現有 chunks)...")
    print("=" * 50)
    
    # 找到有 chunk 檔案的案例
    data_dir = Path(project_root) / "data"
    case_with_chunks = None
    
    for case_dir in data_dir.iterdir():
        if case_dir.is_dir() and case_dir.name not in ["temp_chunks", "db", "text", "__pycache__"]:
            chunk_files = list(case_dir.glob("chunk_*.wav"))
            if chunk_files:
                case_with_chunks = case_dir
                break
    
    if not case_with_chunks:
        print("❌ 找不到有 chunk 檔案的案例")
        return False
    
    print(f"📁 使用案例: {case_with_chunks.name}")
    
    try:
        from core.overall_pipeline import OverallPipeline
        
        # 找到真實的影片檔案
        video_files = list(case_with_chunks.glob("*.MP4")) + list(case_with_chunks.glob("*.mp4"))
        if not video_files:
            print("❌ 找不到影片檔案")
            return False
        
        video_file = video_files[0]
        print(f"📹 使用影片: {video_file.name}")
        
        # 初始化 pipeline
        pipeline = OverallPipeline(str(video_file), case_name=f"{case_with_chunks.name}-test")
        
        # 手動建立 chunk metadata
        chunk_files = sorted(case_with_chunks.glob("chunk_*.wav"))
        chunk_metadata = []
        
        for chunk_file in chunk_files:
            # 解析檔名取得時間資訊
            try:
                parts = chunk_file.stem.split('_')
                start_ms = int(parts[-2])
                end_ms = int(parts[-1])
                
                chunk_metadata.append({
                    'file_path': str(chunk_file),
                    'start_time_ms': start_ms,
                    'end_time_ms': end_ms,
                    'duration_ms': end_ms - start_ms
                })
            except:
                # 如果解析失敗，使用預設值
                chunk_metadata.append({
                    'file_path': str(chunk_file),
                    'start_time_ms': 0,
                    'end_time_ms': 60000,  # 假設 60 秒
                    'duration_ms': 60000
                })
        
        print(f"📄 找到 {len(chunk_metadata)} 個 chunk 檔案")
        
        # 跳過音訊切分，直接從 AI 處理開始
        print("\n⏩ 跳過音訊切分，直接進行 AI 處理...")
        
        # 檢查是否已有 aligned 檔案
        aligned_files = []
        for chunk_file in chunk_files:
            aligned_file = chunk_file.with_suffix('') / "_aligned.json"
            aligned_file = str(chunk_file).replace('.wav', '_aligned.json')
            if os.path.exists(aligned_file):
                aligned_files.append(aligned_file)
        
        if aligned_files:
            print(f"✅ 找到 {len(aligned_files)} 個已處理的 aligned 檔案")
            
            # 直接進行合併和後處理
            all_segments = pipeline.step3_merge_chunks(aligned_files)
            
            if all_segments:
                final_segments = pipeline.step4_stitch_and_flag(all_segments)
                output_file = pipeline.save_results(final_segments)
                
                print(f"\n🎉 測試成功！結果檔案: {output_file}")
                return True
            else:
                print("❌ 沒有可用的片段資料")
                return False
        else:
            print("⚠️ 沒有找到已處理的 aligned 檔案")
            print("💡 建議先執行 AI 處理步驟")
            return False
            
    except Exception as e:
        print(f"❌ 測試失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_with_existing_chunks()
    
    if success:
        print("\n✅ 完整流程測試通過！")
    else:
        print("\n❌ 測試失敗，請檢查錯誤訊息")