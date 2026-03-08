"""
整理資料夾供前處理使用：
- 掃描底下的每一個資料夾
- 若底下已有「source」資料夾 → 視為已前處理，跳過
- 若沒有「source」→ 建立 source，並將該資料夾內所有檔案/子資料夾移入 source
"""
import os
import shutil


def find_data_root():
    """專案根目錄底下的 data 資料夾（腳本在 core/scripts/data/，往上三層即專案根目錄）。"""
    current = os.path.abspath(os.path.dirname(__file__))
    for _ in range(3):
        current = os.path.dirname(current)
    return os.path.join(current, "data")


def main():
    data_root = find_data_root()
    print(f"📂 資料根目錄: {data_root}")
    print("-" * 50)

    if not os.path.isdir(data_root):
        print("❌ 資料根目錄不存在。")
        return

    target_folders = [
        name for name in os.listdir(data_root)
        if os.path.isdir(os.path.join(data_root, name))
        and name not in ("__pycache__", ".git", "source")
    ]

    if not target_folders:
        print("⚠️ 底下沒有任何資料夾可處理。")
        return

    print(f"📋 找到 {len(target_folders)} 個目標資料夾")
    skipped = 0
    processed = 0

    for folder_name in sorted(target_folders):
        folder_path = os.path.join(data_root, folder_name)
        source_path = os.path.join(folder_path, "source")

        if os.path.isdir(source_path):
            print(f"⏭️  跳過（已有 source）: {folder_name}")
            skipped += 1
            continue

        # 建立 source，並把該資料夾內「所有直接子項目」移入 source
        os.makedirs(source_path, exist_ok=True)
        moved = 0
        for item in os.listdir(folder_path):
            if item == "source":
                continue
            src = os.path.join(folder_path, item)
            dst = os.path.join(source_path, item)
            if os.path.exists(dst):
                print(f"   ⚠️ 目標已存在，跳過: {folder_name}/{item}")
                continue
            shutil.move(src, dst)
            moved += 1
        print(f"✅ 已整理: {folder_name} （建立 source，移入 {moved} 個項目）")
        processed += 1

    print("-" * 50)
    print(f"🎉 完成。已整理: {processed} 個，跳過（已有 source）: {skipped} 個。")


if __name__ == "__main__":
    main()
