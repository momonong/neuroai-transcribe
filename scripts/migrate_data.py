import os
import shutil
import glob
from dotenv import load_dotenv

load_dotenv()  # 讀取 .env 檔案中的環境變數

# 設定你的專案根目錄路徑
PROJECT_ROOT = r"D:\projects\neuroai-transcribe\data\20250324-20054665" + os.getenv("TESTER_NAME")

# 定義子資料夾名稱
FOLDERS = {
    "source": "source",
    "intermediate": "intermediate",
    "output": "output"
}

def organize_project():
    # 1. 建立資料夾
    for folder_name in FOLDERS.values():
        path = os.path.join(PROJECT_ROOT, folder_name)
        os.makedirs(path, exist_ok=True)
        print(f"📁 Checked folder: {path}")

    # 2. 檔案分類規則 (副檔名或關鍵字)
    moves = [
        # (檔案特徵, 目標資料夾)
        ("*.MP4", "source"),
        ("*.mp3", "source"),
        ("*.srt", "source"),
        
        ("chunk_*.wav", "intermediate"),
        ("*_whisper.json", "intermediate"),
        ("*_diar.json", "intermediate"),
        ("*_aligned.json", "intermediate"),
        
        # 這些看起來像是手動編輯或最終產出的檔案
        ("*_edited.json", "output"),
        ("*_flagged_for_human.json", "output"),
        ("transcript.json", "output"),
    ]

    print("\n🚀 開始整理檔案...")
    
    for pattern, dest_key in moves:
        dest_dir = os.path.join(PROJECT_ROOT, FOLDERS[dest_key])
        # 搜尋符合 pattern 的檔案
        files = glob.glob(os.path.join(PROJECT_ROOT, pattern))
        
        for f in files:
            filename = os.path.basename(f)
            # 避免移動資料夾本身
            if os.path.isdir(f): continue
            
            src_path = f
            dst_path = os.path.join(dest_dir, filename)
            
            try:
                shutil.move(src_path, dst_path)
                print(f"✅ Moved: {filename} -> {dest_key}/")
            except Exception as e:
                print(f"❌ Error moving {filename}: {e}")

    print("\n✨ 整理完成！")

if __name__ == "__main__":
    organize_project()