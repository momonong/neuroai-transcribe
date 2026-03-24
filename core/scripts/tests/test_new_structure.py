#!/usr/bin/env python3
"""
測試新的扁平化資料夾結構
"""
import sys
import os

# 確保專案根在 path，以便 import core
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(backend_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.config import config
from core.file_manager import file_manager

def test_new_structure():
    print("🧪 測試新的資料夾結構...")
    print("=" * 50)
    
    # 1. 測試配置
    print("📋 配置測試:")
    print(f"   Project Root: {config.project_root}")
    print(f"   Data Dir: {config.data_dir}")
    print(f"   DB Dir: {config.db_dir}")
    print(f"   Model Cache: {config.model_cache_dir}")
    
    # 2. 測試檔案管理器
    print("\n📁 檔案管理器測試:")
    test_case = "20250120-test"
    case_dir = file_manager.get_case_dir(test_case)
    print(f"   案例目錄: {case_dir}")
    
    # 測試影片搜尋
    print("\n🎥 影片檔案搜尋:")
    videos = file_manager.find_video_files()
    for video in videos[:3]:
        print(f"   - {video['name']} ({video['case_name']})")
    
    print("\n✅ 測試完成!")

if __name__ == "__main__":
    test_new_structure()