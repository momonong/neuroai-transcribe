"""
比較兩個 case（例如 data/test vs data/test1）的 pipeline 成果，輸出 Markdown。

用途：
- 快速比較兩次跑出來的品質指標（CER、字數、missing id、Unknown ratio…）
- 產生可貼到 issue/報告的 Markdown 表格

用法（專案根目錄）：
  python -m core.scripts.evaluate.compare_cases --case-a test --case-b test1
  python -m core.scripts.evaluate.compare_cases --case-a test --case-b test1 --markdown data/compare_test_vs_test1.md

備註：
- 指標來源與 `core.scripts.evaluate.audit` / `core.scripts.evaluate.insights` 一致。
- 若任一 case 沒有 ground truth（預設 data/<case>/edited.json），CER 等欄位會是 "—"。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.scripts.evaluate.audit import audit_case
from core.scripts.evaluate.insights import attach_insights_layer


def _get(d: Dict[str, Any], path: List[str], default: Any = None) -> Any:
    cur: Any = d
    for k in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return cur if cur is not None else default


def _cell(x: Any) -> str:
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:.6g}"
    return str(x)


def _pct(x: Any) -> str:
    if isinstance(x, (int, float)):
        return f"{x:.2%}"
    return "—"


def _delta_num(a: Any, b: Any) -> str:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        d = b - a
        if isinstance(d, float):
            return f"{d:+.6g}"
        return f"{d:+d}"
    return "—"


def _load_full(case: str, *, include_ground_truth: bool, ground_truth_path: Optional[str]) -> Dict[str, Any]:
    audit = audit_case(case, include_ground_truth=include_ground_truth, ground_truth_path=ground_truth_path)
    return attach_insights_layer(audit)


def _case_header(full: Dict[str, Any]) -> str:
    case = full.get("case_name", "-")
    err = full.get("error")
    if err:
        return f"- `{case}`: ⚠️ `{err}`"
    return f"- `{case}`: OK"


def render_compare_markdown(
    a_full: Dict[str, Any],
    b_full: Dict[str, Any],
    *,
    label_a: str,
    label_b: str,
) -> str:
    lines: List[str] = []
    a_case = a_full.get("case_name", "A")
    b_case = b_full.get("case_name", "B")

    lines.append(f"# Pipeline case compare：`{a_case}` vs `{b_case}`\n")
    lines.append("## 狀態\n")
    lines.append(_case_header(a_full))
    lines.append(_case_header(b_full))
    lines.append("")

    # ===== Summary table (post-stitch / final transcript based) =====
    lines.append("## 指標總覽（以終稿 transcript.json 為準；若有 GT 則包含 CER）\n")
    lines.append(f"| **指標** | **{label_a}** | **{label_b}** | **Δ ({label_b}-{label_a})** |")
    lines.append("| --- | --- | --- | --- |")

    # Post-stitch / final transcript metrics (from insights comparison table)
    a_ct = _get(a_full, ["insights", "comparison_table"], {}) or {}
    b_ct = _get(b_full, ["insights", "comparison_table"], {}) or {}
    a_post = (a_ct.get("post_stitch_final_transcript") or {}) if isinstance(a_ct, dict) else {}
    b_post = (b_ct.get("post_stitch_final_transcript") or {}) if isinstance(b_ct, dict) else {}

    # Baseline / GT
    a_gt_chars = a_ct.get("ground_truth_normalized_char_baseline") if isinstance(a_ct, dict) else None
    b_gt_chars = b_ct.get("ground_truth_normalized_char_baseline") if isinstance(b_ct, dict) else None
    lines.append(f"| **GT 基準字數（正規化）** | {_cell(a_gt_chars)} | {_cell(b_gt_chars)} | — |")

    a_chars = a_post.get("normalized_hypothesis_chars")
    b_chars = b_post.get("normalized_hypothesis_chars")
    lines.append(f"| **終稿字數（正規化）** | {_cell(a_chars)} | {_cell(b_chars)} | {_delta_num(a_chars, b_chars)} |")

    a_cer = a_post.get("cer")
    b_cer = b_post.get("cer")
    lines.append(f"| **CER** | {_cell(a_cer)} | {_cell(b_cer)} | {_delta_num(a_cer, b_cer)} |")

    # jiwer components if present
    a_ins = a_post.get("insertions")
    a_del = a_post.get("deletions")
    a_sub = a_post.get("substitutions")
    b_ins = b_post.get("insertions")
    b_del = b_post.get("deletions")
    b_sub = b_post.get("substitutions")
    lines.append(
        f"| **Ins/Del/Sub** | {_cell(a_ins)}/{_cell(a_del)}/{_cell(a_sub)} | "
        f"{_cell(b_ins)}/{_cell(b_del)}/{_cell(b_sub)} | — |"
    )

    a_missing = a_post.get("missing_aligned_segment_ids_total")
    b_missing = b_post.get("missing_aligned_segment_ids_total")
    lines.append(
        f"| **遺失 aligned segment id（終稿）** | {_cell(a_missing)} | {_cell(b_missing)} | {_delta_num(a_missing, b_missing)} |"
    )

    # Audit summary level metrics
    a_sum = a_full.get("summary") or {}
    b_sum = b_full.get("summary") or {}
    a_chunks = _cell(a_sum.get("chunk_count") or a_full.get("chunk_count"))
    b_chunks = _cell(b_sum.get("chunk_count") or b_full.get("chunk_count"))
    lines.append(f"| **chunk 數** | {a_chunks} | {b_chunks} | — |")

    # Avg whisper coverage
    def _avg_whisper_cov(full: Dict[str, Any]) -> Optional[float]:
        bullets = _get(full, ["insights", "narrative_bullets"], []) or []
        # narrative already contains avg whisper coverage, but parsing text is fragile; compute from chunks instead.
        covs: List[float] = []
        for c in full.get("chunks") or []:
            r = _get(c, ["whisper", "coverage_ratio"])
            if isinstance(r, (int, float)):
                covs.append(float(r))
        if not covs:
            return None
        return sum(covs) / len(covs)

    a_cov = _avg_whisper_cov(a_full)
    b_cov = _avg_whisper_cov(b_full)
    lines.append(f"| **Whisper 覆蓋率平均** | {_pct(a_cov)} | {_pct(b_cov)} | {_delta_num(a_cov, b_cov)} |")

    # Unknown ratio avg
    def _avg_unknown(full: Dict[str, Any]) -> Optional[float]:
        rs: List[float] = []
        for c in full.get("chunks") or []:
            r = _get(c, ["aligned", "unknown_speaker_ratio"])
            if isinstance(r, (int, float)):
                rs.append(float(r))
        if not rs:
            return None
        return sum(rs) / len(rs)

    a_unk = _avg_unknown(a_full)
    b_unk = _avg_unknown(b_full)
    lines.append(f"| **Aligned Unknown ratio 平均** | {_pct(a_unk)} | {_pct(b_unk)} | {_delta_num(a_unk, b_unk)} |")
    lines.append("")

    # ===== Chunk table =====
    lines.append("## 分 chunk 對照（終稿/aligned 字元比、missing id、Unknown）\n")
    lines.append(
        f"| **Chunk** | **{label_a} retention** | **{label_b} retention** | "
        f"**{label_a} missing** | **{label_b} missing** | "
        f"**{label_a} Unknown** | **{label_b} Unknown** |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")

    def _index_map(full: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
        m: Dict[int, Dict[str, Any]] = {}
        for c in full.get("chunks") or []:
            idx = c.get("chunk_index")
            if isinstance(idx, int):
                m[idx] = c
        return m

    am = _index_map(a_full)
    bm = _index_map(b_full)
    all_idx = sorted(set(am.keys()) | set(bm.keys()))
    for idx in all_idx:
        ca = am.get(idx) or {}
        cb = bm.get(idx) or {}
        a_ret = ca.get("char_ratio_stitched_over_aligned")
        b_ret = cb.get("char_ratio_stitched_over_aligned")
        a_m = _get(ca, ["stitch_id_coverage", "missing_count"])
        b_m = _get(cb, ["stitch_id_coverage", "missing_count"])
        a_u = _get(ca, ["aligned", "unknown_speaker_ratio"])
        b_u = _get(cb, ["aligned", "unknown_speaker_ratio"])
        lines.append(
            f"| **{idx}** | {_pct(a_ret)} | {_pct(b_ret)} | {_cell(a_m)} | {_cell(b_m)} | {_pct(a_u)} | {_pct(b_u)} |"
        )
    lines.append("")

    # ===== Raw links =====
    lines.append("## 產物路徑提示\n")
    lines.append(f"- `{label_a}`: `data/{a_case}/output/transcript.json`、`data/{a_case}/intermediate/`")
    lines.append(f"- `{label_b}`: `data/{b_case}/output/transcript.json`、`data/{b_case}/intermediate/`")
    lines.append("")

    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="比較兩個 case 的 pipeline 成果，輸出 Markdown")
    p.add_argument("--case-a", required=True)
    p.add_argument("--case-b", required=True)
    p.add_argument("--label-a", default=None, help="表格顯示用名稱（預設同 case-a）")
    p.add_argument("--label-b", default=None, help="表格顯示用名稱（預設同 case-b）")
    p.add_argument("--ground-truth-a", default=None, help="A 的 GT 路徑（預設 data/<case>/edited.json）")
    p.add_argument("--ground-truth-b", default=None, help="B 的 GT 路徑（預設 data/<case>/edited.json）")
    p.add_argument("--no-ground-truth", action="store_true", help="兩邊都不載入 GT（只做結構稽核）")
    p.add_argument("--json", default=None, help="輸出完整 JSON（含兩邊 audit+insights）")
    p.add_argument("--markdown", default=None, help="寫出 Markdown 檔")
    p.add_argument(
        "--quiet",
        action="store_true",
        help="不在終端列印 Markdown（避免 Windows cp950 亂碼）；僅在有指定 --markdown 時輸出檔案路徑",
    )
    args = p.parse_args(argv)

    inc_gt = not args.no_ground_truth
    a_full = _load_full(args.case_a, include_ground_truth=inc_gt, ground_truth_path=args.ground_truth_a)
    b_full = _load_full(args.case_b, include_ground_truth=inc_gt, ground_truth_path=args.ground_truth_b)

    md = render_compare_markdown(
        a_full,
        b_full,
        label_a=args.label_a or args.case_a,
        label_b=args.label_b or args.case_b,
    )
    if not args.quiet:
        print(md)

    if args.json:
        outp = Path(args.json)
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(
            json.dumps({"a": a_full, "b": b_full}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n[JSON] {outp}", file=sys.stderr)

    if args.markdown:
        outp = Path(args.markdown)
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(md, encoding="utf-8")
        print(f"\n[Markdown] {outp}", file=sys.stderr)

    return 1 if a_full.get("error") or b_full.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())

