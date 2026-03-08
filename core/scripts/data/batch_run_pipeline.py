"""
批次前處理：掃描專案根目錄底下 data 的每一筆資料（子資料夾），
若已有 intermediate 則跳過，否則對該筆資料執行 run_pipeline 前處理。
"""
import os
import sys
from pathlib import Path

# 讓腳本可從任意目錄執行，並能 import core
_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core.run_pipeline import run_pipeline


VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".mp3", ".wav", ".m4a")


def find_data_root() -> str:
    """專案根目錄底下的 data 資料夾。"""
    current = os.path.abspath(os.path.dirname(__file__))
    for _ in range(3):
        current = os.path.dirname(current)
    return os.path.join(current, "data")


def find_one_video_in_case(case_path: str) -> str | None:
    """在單筆資料夾內找一個影音檔：優先 source/，否則該層。回傳絕對路徑。"""
    case = Path(case_path)
    search_dirs = [case / "source"] if (case / "source").is_dir() else []
    search_dirs.append(case)
    for d in search_dirs:
        if not d.exists():
            continue
        for ext in VIDEO_EXTENSIONS:
            for f in sorted(d.glob(f"*{ext}")):
                if f.suffix.lower() in [e for e in VIDEO_EXTENSIONS]:
                    return str(f.resolve())
    return None


def main():
    data_root = find_data_root()
    print(f"📂 資料根目錄: {data_root}")
    print("-" * 50)

    if not os.path.isdir(data_root):
        print("❌ 資料根目錄不存在。")
        return

    case_folders = [
        name for name in os.listdir(data_root)
        if os.path.isdir(os.path.join(data_root, name))
        and name not in ("__pycache__", ".git")
    ]

    if not case_folders:
        print("⚠️ 底下沒有任何資料夾可處理。")
        return

    skipped = 0
    processed = 0
    failed = 0

    for case_name in sorted(case_folders):
        case_path = os.path.join(data_root, case_name)
        inter_path = os.path.join(case_path, "intermediate")

        if os.path.isdir(inter_path):
            print(f"⏭️  跳過（已有 intermediate）: {case_name}")
            skipped += 1
            continue

        video_path = find_one_video_in_case(case_path)
        if not video_path:
            print(f"⚠️ 跳過（找不到影音檔）: {case_name}")
            skipped += 1
            continue

        print(f"\n▶ 前處理: {case_name}")
        if run_pipeline(video_path, case_name):
            processed += 1
        else:
            failed += 1

    print("-" * 50)
    print(f"🎉 完成。成功: {processed}，跳過: {skipped}，失敗: {failed}。")


if __name__ == "__main__":
    main()
