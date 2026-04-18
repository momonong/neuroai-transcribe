from typing import Any, Dict, List, Optional
import re

from core.config import config


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def aligned_to_stitch_shape(aligned: List[dict]) -> List[dict]:
    """
    將 alignment 段落轉成與 stitch 輸出相同欄位。
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
    
    merged_text = ""
    for i, seg in enumerate(run):
        text = (seg.get("text") or "").strip()
        if not merged_text:
            merged_text = text
        else:
            if re.search(r"[\u4e00-\u9fa5]$", merged_text) and re.match(r"^[\u4e00-\u9fa5]", text):
                merged_text += text
            else:
                merged_text += " " + text
                
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


def merge_aligned_segments(
    aligned: List[dict], 
    *, 
    max_gap_sec: float = 1.5,
    max_chars: int = 80,
    soft_max_chars: int = 40,
    soft_gap_sec: float = 0.5
) -> List[dict]:
    if not aligned:
        return []

    merged: List[Dict[str, Any]] = []
    current_run: List[Dict[str, Any]] = [aligned[0]]
    current_chars = len(str(aligned[0].get("text") or ""))

    # 標點符號
    sentence_endings = (u"。", u"！", u"？", u"!", u"?", u".")
    # 轉折詞/句首詞（如果下一句開頭是這些，且當前已有一點長度，傾向斷句）
    transition_starters = (
        "那", "那我", "那我們", "所以", "然後", "但是", "而且", 
        "可是", "因此", "不過", "那我們", "那假設"
    )

    for next_seg in aligned[1:]:
        prev_seg = current_run[-1]
        prev_text = (prev_seg.get("text") or "").strip()
        prev_speaker = str(prev_seg.get("speaker"))
        next_speaker = str(next_seg.get("speaker"))
        prev_end = _safe_float(prev_seg.get("end"))
        next_start = _safe_float(next_seg.get("start"))
        next_text = (next_seg.get("text") or "").strip()

        can_merge = False
        
        # 1. 語者必須相同
        if prev_speaker == next_speaker:
            # 2. 基本長度與標點檢查
            has_ending_punc = prev_text.endswith(sentence_endings)
            hard_length_exceeded = (current_chars + len(next_text)) > max_chars
            
            # 3. 轉折詞與軟性長度檢查
            starts_with_transition = next_text.startswith(transition_starters)
            is_fairly_long = current_chars >= soft_max_chars

            if prev_end is not None and next_start is not None:
                gap_sec = next_start - prev_end
                
                # 判斷是否應該斷開：
                # - 如果已經有結束標點 -> 斷
                # - 如果加上去太長 -> 斷
                # - 如果已經達到軟長度 (40字) 且停頓超過軟門檻 (0.5s) -> 斷
                # - 如果下一句是轉折詞 (那...) 且停頓超過軟門檻 -> 斷
                # - 如果停頓超過硬門檻 (1.5s) -> 斷
                
                should_break = (
                    has_ending_punc or 
                    hard_length_exceeded or
                    gap_sec > max_gap_sec or
                    (is_fairly_long and gap_sec > soft_gap_sec) or
                    (starts_with_transition and gap_sec > soft_gap_sec)
                )
                
                if not should_break:
                    can_merge = True

        if can_merge:
            current_run.append(next_seg)
            current_chars += len(next_text)
        else:
            merged.append(_build_merged_item(current_run, sentence_id=len(merged)))
            current_run = [next_seg]
            current_chars = len(next_text)

    merged.append(_build_merged_item(current_run, sentence_id=len(merged)))
    return merged


def run_stitching_logic(raw_data: List[dict]):
    print(f"🛡️ Starting Smarter Rule-based Stitch (Total: {len(raw_data)} segments)...")
    final_results = merge_aligned_segments(
        raw_data, 
        max_gap_sec=config.stitch_merge_max_gap_sec,
        max_chars=config.stitch_max_chars,
        soft_max_chars=config.stitch_soft_max_chars,
        soft_gap_sec=config.stitch_soft_gap_sec
    )
    print(f"✅ Smarter Stitch complete. ({len(final_results)} sentences)")
    return final_results
