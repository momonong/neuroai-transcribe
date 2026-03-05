"""
Chunk 清單、讀取單一 chunk、存檔的純邏輯（無 FastAPI 依賴）。
"""
import json
import os
import glob
from datetime import datetime
from typing import List, Optional, Dict, Any

from config import DATA_DIR, get_real_path


def _chunk_sort_key(path: str) -> int:
    try:
        filename = os.path.basename(path)
        parts = filename.split("_")
        return int(parts[1])
    except Exception:
        return 0


def list_chunks(case: Optional[str] = None) -> List[str]:
    """
    依 case 列出 chunk 檔案（智慧篩選：每個 chunk ID 只回傳最高優先級檔案）。
    優先級: edited > flagged > stitched > verified > aligned。
    回傳相對 DATA_DIR 的路徑字串列表。
    """
    if case:
        inter_path = os.path.join(DATA_DIR, case, "intermediate", "chunk_*.json")
        root_path = os.path.join(DATA_DIR, case, "chunk_*.json")
        all_files = glob.glob(inter_path) + glob.glob(root_path)
    else:
        all_files = glob.glob(os.path.join(DATA_DIR, "*", "intermediate", "chunk_*.json")) + glob.glob(
            os.path.join(DATA_DIR, "*", "chunk_*.json")
        )

    chunk_groups: Dict[str, Dict[str, str]] = {}
    for f in all_files:
        filename = os.path.basename(f)
        if "whisper" in filename or "diar" in filename:
            continue
        parts = filename.split("_")
        if len(parts) < 2:
            continue
        parent_dir = os.path.dirname(f)
        if os.path.basename(parent_dir) == "intermediate":
            case_name = os.path.basename(os.path.dirname(parent_dir))
        else:
            case_name = os.path.basename(parent_dir)
        chunk_id = f"{parts[0]}_{parts[1]}"
        unique_key = f"{case_name}/{chunk_id}"
        if unique_key not in chunk_groups:
            chunk_groups[unique_key] = {}
        if "flagged_for_human" in filename:
            chunk_groups[unique_key]["flagged"] = f
        elif "edited" in filename:
            chunk_groups[unique_key]["edited"] = f
        elif "verified_dataset" in filename:
            chunk_groups[unique_key]["verified"] = f
        elif "stitched" in filename:
            chunk_groups[unique_key]["stitched"] = f
        elif "aligned" in filename:
            chunk_groups[unique_key]["aligned"] = f

    json_files: List[str] = []
    for key, variants in chunk_groups.items():
        best_file = None
        if "edited" in variants:
            best_file = variants["edited"]
        elif "flagged" in variants:
            best_file = variants["flagged"]
        elif "stitched" in variants:
            best_file = variants["stitched"]
        elif "verified" in variants:
            best_file = variants["verified"]
        elif "aligned" in variants:
            best_file = variants["aligned"]
        if best_file:
            rel_path = os.path.relpath(best_file, DATA_DIR)
            json_files.append(rel_path.replace("\\", "/"))

    json_files.sort(key=_chunk_sort_key)
    return json_files


