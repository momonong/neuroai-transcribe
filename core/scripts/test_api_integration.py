#!/usr/bin/env python3
"""
測試 API 整合 - 驗證新的扁平化結構是否正常工作
"""
import sys
import os
import requests
import json
from pathlib import Path

# 確保正確的路徑設定
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(backend_dir)

sys.path.insert(0, backend_dir)

API_BASE = "http://localhost:8001/api"

def test_api_endpoints():
    """測試各個 API 端點"""
    print("🧪 測試 API 端點...")
    print("=" * 50)
    
    # 1. 測試案例清單 API
    print("📋 測試案例清單 API (/api/testers):")
    try:
        response = requests.get(f"{API_BASE}/testers", timeout=5)
        if response.status_code == 200:
            cases = response.json()
            print(f"   ✅ 成功取得 {len(cases)} 個案例:")
            for case in cases[:3]:  # 只顯示前3個
                print(f"      - {case}")
        else:
            print(f"   ❌ 失敗: {response.status_code}")
    except Exception as e:
        print(f"   ❌ 連線失敗: {e}")
    
    # 2. 測試影片清單 API
    print("\n🎥 測試影片清單 API (/api/videos):")
    try:
        response = requests.get(f"{API_BASE}/videos", timeout=5)
        if response.status_code == 200:
            videos = response.json()
            print(f"   ✅ 成功取得 {len(videos)} 個影片:")
            for video in videos[:3]:  # 只顯示前3個
                print(f"      - {video['name']}")
                print(f"        路徑: {video['path']}")
        else:
            print(f"   ❌ 失敗: {response.status_code}")
    except Exception as e:
        print(f"   ❌ 連線失敗: {e}")
    
    # 3. 測試 JSON 檔案清單 API
    print("\n📄 測試 JSON 檔案清單 API (/api/temp/chunks):")
    try:
        response = requests.get(f"{API_BASE}/temp/chunks", timeout=5)
        if response.status_code == 200:
            data = response.json()
            files = data.get('files', [])
            print(f"   ✅ 成功取得 {len(files)} 個 JSON 檔案:")
            for file in files[:3]:  # 只顯示前3個
                print(f"      - {file}")
        else:
            print(f"   ❌ 失敗: {response.status_code}")
    except Exception as e:
        print(f"   ❌ 連線失敗: {e}")
    
    # 4. 測試讀取特定檔案 API (如果有檔案的話)
    print("\n📖 測試讀取特定檔案 API:")
    try:
        # 先取得檔案清單
        response = requests.get(f"{API_BASE}/temp/chunks", timeout=5)
        if response.status_code == 200:
            files = response.json().get('files', [])
            if files:
                test_file = files[0]
                print(f"   測試檔案: {test_file}")
                
                response = requests.get(f"{API_BASE}/temp/chunk/{test_file}", timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    segments_count = len(data.get('segments', []))
                    media_file = data.get('media_file', 'N/A')
                    print(f"   ✅ 成功讀取檔案:")
                    print(f"      - 段落數: {segments_count}")
                    print(f"      - 媒體檔案: {media_file}")
                else:
                    print(f"   ❌ 讀取失敗: {response.status_code}")
            else:
                print("   ⚠️  沒有可測試的檔案")
        else:
            print("   ❌ 無法取得檔案清單")
    except Exception as e:
        print(f"   ❌ 測試失敗: {e}")

def check_data_structure():
    """檢查實際的資料夾結構"""
    print("\n📁 檢查資料夾結構:")
    print("=" * 30)
    
    data_dir = Path(project_root) / "data"
    
    if not data_dir.exists():
        print("❌ data 資料夾不存在")
        return
    
    case_count = 0
    total_videos = 0
    total_jsons = 0
    
    for item in sorted(data_dir.iterdir()):
        if item.is_dir() and item.name not in ["temp_chunks", "db", "text", "__pycache__"]:
            case_count += 1
            files = list(item.iterdir())
            videos = [f for f in files if f.suffix.lower() in ['.mp4', '.mp3', '.wav']]
            jsons = [f for f in files if f.suffix == '.json']
            
            total_videos += len(videos)
            total_jsons += len(jsons)
            
            print(f"   📁 {item.name}: {len(videos)} 影音, {len(jsons)} JSON")
    
    print(f"\n📊 總計: {case_count} 個案例, {total_videos} 個影音檔, {total_jsons} 個 JSON 檔")

if __name__ == "__main__":
    print("🚀 開始整合測試...")
    
    # 檢查資料夾結構
    check_data_structure()
    
    # 測試 API (需要後端服務運行)
    print("\n" + "="*50)
    print("⚠️  以下測試需要後端服務運行在 localhost:8001")
    print("   請先執行: python backend/main.py")
    print("="*50)
    
    response = input("\n❓ 後端服務是否已啟動? (y/N): ").strip().lower()
    if response == 'y':
        test_api_endpoints()
    else:
        print("⏩ 跳過 API 測試")
    
    print("\n✅ 整合測試完成!")