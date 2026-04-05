#!/usr/bin/env python3
"""
測試完整流程 Pipeline
"""
import sys
import os
from pathlib import Path

# 確保專案根在 path，以便 import core（core 位於專案根 core/）
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(backend_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

def find_test_video():
    """尋找可用的測試影片"""
    data_dir = Path(project_root) / "data"
    
    if not data_dir.exists():
        return None
    
    # 搜尋 MP4 檔案
    for case_dir in data_dir.iterdir():
        if case_dir.is_dir() and case_dir.name not in ["temp_chunks", "db", "text", "__pycache__"]:
            for video_file in case_dir.glob("*.MP4"):
                return str(video_file)
            for video_file in case_dir.glob("*.mp4"):
                return str(video_file)
    
    return None

def test_overall_pipeline_import():
    """測試完整流程的匯入"""
    print("🧪 測試完整流程匯入...")
    print("=" * 40)
    
    try:
        from core.overall_pipeline import OverallPipeline
        print("   ✅ OverallPipeline 匯入成功")
        return True
    except ImportError as e:
        print(f"   ❌ 匯入失敗: {e}")
        return False
    except Exception as e:
        print(f"   ❌ 其他錯誤: {e}")
        return False

def test_pipeline_initialization():
    """測試流程初始化"""
    print("\n🔧 測試流程初始化...")
    print("=" * 40)
    
    # 尋找測試影片
    test_video = find_test_video()
    
    if not test_video:
        print("   ⚠️ 找不到測試影片檔案")
        return False
    
    print(f"   📹 找到測試影片: {Path(test_video).name}")
    
    try:
        from core.overall_pipeline import OverallPipeline
        
        # 測試初始化
        pipeline = OverallPipeline(test_video, case_name="test-pipeline")
        
        print(f"   ✅ 初始化成功")
        print(f"      案例名稱: {pipeline.case_name}")
        print(f"      案例目錄: {pipeline.case_dir}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ 初始化失敗: {e}")
        return False

def show_usage_examples():
    """顯示使用範例"""
    print("\n📖 使用範例:")
    print("=" * 40)
    
    test_video = find_test_video()
    if test_video:
        video_name = Path(test_video).name
        print(f"# 使用找到的影片檔案")
        print(f"python backend/core/overall_pipeline.py \"{test_video}\"")
        print()
        print(f"# 指定案例名稱")
        print(f"python backend/core/overall_pipeline.py \"{test_video}\" --case-name \"我的測試案例\"")
        print()
        print(f"# 指定切分片段數")
        print(f"python backend/core/overall_pipeline.py \"{test_video}\" --chunks 6")
    else:
        print("# 一般使用方式")
        print("python backend/core/overall_pipeline.py \"path/to/video.mp4\"")
        print()
        print("# 指定案例名稱和片段數")
        print("python backend/core/overall_pipeline.py \"path/to/video.mp4\" --case-name \"案例名稱\" --chunks 4")

def main():
    print("🚀 完整流程測試開始...")
    
    # 1. 測試匯入
    import_success = test_overall_pipeline_import()
    
    # 2. 測試初始化
    init_success = test_pipeline_initialization()
    
    # 3. 顯示使用範例
    show_usage_examples()
    
    print("\n" + "=" * 50)
    print("📊 測試結果:")
    print(f"   匯入測試: {'✅ 通過' if import_success else '❌ 失敗'}")
    print(f"   初始化測試: {'✅ 通過' if init_success else '❌ 失敗'}")
    
    if import_success and init_success:
        print("\n🎉 完整流程基本功能正常！")
        print("💡 現在可以使用上述範例命令來執行完整轉錄流程")
    else:
        print("\n⚠️ 發現問題，請檢查上述錯誤訊息")

if __name__ == "__main__":
    main()