def get_chunk(filename: str) -> Dict[str, Any]:
    """
    依 filename（相對路徑）讀取單一 chunk。
    解析 core_name、候選路徑、依優先權選檔、讀取 JSON、媒體配對，組裝成前端需要的 dict。
    若檔案不存在則 raise FileNotFoundError；其他錯誤由呼叫方處理。
    """
    request_path = get_real_path(filename)
    directory = os.path.dirname(request_path)
    request_fname = os.path.basename(request_path)

    core_name = (
        request_fname.replace("_flagged_for_human.json", "")
        .replace("_edited.json", "")
        .replace("_verified_dataset.json", "")
        .replace("_stitched.json", "")
        .replace("_aligned.json", "")
        .replace(".json", "")
    )
    for suffix in ["_whisper", "_aligned", "_diar"]:
        if core_name.endswith(suffix):
            core_name = core_name.replace(suffix, "")

    candidate_edited = os.path.join(directory, f"{core_name}_edited.json")
    candidate_flagged = os.path.join(directory, f"{core_name}_flagged_for_human.json")
    candidate_stitched = os.path.join(directory, f"{core_name}_stitched.json")
    candidate_verified = os.path.join(directory, f"{core_name}_verified_dataset.json")
    candidate_aligned = os.path.join(directory, f"{core_name}_aligned.json")

    target_path = None
    if os.path.exists(candidate_edited):
        target_path = candidate_edited
    elif os.path.exists(candidate_flagged):
        target_path = candidate_flagged
    elif os.path.exists(candidate_stitched):
        target_path = candidate_stitched
    elif os.path.exists(candidate_verified):
        target_path = candidate_verified
    elif os.path.exists(candidate_aligned):
        target_path = candidate_aligned
    else:
        target_path = request_path

    if not target_path or not os.path.exists(target_path):
        raise FileNotFoundError(f"Chunk file not found: {filename}")

    with open(target_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    case_root = os.path.dirname(directory)
    if os.path.basename(directory) != "intermediate":
        case_root = directory
    media_search_dirs = [
        os.path.join(case_root, "source"),
        case_root,
    ]
    target_media = None
    media_folder_found = None
    for search_dir in media_search_dirs:
        if not os.path.exists(search_dir):
            continue
        files = os.listdir(search_dir)
        mp4_files = [f for f in files if f.lower().endswith((".mp4", ".mov", ".avi"))]
        if mp4_files:
            mp4_files.sort(key=len)
            target_media = mp4_files[0]
            media_folder_found = search_dir
            break

    processed_data: Dict[str, Any] = (
        data
        if isinstance(data, dict)
        else {"segments": data, "speaker_mapping": {}, "file_type": "original"}
    )
    if target_media and media_folder_found:
        full_media_path = os.path.join(media_folder_found, target_media)
        media_rel_path = os.path.relpath(full_media_path, DATA_DIR).replace("\\", "/")
        processed_data["media_file"] = media_rel_path
    if "_flagged_for_human" in target_path:
        processed_data["file_type"] = "flagged"
    elif "_edited" in target_path:
        processed_data["file_type"] = "edited"
    else:
        processed_data["file_type"] = "original"

    return processed_data


def save_chunk(payload: Any) -> Dict[str, str]:
    """
    將 SavePayload 內容寫入 _edited.json。
    payload 需有 filename, speaker_mapping, segments（可為 Pydantic 或 dict）。
    回傳 {"status": "success", "saved_to": rel_path, "filename": new_filename}。
    """
    full_path = get_real_path(payload.filename)
    directory = os.path.dirname(full_path)
    filename = os.path.basename(full_path)
    core_name = (
        filename.replace("_flagged_for_human.json", "")
        .replace("_edited.json", "")
        .replace("_aligned.json", "")
        .replace("_stitched.json", "")
        .replace("_verified_dataset.json", "")
        .replace(".json", "")
    )
    new_filename = f"{core_name}_edited.json"
    save_path = os.path.join(directory, new_filename)

    segments = payload.segments
    if not segments:
        segments_data = []
    elif hasattr(segments[0], "model_dump"):
        segments_data = [s.model_dump() for s in segments]
    elif hasattr(segments[0], "dict"):
        segments_data = [s.dict() for s in segments]
    else:
        segments_data = [dict(s) for s in segments]
    data_to_save = {
        "last_modified": datetime.now().isoformat(),
        "speaker_mapping": payload.speaker_mapping,
        "segments": segments_data,
    }
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(data_to_save, f, ensure_ascii=False, indent=2)

    relative_path = os.path.relpath(save_path, DATA_DIR).replace("\\", "/")
    return {
        "status": "success",
        "saved_to": relative_path,
        "filename": new_filename,
    }
