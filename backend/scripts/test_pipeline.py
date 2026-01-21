#!/usr/bin/env python3
"""
測試 Pipeline 模組
"""
import sys
import os
from pathlib import Path

# 確保正確的路徑設定
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(backend_dir)

sys.path.insert(0, backend_dir)

def test_pipeline_imports():
    """測試 Pipeline 相關的匯入"""
    print("🧪 測試 Pipeline 匯入...")
    print("=" * 40)
    
    try:
        print("📦 測試基本匯入...")
        import torch
        print(f"   ✅ PyTorch: {torch.__version__}")
        
        from core.config import config
        print(f"   ✅ Config: {config.device}")
        
        print("📦 測試 AI 模組匯入...")
        from faster_whisper import WhisperModel
        print("   ✅ Faster-Whisper")
        
        from pyannote.audio import Pipeline
        print("   ✅ Pyannote")
        
        print("📦 測試 Pipeline 類別...")
        from core.pipeline import PipelinePhase2
        print("   ✅ PipelinePhase2")
        
        # 測試初始化 (不載入模型)
        processor = PipelinePhase2()
        print(f"   ✅ 初始化成功 (Device: {processor.device})")
        
        return True
        
    except ImportError as e:
        print(f"   ❌ 匯入錯誤: {e}")
        return False
    except Exception as e:
        print(f"   ❌ 其他錯誤: {e}")
        return False

def check_case_folders():
    """檢查可用的案例資料夾"""
    print("\n📁 檢查案例資料夾...")
    print("=" * 40)
    
    data_dir = Path(project_root) / "data"
    
    if not data_dir.exists():
        print("❌ data 資料夾不存在")
        return []
    
    cases_with_chunks = []
    
    for case_dir in data_dir.iterdir():
        if case_dir.is_dir() and case_dir.name not in ["temp_chunks", "db", "text", "__pycache__"]:
            # 檢查是否有 chunk wav 檔案
            chunk_files = list(case_dir.glob("chunk_*.wav"))
            
            if chunk_files:
                cases_with_chunks.append({
                    "name": case_dir.name,
                    "path": str(case_dir),
                    "chunks": len(chunk_files)
                })
                print(f"   📁 {case_dir.name}: {len(chunk_files)} chunks")
            else:
                print(f"   📁 {case_dir.name}: 無 chunk 檔案")
    
    if cases_with_chunks:
        print(f"\n✅ 找到 {len(cases_with_chunks)} 個有 chunk 檔案的案例")
    else:
        print("\n⚠️ 沒有找到包含 chunk 檔案的案例")
    
    return cases_with_chunks

def test_pipeline_dry_run():
    """測試 Pipeline 乾跑 (不實際執行 AI 模型)"""
    print("\n🔄 測試 Pipeline 乾跑...")
    print("=" * 40)
    
    # 檢查環境變數
    case_name = os.getenv("CASE_NAME")
    if case_name:
        print(f"📋 環境變數 CASE_NAME: {case_name}")
        case_folder = Path(project_root) / "data" / case_name
        
        if case_folder.exists():
            chunk_files = list(case_folder.glob("chunk_*.wav"))
            print(f"   📂 資料夾存在: {case_folder}")
            print(f"   🎵 Chunk 檔案: {len(chunk_files)}")
            
            if chunk_files:
                print("   📋 檔案清單:")
                for chunk in sorted(chunk_files)[:3]:  # 只顯示前3個
                    print(f"      - {chunk.name}")
                if len(chunk_files) > 3:
                    print(f"      ... 還有 {len(chunk_files) - 3} 個檔案")
            
            return True
        else:
            print(f"   ❌ 資料夾不存在: {case_folder}")
            return False
    else:
        print("⚠️ 未設定 CASE_NAME 環境變數")
        return False

if __name__ == "__main__":
    print("🚀 Pipeline 測試開始...")
    
    # 1. 測試匯入
    import_success = test_pipeline_imports()
    
    # 2. 檢查案例資料夾
    cases = check_case_folders()
    
    # 3. 測試乾跑
    dry_run_success = test_pipeline_dry_run()
    
    print("\n" + "=" * 50)
    print("📊 測試結果:")
    print(f"   匯入測試: {'✅ 通過' if import_success else '❌ 失敗'}")
    print(f"   資料夾檢查: {'✅ 通過' if cases else '⚠️ 無可用案例'}")
    print(f"   乾跑測試: {'✅ 通過' if dry_run_success else '❌ 失敗'}")
    
    if import_success and cases:
        print("\n🎉 Pipeline 基本功能正常！")
        print("💡 建議:")
        print("   1. 設定環境變數: set CASE_NAME=案例名稱")
        print("   2. 執行 Pipeline: python backend/core/pipeline.py")
    else:
        print("\n⚠️ 發現問題，請檢查上述錯誤訊息")