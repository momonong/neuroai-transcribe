"""
Segment 時間區間重新辨識（Whisper）掛鉤。

請在此模組實作實際音訊裁切與 Whisper 呼叫；目前僅回傳佔位結果，API 已就緒。
"""
from __future__ import annotations

from typing import Any


def run_segment_reinfer(
    *,
    case_name: str,
    chunk_filename: str,
    start_sec: float,
    end_sec: float,
    sentence_id: float | None,
) -> dict[str, Any]:
    """
    依 chunk 與 [start_sec, end_sec]（與 transcript JSON 內 segment 時間一致）執行重新辨識。

    實作建議：
    - 由 case_name / chunk_filename 解析出對應 wav 或影片路徑
    - 將 start_sec、end_sec 換算成音檔上的絕對時間（若需加上 chunk offset）
    - 呼叫 Whisper 後回傳 {"ok": True, "text": "...", "message": "..."}

    Returns:
        與 SegmentReinferResponse 對齊的 dict。
    """
    _ = (case_name, chunk_filename, start_sec, end_sec, sentence_id)
    return {
        "ok": True,
        "text": None,
        "message": "Whisper 重新辨識尚未接線：請在 backend/services/segment_reinfer.py 實作 run_segment_reinfer。",
    }
