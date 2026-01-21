#!/usr/bin/env python3
"""
測試新的扁平化資料夾結構
"""
import sys
import os

# 確保正確的路徑設定
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(backend_dir)

sys.path.insert(0, backend_dir)

from core.config import config
from core.file_manager import file_manager

def test_new_structure():
    print("🧪 測試新的資料夾結構...")
    print("=" * 50)
    
    # 1. 測試配置
    print("📋 配置測試:")
    print(f"   Data Dir: {config.data_dir}")
    print(f"   Temp Chunks: {config.temp_chunks_dir}")
    print(f"   DB Dir: {config.db_dir}")
    print(f"   Text Dir: {config.text_dir}")
    
    # 2. 測試檔案管理器
    print("\n📁 檔案管理器測試:")
    
    # 測試案例目錄建立
    test_case = "20250120-test"
    case_dir = file_manager.get_case_dir(test_case)
    print(f"   案例目錄: {case_dir}")
    
    # 測試影片搜尋
    print("\n🎥 影片檔案搜尋:")
    videos = file_manager.find_video_files()
    for video in videos[:3]:  # 只顯示前3個
        print(f"   - {video['name']} ({video['case_name']})")
    
    # 測試案例清單
    print("\n📋 案例清單:")
    cases = file_manager.get_case_list()
    for case in cases[:3]:  # 只顯示前3個
        print(f"   - {case['name']}: {case['config'].get('status', 'unknown')}")
    
    print("\n✅ 測試完成!")

if __name__ == "__main__":
    test_new_structure()