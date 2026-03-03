import os
import shutil
import glob

def find_data_dir():
    current_path = os.path.abspath(__file__)
    for _ in range(5):
        current_path = os.path.dirname(current_path)
        potential_data = os.path.join(current_path, "data")
        if os.path.exists(potential_data):
            if os.path.exists(os.path.join(potential_data, "ASD")) or \
               os.path.exists(os.path.join(potential_data, "temp_chunks")):
                return potential_data
    return None

def main():
    # 1. 定位資料夾
    data_root = find_data_dir()
    if not data_root:
        print("❌ 錯誤：找不到 'data' 資料夾！")
        return

    ASD_DIR = os.path.join(data_root, "ASD")
    TEMP_CHUNKS_DIR = os.path.join(data_root, "temp_chunks")

    print(f"🚀 開始執行歸檔 (除錯模式)...")
    print(f"📂 來源: {TEMP_CHUNKS_DIR}")
    print(f"📂 目標: {ASD_DIR}")
    print("-" * 50)

    if not os.path.exists(TEMP_CHUNKS_DIR):
        print("❌ 找不到 temp_chunks 資料夾。")
        return

    # 2. 列出所有目標專案
    asd_projects = []
    if os.path.exists(ASD_DIR):
        asd_projects = [f for f in os.listdir(ASD_DIR) if os.path.isdir(os.path.join(ASD_DIR, f))]
    
    print(f"📋 偵測到 {len(asd_projects)} 個 ASD 專案:")
    for i, p in enumerate(asd_projects):
        print(f"   [{i+1}] {p}")
    print("-" * 50)

    # 3. 掃描來源資料夾
    chunk_folders = [f for f in os.listdir(TEMP_CHUNKS_DIR) if os.path.isdir(os.path.join(TEMP_CHUNKS_DIR, f))]
    
    if not chunk_folders:
        print("✨ temp_chunks 裡面是空的，沒有資料夾需要搬移。")
        return

    for folder_name in chunk_folders:
        print(f"\n📦 正在處理來源資料夾: '{folder_name}'")
        
        # --- 嘗試自動配對 (忽略大小寫、忽略前後空白) ---
        clean_name = folder_name.strip().lower()
        matched_project = next((proj for proj in asd_projects if clean_name in proj.lower()), None)
        
        target_dir = None

        if matched_project:
            print(f"   🤖 自動配對成功 -> '{matched_project}'")
            target_dir = os.path.join(ASD_DIR, matched_project)
        else:
            print(f"   ⚠️ 無法自動配對！")
            # --- 手動選擇模式 ---
            print("   請手動選擇要搬移到哪個專案：")
            for i, p in enumerate(asd_projects):
                print(f"     [{i+1}] {p}")
            print(f"     [s] 跳過 (Skip)")
            
            choice = input("   👉 請輸入編號: ")
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(asd_projects):
                    selected_proj = asd_projects[idx]
                    print(f"   ✅ 你選擇了: {selected_proj}")
                    target_dir = os.path.join(ASD_DIR, selected_proj)
                else:
                    print("   ❌ 編號無效，跳過。")
                    continue
            else:
                print("   已跳過。")
                continue

        # --- 執行搬移 ---
        if target_dir:
            src_path = os.path.join(TEMP_CHUNKS_DIR, folder_name)
            files = glob.glob(os.path.join(src_path, "*"))
            
            if not files:
                print("   ⚠️ 資料夾是空的，嘗試刪除並跳過...")
                try: os.rmdir(src_path) 
                except: pass
                continue

            count = 0
            for file_path in files:
                file_name = os.path.basename(file_path)
                target_file = os.path.join(target_dir, file_name)
                
                if not os.path.exists(target_file):
                    shutil.move(file_path, target_file)
                    print(f"     ✅ 搬移檔案: {file_name}")
                    count += 1
                else:
                    print(f"     ⚠️ 檔案已存在 (跳過): {file_name}")
            
            if count > 0:
                # 嘗試刪除空的來源資料夾
                try:
                    os.rmdir(src_path)
                    print(f"   🗑️ 已移除來源空資料夾")
                except:
                    print(f"   ⚠️ 來源資料夾還有剩餘檔案，未刪除")

    print("\n🎉 全部處理完成！")

if __name__ == "__main__":
    main()