from typing import Any, Dict, List, Optional

from core.config import config


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def aligned_to_stitch_shape(aligned: List[dict]) -> List[dict]:
    """
    將 alignment 段落轉成與 stitch 輸出相同欄位，供 Flag / transcript 沿用。
    一對一對應，不做任何併句。
    """
    final_results: List[dict] = []
    for idx, row in enumerate(aligned):
        sid = row.get("id")
        ids = [str(sid)] if sid is not None else []
        final_results.append(
            {
                "start": row.get("start"),
                "end": row.get("end"),
                "speaker": row.get("speaker", "Unknown"),
                "text": row.get("text") or "",
                "source_ids": ids,
                "verification_score": 1.0,
                "status": "NoStitch_Aligned",
                "sentence_id": idx,
            }
        )
    return final_results


def _build_merged_item(run: List[Dict[str, Any]], sentence_id: int) -> Dict[str, Any]:
    first = run[0]
    last = run[-1]
    source_ids = [str(seg.get("id")) for seg in run if seg.get("id") is not None]
    merged_text = "".join(seg.get("text") or "" for seg in run)
    status = "RuleStitch_Merged" if len(run) > 1 else "RuleStitch_Single"
    return {
        "start": first.get("start"),
        "end": last.get("end"),
        "speaker": first.get("speaker", "Unknown"),
        "text": merged_text,
        "source_ids": source_ids,
        "verification_score": 1.0,
        "status": status,
        "sentence_id": sentence_id,
    }


def merge_aligned_segments(aligned: List[dict], *, max_gap_sec: float = 1.5) -> List[dict]:
    if not aligned:
        return []

    merged: List[Dict[str, Any]] = []
    current_run: List[Dict[str, Any]] = [aligned[0]]

    for next_seg in aligned[1:]:
        prev_seg = current_run[-1]
        prev_speaker = str(prev_seg.get("speaker"))
        next_speaker = str(next_seg.get("speaker"))
        prev_end = _safe_float(prev_seg.get("end"))
        next_start = _safe_float(next_seg.get("start"))

        can_merge = False
        if prev_speaker == next_speaker and prev_end is not None and next_start is not None:
            gap_sec = next_start - prev_end
            can_merge = gap_sec <= max_gap_sec

        if can_merge:
            current_run.append(next_seg)
        else:
            merged.append(_build_merged_item(current_run, sentence_id=len(merged)))
            current_run = [next_seg]

    merged.append(_build_merged_item(current_run, sentence_id=len(merged)))
    return merged


def run_stitching_logic(raw_data: List[dict]):
    print(f"🛡️ Starting Rule-based Stitch (Total: {len(raw_data)} segments)...")
    final_results = merge_aligned_segments(
        raw_data, max_gap_sec=config.stitch_merge_max_gap_sec
    )
    print(f"✅ Rule-based Stitch complete. ({len(final_results)} sentences)")
    return final_results

