#!/usr/bin/env python3
"""
遷移腳本：將 data/ASD/ 下的資料夾移到 data/ 下
"""
import os
import shutil
from pathlib import Path

def migrate_asd_to_flat():
    """將 ASD 資料夾下的案例移到 data 根目錄"""
    
    project_root = Path(__file__).parent.parent.parent
    data_dir = project_root / "data"
    asd_dir = data_dir / "ASD"
    
    print(f"🚀 開始遷移資料夾結構...")
    print(f"   來源: {asd_dir}")
    print(f"   目標: {data_dir}")
    print("=" * 50)
    
    if not asd_dir.exists():
        print("❌ ASD 資料夾不存在，無需遷移")
        return
    
    # 取得 ASD 下的所有案例資料夾
    case_folders = [f for f in asd_dir.iterdir() if f.is_dir()]
    
    if not case_folders:
        print("📂 ASD 資料夾是空的，無需遷移")
        return
    
    print(f"📋 發現 {len(case_folders)} 個案例資料夾:")
    for folder in case_folders:
        print(f"   - {folder.name}")
    
    # 確認是否繼續
    response = input("\n❓ 是否繼續遷移? (y/N): ").strip().lower()
    if response != 'y':
        print("❌ 取消遷移")
        return
    
    # 開始遷移
    success_count = 0
    for case_folder in case_folders:
        target_path = data_dir / case_folder.name
        
        try:
            if target_path.exists():
                print(f"⚠️  目標已存在，跳過: {case_folder.name}")
                continue
            
            # 移動資料夾
            shutil.move(str(case_folder), str(target_path))
            print(f"✅ 已移動: {case_folder.name}")
            success_count += 1
            
        except Exception as e:
            print(f"❌ 移動失敗 {case_folder.name}: {e}")
    
    print("=" * 50)
    print(f"🎉 遷移完成! 成功移動 {success_count} 個資料夾")
    
    # 檢查 ASD 資料夾是否為空
    remaining_items = list(asd_dir.iterdir())
    if not remaining_items:
        print(f"🗑️  ASD 資料夾已空，是否刪除? (y/N): ", end="")
        response = input().strip().lower()
        if response == 'y':
            asd_dir.rmdir()
            print("✅ 已刪除空的 ASD 資料夾")
    else:
        print(f"⚠️  ASD 資料夾還有 {len(remaining_items)} 個項目，請手動檢查")

def show_new_structure():
    """顯示新的資料夾結構"""
    project_root = Path(__file__).parent.parent.parent
    data_dir = project_root / "data"
    
    print("\n📁 新的資料夾結構:")
    print("=" * 30)
    
    if not data_dir.exists():
        print("❌ data 資料夾不存在")
        return
    
    for item in sorted(data_dir.iterdir()):
        if item.is_dir():
            if item.name in ["temp_chunks", "db", "text", "__pycache__"]:
                print(f"   📁 {item.name}/ (系統資料夾)")
            else:
                # 計算案例資料夾內的檔案數量
                try:
                    files = list(item.iterdir())
                    video_count = len([f for f in files if f.suffix.lower() in ['.mp4', '.mp3', '.wav']])
                    json_count = len([f for f in files if f.suffix == '.json'])
                    print(f"   📁 {item.name}/ ({video_count} 影音, {json_count} JSON)")
                except:
                    print(f"   📁 {item.name}/")

if __name__ == "__main__":
    migrate_asd_to_flat()
    show_new_structure()