"""
由 intermediate JSON / chunk 檔名計算指標的純函數（方便單元測試或匯入）。
"""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# chunk_1_0_60000.wav -> (0, 60000) 毫秒
_CHUNK_STEM_RE = re.compile(r"^chunk_(\d+)_(\d+)_(\d+)$")


def parse_chunk_wav_ms(stem: str) -> Optional[Tuple[int, int, int]]:
    m = _CHUNK_STEM_RE.match(stem)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def load_json_list(path: Path) -> Optional[List[Dict[str, Any]]]:
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else None
    except (json.JSONDecodeError, OSError):
        return None


def merge_intervals(intervals: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    if not intervals:
        return []
    srt = sorted(intervals, key=lambda x: (x[0], x[1]))
    merged: List[Tuple[float, float]] = [srt[0]]
    for s, e in srt[1:]:
        ps, pe = merged[-1]
        if s <= pe:
            merged[-1] = (ps, max(pe, e))
        else:
            merged.append((s, e))
    return merged


def interval_union_seconds(intervals: List[Tuple[float, float]]) -> float:
    return sum(max(0.0, e - s) for s, e in merge_intervals(intervals))


def gaps_in_window(
    merged: List[Tuple[float, float]], window_start: float, window_end: float
) -> List[Tuple[float, float]]:
    """在 [window_start, window_end] 內，合併區間之間的空隙。"""
    gaps: List[Tuple[float, float]] = []
    if window_end <= window_start:
        return gaps
    if not merged:
        return [(window_start, window_end)]
    t = window_start
    for s, e in merged:
        s = max(s, window_start)
        e = min(e, window_end)
        if s > t:
            gaps.append((t, min(s, window_end)))
        t = max(t, e)
    if t < window_end:
        gaps.append((t, window_end))
    return gaps


def whisper_intervals(segments: List[Dict[str, Any]]) -> List[Tuple[float, float]]:
    out: List[Tuple[float, float]] = []
    for seg in segments:
        try:
            s = float(seg["start"])
            e = float(seg["end"])
            if e > s:
                out.append((s, e))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def diar_turns(diar: List[Dict[str, Any]]) -> int:
    return len(diar) if diar else 0


def aligned_unknown_ratio(aligned: List[Dict[str, Any]]) -> Tuple[int, int, float]:
    n = len(aligned)
    if n == 0:
        return 0, 0, 0.0
    unk = sum(1 for x in aligned if str(x.get("speaker", "")) == "Unknown")
    return unk, n, unk / n


def stitch_id_coverage(
    aligned: List[Dict[str, Any]], stitched: List[Dict[str, Any]]
) -> Dict[str, Any]:
    ids_a = {str(x["id"]) for x in aligned if "id" in x}
    ids_s: set[str] = set()
    for row in stitched:
        for sid in row.get("source_ids") or []:
            ids_s.add(str(sid))
    missing = sorted(ids_a - ids_s)
    extra = sorted(ids_s - ids_a)
    return {
        "aligned_segment_count": len(ids_a),
        "referenced_ids_count": len(ids_s & ids_a),
        "missing_ids": missing,
        "missing_count": len(missing),
        "extra_ids": extra,
        "extra_count": len(extra),
    }


def total_text_chars(rows: List[Dict[str, Any]], key: str = "text") -> int:
    return sum(len(str(x.get(key) or "")) for x in rows)


def opencc_would_modify_stats(
    texts: List[str], cc: Any
) -> Tuple[int, int]:
    """若 cc.convert(t) != t 則計為一筆（可能含簡體或異體需轉換）。"""
    changed = 0
    for t in texts:
        if not t:
            continue
        try:
            if cc.convert(t) != t:
                changed += 1
        except Exception:
            continue
    return changed, len([t for t in texts if t])


# --- Ground truth（如 data/<case>/edited.json）與假設逐字稿比對 ---

_SPEAKER_PREFIX_RE = re.compile(
    r"(小孩|測試者|老師|Child|Therapist|Unknown)[:：]\s*",
    re.IGNORECASE,
)


def load_segments_from_project_json(path: Path) -> List[Dict[str, Any]]:
    """
    讀取 { \"segments\": [...] }、純 list，或其它含逐字欄位的 JSON。
    """
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        segs = data.get("segments")
        if isinstance(segs, list):
            return segs
    return []


def segments_concat_text(
    segments: List[Dict[str, Any]], sort_by_time: bool = True
) -> str:
    """依 start 排序後串接 text（與時間軸一致）。"""
    rows: List[Tuple[float, str]] = []
    for s in segments:
        t = str(s.get("text") or "").strip()
        if not t:
            continue
        try:
            st = float(s.get("start", 0) or 0)
        except (TypeError, ValueError):
            st = 0.0
        rows.append((st, t))
    if sort_by_time:
        rows.sort(key=lambda x: x[0])
    return "".join(txt for _, txt in rows)


def normalize_for_character_eval(text: str) -> str:
    """
    與專案內 wer_eval 類似：去掉角色前綴、只保留基本漢字範圍（CJK 統一漢字常用區）。
    """
    text = _SPEAKER_PREFIX_RE.sub("", text)
    text = re.sub(r"[^\u4e00-\u9fa5]", "", text)
    return text


def _chars_as_jiwer_words(s: str) -> str:
    return " ".join(list(s))


def reference_vs_hypothesis_metrics(
    reference_normalized: str, hypothesis_normalized: str
) -> Dict[str, Any]:
    """
    在「已正規化」的字串上計算 CER（以 jiwer 字元當 word）與 difflib 相似度。
    若未安裝 jiwer，僅回傳 difflib。
    """
    ref, hyp = reference_normalized, hypothesis_normalized
    out: Dict[str, Any] = {
        "reference_char_count": len(ref),
        "hypothesis_char_count": len(hyp),
        "difflib_sequence_ratio": round(difflib.SequenceMatcher(None, ref, hyp).ratio(), 6),
    }
    try:
        import jiwer

        if not ref and not hyp:
            out["jiwer_word_errors"] = {
                "cer_as_char_wer": 0.0,
                "hits": 0,
                "insertions": 0,
                "deletions": 0,
                "substitutions": 0,
            }
            return out
        measures = jiwer.process_words(
            _chars_as_jiwer_words(ref),
            _chars_as_jiwer_words(hyp),
        )
        mer_raw = getattr(measures, "mer", None)
        out["jiwer_word_errors"] = {
            "cer_as_char_wer": round(float(measures.wer), 6),
            "mer": round(float(mer_raw), 6) if mer_raw is not None else None,
            "hits": measures.hits,
            "insertions": measures.insertions,
            "deletions": measures.deletions,
            "substitutions": measures.substitutions,
        }
    except ImportError:
        out["jiwer_word_errors"] = None
        out["jiwer_note"] = "未安裝 jiwer，請 pip install jiwer 以取得 CER(insert/del/sub)"
    return out


def concat_aligned_chunks(inter_dir: Path, stems: List[str]) -> str:
    """依 chunk 順序串接所有 aligned 段落文字（stitch 前）。"""
    parts: List[str] = []
    for stem in stems:
        aligned = load_json_list(inter_dir / f"{stem}_aligned.json") or []
        parts.append(segments_concat_text(aligned, sort_by_time=True))
    return "".join(parts)


def build_ground_truth_report(
    gt_path: Path,
    segments_final: List[Dict[str, Any]],
    inter_dir: Optional[Path],
    stems: List[str],
) -> Dict[str, Any]:
    """
    將人工編修檔（如 edited.json）與 pipeline 輸出比對。
    """
    if not gt_path.exists():
        return {
            "skipped": True,
            "path": str(gt_path),
            "reason": "檔案不存在",
        }

    gt_segments = load_segments_from_project_json(gt_path)
    gt_text_raw = segments_concat_text(gt_segments, sort_by_time=True)
    gt_norm = normalize_for_character_eval(gt_text_raw)

    hyp_final_raw = segments_concat_text(segments_final, sort_by_time=True)
    hyp_final_norm = normalize_for_character_eval(hyp_final_raw)

    refs: Dict[str, Any] = {
        "final_transcript": {
            "description": "output/transcript.json（stitch+flag 後合併稿）",
            "segment_count_hypothesis": len(segments_final),
            **reference_vs_hypothesis_metrics(gt_norm, hyp_final_norm),
        }
    }

    if inter_dir and stems:
        aligned_raw = concat_aligned_chunks(inter_dir, stems)
        aligned_norm = normalize_for_character_eval(aligned_raw)
        refs["aligned_concat_pre_stitch"] = {
            "description": "全部 chunk 的 aligned 依序串接（LLM stitch 前）",
            **reference_vs_hypothesis_metrics(gt_norm, aligned_norm),
        }

    return {
        "skipped": False,
        "path": str(gt_path.resolve()),
        "ground_truth_segment_count": len(gt_segments),
        "normalize_note": "僅保留 \\u4e00-\\u9fa5，並移除特定說話者前綴；與 aaiml_paper/wer_eval 風格一致",
        "against": refs,
    }

