"""
掃描 data 目錄、列出影片與 cases 的純邏輯（無 FastAPI 依賴）。
"""
import os
from typing import List, Dict

from config import DATA_DIR, IGNORE_DIRS

# 支援常見音視訊格式
_VIDEO_EXTENSIONS = [".mp4", ".MP4", ".mov", ".MOV", ".avi", ".AVI"]


def list_videos() -> List[Dict[str, str]]:
    """
    掃描 DATA_DIR 底下各 case，支援 data/Case/source 與 data/Case 兩種結構，
    排除 IGNORE_DIRS，回傳影片列表。每項含 path（相對 DATA_DIR）、name。
    """
    video_files: List[Dict[str, str]] = []
    if not os.path.exists(DATA_DIR):
        return video_files

    with os.scandir(DATA_DIR) as it:
        for entry in it:
            if not entry.is_dir() or entry.name in IGNORE_DIRS:
                continue
            case_name = entry.name
            case_path = entry.path

            search_targets = []
            source_dir = os.path.join(case_path, "source")
            if os.path.exists(source_dir):
                search_targets.append(source_dir)
            search_targets.append(case_path)

            seen_files = set()
            for target_dir in search_targets:
                if not os.path.exists(target_dir):
                    continue
                for f in os.listdir(target_dir):
                    if not any(f.endswith(ext) for ext in _VIDEO_EXTENSIONS):
                        continue
                    if f.startswith("chunk_"):
                        continue
                    if f in seen_files:
                        continue
                    seen_files.add(f)
                    full_path = os.path.join(target_dir, f)
                    rel_path = os.path.relpath(full_path, DATA_DIR).replace("\\", "/")
                    video_files.append({"path": rel_path, "name": case_name})

    video_files.sort(key=lambda x: x["name"], reverse=True)
    return video_files


def list_cases() -> List[str]:
    """列出 data 底下專案資料夾（排除 IGNORE_DIRS）。"""
    cases: List[str] = []
    if not os.path.exists(DATA_DIR):
        return cases
    with os.scandir(DATA_DIR) as it:
        for entry in it:
            if entry.is_dir() and entry.name not in IGNORE_DIRS:
                cases.append(entry.name)
    cases.sort(reverse=True)
    return cases
