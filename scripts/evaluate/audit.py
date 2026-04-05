"""
掃描 data/<case>/intermediate 內各階段產物，輸出覆蓋率、缺漏 ID、簡繁指標等。

用法（專案根目錄）:
  python -m core.scripts.evaluate --case test
  python -m core.scripts.evaluate --case test --json data/test/output/pipeline_audit.json
  python -m core.scripts.evaluate --case test --ground-truth data/test/edited.json

預設會讀取 data/<case>/edited.json 與 output/transcript.json 做正規化後 CER（需 pip install jiwer）及 difflib 相似度；另會與 stitch 前 aligned 全文比對。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# 專案根目錄
_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shared.file_manager import file_manager

from core.scripts.evaluate.metrics_lib import (
    aligned_unknown_ratio,
    build_ground_truth_report,
    diar_turns,
    gaps_in_window,
    interval_union_seconds,
    load_json_list,
    merge_intervals,
    opencc_would_modify_stats,
    parse_chunk_wav_ms,
    stitch_id_coverage,
    total_text_chars,
    whisper_intervals,
)


def _try_opencc():
    try:
        from opencc import OpenCC

        return OpenCC("s2twp")
    except ImportError:
        return None


def discover_chunk_stems(inter_dir: Path) -> List[str]:
    stems = sorted({p.stem for p in inter_dir.glob("chunk_*.wav")})
    return stems


def _load_final_transcript_segments(case_name: str) -> List[Dict[str, Any]]:
    out_path = file_manager.get_output_file_path(case_name, "transcript.json")
    raw = file_manager.load_json(out_path)
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict) and isinstance(raw.get("segments"), list):
        return raw["segments"]
    return []


def audit_chunk(
    inter_dir: Path,
    stem: str,
    cc: Any,
) -> Dict[str, Any]:
    parsed = parse_chunk_wav_ms(stem)
    chunk_idx = start_ms = end_ms = None
    duration_sec = 0.0
    if parsed:
        chunk_idx, start_ms, end_ms = parsed
        duration_sec = max(0.0, (end_ms - start_ms) / 1000.0)

    w_path = inter_dir / f"{stem}_whisper.json"
    d_path = inter_dir / f"{stem}_diar.json"
    a_path = inter_dir / f"{stem}_aligned.json"
    s_path = inter_dir / f"{stem}_stitched.json"
    f_path = inter_dir / f"{stem}_flagged_for_human.json"

    whisper = load_json_list(w_path) or []
    diar = load_json_list(d_path) or []
    aligned = load_json_list(a_path) or []
    stitched = load_json_list(s_path) or []
    flagged = load_json_list(f_path) or []

    w_ivals = whisper_intervals(whisper)
    merged = merge_intervals(w_ivals)
    covered = interval_union_seconds(w_ivals)
    gaps = gaps_in_window(merged, 0.0, duration_sec) if duration_sec > 0 else []
    gap_seconds = sum(e - s for s, e in gaps)
    max_gap = max((e - s for s, e in gaps), default=0.0)

    whisper_texts = [str(x.get("text") or "") for x in whisper]
    aligned_texts = [str(x.get("text") or "") for x in aligned]
    post_stitch = flagged if flagged else stitched

    opencc_w = opencc_a = opencc_p = None
    if cc:
        c1, t1 = opencc_would_modify_stats(whisper_texts, cc)
        c2, t2 = opencc_would_modify_stats(aligned_texts, cc)
        pt = [str(x.get("text") or "") for x in post_stitch]
        c3, t3 = opencc_would_modify_stats(pt, cc)
        opencc_w = {"would_modify": c1, "total": t1}
        opencc_a = {"would_modify": c2, "total": t2}
        opencc_p = {"would_modify": c3, "total": t3}

    unk_n, unk_d, unk_r = aligned_unknown_ratio(aligned)
    stitch_report: Optional[Dict[str, Any]] = None
    if aligned and post_stitch:
        stitch_report = stitch_id_coverage(aligned, post_stitch)

    return {
        "chunk_stem": stem,
        "chunk_index": chunk_idx,
        "chunk_start_ms": start_ms,
        "chunk_end_ms": end_ms,
        "files": {
            "whisper": w_path.name,
            "diar": d_path.name,
            "aligned": a_path.name,
            "stitched": s_path.name,
            "flagged": f_path.name,
        },
        "file_exists": {
            "whisper": w_path.exists(),
            "diar": d_path.exists(),
            "aligned": a_path.exists(),
            "stitched": s_path.exists(),
            "flagged": f_path.exists(),
        },
        "whisper": {
            "segment_count": len(whisper),
            "duration_sec_from_filename": round(duration_sec, 3),
            "union_covered_sec": round(covered, 3),
            "coverage_ratio": round(covered / duration_sec, 4) if duration_sec > 0 else None,
            "gap_seconds_total": round(gap_seconds, 3),
            "max_gap_seconds": round(max_gap, 3),
            "char_count": total_text_chars(whisper),
            "opencc_would_modify": opencc_w,
        },
        "diarization": {
            "turn_count": diar_turns(diar),
        },
        "aligned": {
            "segment_count": len(aligned),
            "unknown_speaker_count": unk_n,
            "unknown_speaker_ratio": round(unk_r, 4),
            "char_count": total_text_chars(aligned),
            "opencc_would_modify": opencc_a,
        },
        "post_stitch": {
            "source": "flagged" if flagged else ("stitched" if stitched else None),
            "sentence_count": len(post_stitch),
            "char_count": total_text_chars(post_stitch),
            "opencc_would_modify": opencc_p,
        },
        "stitch_id_coverage": stitch_report,
        "char_ratio_stitched_over_aligned": (
            round(total_text_chars(post_stitch) / total_text_chars(aligned), 4)
            if aligned and total_text_chars(aligned) > 0
            else None
        ),
    }


def audit_case(
    case_name: str,
    *,
    include_ground_truth: bool = True,
    ground_truth_path: Optional[str] = None,
) -> Dict[str, Any]:
    inter_dir = file_manager.get_intermediate_dir(case_name)
    out_path = file_manager.get_output_file_path(case_name, "transcript.json")

    if not inter_dir.is_dir():
        report: Dict[str, Any] = {
            "case_name": case_name,
            "error": f"intermediate 不存在: {inter_dir}",
            "chunks": [],
            "chunk_count": 0,
            "intermediate_dir": str(inter_dir),
            "opencc_available": _try_opencc() is not None,
            "summary": {
                "chunks_with_aligned": 0,
                "chunks_missing_aligned": 0,
                "total_stitch_missing_ids": 0,
                "stitch_missing_ids_union": [],
                "output_transcript_json": str(out_path),
                "output_transcript_exists": out_path.exists(),
                "output_segment_count_list_or_wrapped": len(_load_final_transcript_segments(case_name)),
            },
        }
        if include_ground_truth:
            gt = (
                Path(ground_truth_path)
                if ground_truth_path
                else file_manager.get_case_dir(case_name) / "edited.json"
            )
            report["ground_truth"] = build_ground_truth_report(
                gt,
                _load_final_transcript_segments(case_name),
                None,
                [],
            )
        return report

    cc = _try_opencc()
    stems = discover_chunk_stems(inter_dir)
    chunks = [audit_chunk(inter_dir, s, cc) for s in stems]

    # 彙總
    total_missing_ids: List[str] = []
    for c in chunks:
        rep = c.get("stitch_id_coverage") or {}
        total_missing_ids.extend(rep.get("missing_ids") or [])

    final_exists = out_path.exists()
    final_segments = _load_final_transcript_segments(case_name)
    final_seg_count = len(final_segments)

    report = {
        "case_name": case_name,
        "intermediate_dir": str(inter_dir),
        "opencc_available": cc is not None,
        "chunk_count": len(stems),
        "chunks": chunks,
        "summary": {
            "chunks_with_aligned": sum(
                1 for c in chunks if c["file_exists"]["aligned"]
            ),
            "chunks_missing_aligned": sum(
                1 for c in chunks if not c["file_exists"]["aligned"]
            ),
            "total_stitch_missing_ids": len(total_missing_ids),
            "stitch_missing_ids_union": sorted(set(total_missing_ids)),
            "output_transcript_json": str(out_path),
            "output_transcript_exists": final_exists,
            "output_segment_count_list_or_wrapped": final_seg_count,
        },
    }
    if include_ground_truth:
        gt = (
            Path(ground_truth_path)
            if ground_truth_path
            else file_manager.get_case_dir(case_name) / "edited.json"
        )
        report["ground_truth"] = build_ground_truth_report(
            gt,
            final_segments,
            inter_dir,
            stems,
        )
    return report


def _print_report(report: Dict[str, Any]) -> None:
    if report.get("error"):
        print(report["error"])
        return
    print(f"案例: {report['case_name']}")
    print(f"intermediate: {report['intermediate_dir']}")
    print(f"OpenCC 可用: {report['opencc_available']}")
    print(f"chunk 數（由 chunk_*.wav）: {report['chunk_count']}")
    s = report["summary"]
    print(
        f"有 aligned 的 chunk: {s['chunks_with_aligned']} / "
        f"缺 aligned: {s['chunks_missing_aligned']}"
    )
    print(f"全案 stitch 漏掉的 segment id 數: {s['total_stitch_missing_ids']}")
    if s["stitch_missing_ids_union"]:
        print(f"  id 列表: {s['stitch_missing_ids_union'][:20]}{'...' if len(s['stitch_missing_ids_union']) > 20 else ''}")
    print(f"output/transcript.json 存在: {s['output_transcript_exists']}")
    print("--- 逐 chunk ---")
    for c in report["chunks"]:
        print(f"\n[{c['chunk_stem']}]")
        fe = c["file_exists"]
        print(
            f"  檔案 W/D/A/S/F: "
            f"{int(fe['whisper'])}{int(fe['diar'])}{int(fe['aligned'])}"
            f"{int(fe['stitched'])}{int(fe['flagged'])}"
        )
        w = c["whisper"]
        if w["coverage_ratio"] is not None:
            print(
                f"  Whisper 時間覆蓋率: {w['coverage_ratio']:.2%} "
                f"(覆蓋 {w['union_covered_sec']}s / chunk {w['duration_sec_from_filename']}s)"
            )
            print(
                f"  時間縫隙: 合計 {w['gap_seconds_total']}s, 最大單段 {w['max_gap_seconds']}s"
            )
        print(f"  Aligned: {c['aligned']['segment_count']} 段, Unknown 比例 {c['aligned']['unknown_speaker_ratio']:.2%}")
        om = c["aligned"].get("opencc_would_modify")
        pm = c["post_stitch"].get("opencc_would_modify")
        wm = c["whisper"].get("opencc_would_modify")
        if (wm and wm.get("total")) or (om and om.get("total")) or (pm and pm.get("total")):
            print(
                "  OpenCC 會改寫的筆數 (whisper / aligned / post_stitch): "
                f"{wm or {}} / {om or {}} / {pm or {}}"
            )
        sc = c.get("stitch_id_coverage")
        if sc:
            print(
                f"  Stitch ID: 缺 {sc['missing_count']} 個 aligned id, 多餘 id {sc['extra_count']}"
            )
        cr = c.get("char_ratio_stitched_over_aligned")
        if cr is not None:
            print(f"  字元數比 (post_stitch/aligned): {cr}")


def _print_ground_truth(report: Dict[str, Any]) -> None:
    gt = report.get("ground_truth")
    if not gt:
        return
    print("\n=== Ground truth（人工稿）比對 ===")
    if gt.get("skipped"):
        print(f"  已略過: {gt.get('reason', '')} ({gt.get('path', '')})")
        return
    print(f"  人工稿: {gt['path']}")
    print(f"  人工 segment 數: {gt['ground_truth_segment_count']}")
    for key, block in gt.get("against", {}).items():
        print(f"\n  [{key}] {block.get('description', '')}")
        print(
            f"    正規化後字數 — ref: {block.get('reference_char_count')}, "
            f"hyp: {block.get('hypothesis_char_count')}"
        )
        print(f"    difflib 相似度: {block.get('difflib_sequence_ratio')}")
        j = block.get("jiwer_word_errors")
        if j:
            print(
                f"    CER(字當作 word 的 jiwer): {j.get('cer_as_char_wer')} "
                f"(ins {j.get('insertions')} / del {j.get('deletions')} / sub {j.get('substitutions')})"
            )
        elif block.get("jiwer_note"):
            print(f"    {block.get('jiwer_note')}")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Pipeline intermediate metrics 稽核")
    p.add_argument("--case", required=True, help="案例名稱（data/<case>/）")
    p.add_argument(
        "--json",
        default=None,
        help="另存完整 JSON 報告路徑（可選）",
    )
    p.add_argument(
        "--ground-truth",
        default=None,
        help="人工 ground truth JSON（預設: data/<case>/edited.json）",
    )
    p.add_argument(
        "--no-ground-truth",
        action="store_true",
        help="不要比對人工稿",
    )
    args = p.parse_args(argv)

    report = audit_case(
        args.case,
        include_ground_truth=not args.no_ground_truth,
        ground_truth_path=args.ground_truth,
    )
    _print_report(report)
    _print_ground_truth(report)

    if args.json:
        outp = Path(args.json)
        outp.parent.mkdir(parents=True, exist_ok=True)
        with open(outp, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n已寫入 JSON: {outp}")

    return 1 if report.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
