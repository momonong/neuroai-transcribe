import os

# 設定資料根目錄
BASE_DIR = "data"

def print_tree(startpath):
    print(f"🚀 開始掃描資料夾: {os.path.abspath(startpath)}")
    print("=" * 50)

    total_json = 0
    total_video = 0

    for root, dirs, files in os.walk(startpath):
        # 排除一些不需要顯示的系統資料夾
        dirs[:] = [d for d in dirs if d not in ['__pycache__', '.git', 'db', 'text']]
        
        level = root.replace(startpath, '').count(os.sep)
        indent = '│   ' * level
        folder_name = os.path.basename(root)
        
        # 顯示資料夾名稱
        print(f"{indent}├── 📁 {folder_name}/")
        
        subindent = '│   ' * (level + 1)
        
        for f in files:
            # 我們只關心 JSON 和 影音檔
            if f.endswith('.json'):
                print(f"{subindent}├── 📄 {f}")
                total_json += 1
            elif f.lower().endswith(('.mp4', '.mp3', '.wav', '.m4a')):
                print(f"{subindent}├── 🎥 {f}")
                total_video += 1
            # 其他檔案就不顯示，避免太亂

    print("=" * 50)
    print(f"📊 統計結果: 發現 {total_json} 個 JSON 檔, {total_video} 個影音檔")

if __name__ == "__main__":
    if os.path.exists(BASE_DIR):
        print_tree(BASE_DIR)
    else:
        print(f"❌ 找不到資料夾: {BASE_DIR}，請確認你是在 backend 目錄下執行。")