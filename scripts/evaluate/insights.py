"""
在 audit_case 之上產生「併句前 vs 併句後 vs GT」對照表、chunk 級洞見與 Markdown 報告。

用法（專案根目錄）:
  python -m core.scripts.evaluate.insights --case test
  python -m core.scripts.evaluate.insights --case test --markdown docs/test_insights.md
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


def _jiwer_tuple(block: Dict[str, Any]) -> Tuple[Optional[float], int, int, int]:
    j = block.get("jiwer_word_errors")
    if not j:
        return None, 0, 0, 0
    return (
        j.get("cer_as_char_wer"),
        int(j.get("insertions") or 0),
        int(j.get("deletions") or 0),
        int(j.get("substitutions") or 0),
    )


def _chunk_verdict(
    retention: Optional[float], missing_ids: int, aligned_seg_count: int
) -> str:
    if retention is None:
        return "無法計算（缺 aligned 或 post_stitch）"
    if retention < 0.70:
        return (
            "極度嚴重：規則併句後字元大幅萎縮，宜優先檢查併句／source_ids 完整性。"
        )
    if retention < 0.85 and missing_ids >= 50:
        return "嚴重漏句：字元保留率低且大量 aligned id 未被 stitch 引用。"
    if retention < 0.85:
        return "明顯字元流失：併句後顯著短於 aligned 串接。"
    if retention > 1.03:
        return (
            "字元數高於 aligned：可能為標點／贅字補入，或與合併策略有關；漏 id 仍請留意。"
        )
    if missing_ids >= 40:
        return "字元比尚可，但仍有大量 segment id 未被回收，請檢查併句批次與 source_ids 產生邏輯。"
    if missing_ids >= 15:
        return "輕度至中度 id 遺漏。"
    return "此 chunk 相對穩定。"


def attach_insights_layer(audit: Dict[str, Any]) -> Dict[str, Any]:
    """在既有 audit 報告上附加 insights（不修改原 chunks 結構）。"""
    chunks: List[Dict[str, Any]] = audit.get("chunks") or []
    gt = audit.get("ground_truth") or {}
    against = (gt.get("against") or {}) if isinstance(gt, dict) else {}

    pre = against.get("aligned_concat_pre_stitch") or {}
    post = against.get("final_transcript") or {}

    ref_chars = pre.get("reference_char_count")
    if ref_chars is None:
        ref_chars = post.get("reference_char_count")

    pre_hyp = pre.get("hypothesis_char_count")
    post_hyp = post.get("hypothesis_char_count")

    cer_pre, ins_pre, del_pre, sub_pre = _jiwer_tuple(pre)
    cer_post, ins_post, del_post, sub_post = _jiwer_tuple(post)

    del_ratio_vs_pre = (
        round((del_post / del_pre), 2) if del_pre and del_pre > 0 else None
    )
    cer_delta = (
        round(cer_post - cer_pre, 6)
        if cer_post is not None and cer_pre is not None
        else None
    )

    total_missing = 0
    chunk_rows: List[Dict[str, Any]] = []
    summary = audit.get("summary") or {}
    union_ids = summary.get("stitch_missing_ids_union") or []
    union_count = len(union_ids)
    for c in chunks:
        sc = c.get("stitch_id_coverage") or {}
        mc = int(sc.get("missing_count") or 0)
        total_missing += mc
        idx = c.get("chunk_index")
        stem = c.get("chunk_stem", "")
        ret = c.get("char_ratio_stitched_over_aligned")
        aligned_n = (c.get("aligned") or {}).get("segment_count")
        chunk_rows.append(
            {
                "chunk_index": idx,
                "chunk_stem": stem,
                "char_retention_stitch_over_aligned": ret,
                "aligned_segment_count": aligned_n,
                "missing_segment_ids": mc,
                "verdict": _chunk_verdict(
                    ret, mc, int(aligned_n or 0)
                ),
            }
        )

    whisper_covs = [
        (c.get("whisper") or {}).get("coverage_ratio")
        for c in chunks
        if (c.get("whisper") or {}).get("coverage_ratio") is not None
    ]
    avg_whisper_cov = (
        round(sum(whisper_covs) / len(whisper_covs), 4) if whisper_covs else None
    )

    gt_skipped = bool(gt.get("skipped"))

    narrative: List[str] = []
    if not gt_skipped and ref_chars and pre_hyp and post_hyp:
        loss_aligned_vs_gt_pct = round((1 - pre_hyp / ref_chars) * 100, 2)
        loss_final_vs_gt_pct = round((1 - post_hyp / ref_chars) * 100, 2)
        stitch_drop_pct = (
            round((1 - post_hyp / pre_hyp) * 100, 2) if pre_hyp > 0 else None
        )
        narrative.append(
            f"正規化後字數：GT {ref_chars}、併句前 {pre_hyp}、併句後 {post_hyp}。"
            f" 相對 GT，併句前缺口約 {loss_aligned_vs_gt_pct}%，併句後缺口約 {loss_final_vs_gt_pct}%。"
        )
        if stitch_drop_pct is not None:
            narrative.append(
                f"併句導致相對「aligned 全文」再萎縮約 {stitch_drop_pct}%（以字數計）。"
            )
    if cer_pre is not None and cer_post is not None:
        narrative.append(
            f"CER：併句前 {cer_pre:.4f} → 併句後 {cer_post:.4f}"
            + (f"（Δ {cer_delta:+.4f}）。" if cer_delta is not None else "。")
        )
    if del_pre and del_post:
        narrative.append(
            f"jiwer 刪除數：併句前 {del_pre} → 併句後 {del_post}"
            + (
                f"（約 {del_ratio_vs_pre:.1f}×）"
                if del_ratio_vs_pre is not None
                else ""
            )
            + "；刪除暴增通常表示對照 GT 時「假設稿變短」，與 stitch 吃字一致。"
        )
    id_note = (
        f"加總各 chunk missing_count = {total_missing}"
        + (
            f"，與 summary 聯集 id 數 {union_count} 一致。"
            if union_count == total_missing
            else f"；summary 聯集 id 數 {union_count}（若不一致請檢查重跑與快取檔）。"
        )
    )
    narrative.append(
        f"全案 stitch 未覆蓋的 aligned segment id：{id_note} "
        "併句前為物理串接 aligned，無 source_ids 遺失問題。"
    )
    if avg_whisper_cov is not None:
        narrative.append(
            f"各 chunk Whisper 時間覆蓋率平均約 {avg_whisper_cov:.2%}（VAD／小聲語音可能 contribution）。"
        )

    action_hints: List[str] = [
        "若 missing id 與字元保留率雙高：優先檢討規則併句條件（時間窗、同 speaker 合併閾值）與 `source_ids` 完整性。",
        "若併句前 CER 已可接受、併句後變差：可將「語意順稿」與「逐字繼承」拆階段，先保字再語意。",
        "實驗對照：以規則併句（同說話者＋時間接近）產生一版終稿，再對照本報告數值。",
    ]
    if total_missing > 50:
        action_hints.insert(
            0,
            "【高優先】目前未回收的 aligned id 數量偏高，建議在 stitch 失敗或漏 id 時直接採用 raw aligned 合併兜底。",
        )

    comparison_table = {
        "ground_truth_normalized_char_baseline": ref_chars,
        "pre_stitch_aligned_concat": {
            "label": "併句前（純 aligned 段落串接）",
            "normalized_hypothesis_chars": pre_hyp,
            "cer": cer_pre,
            "insertions": ins_pre,
            "deletions": del_pre,
            "substitutions": sub_pre,
            "difflib_ratio": pre.get("difflib_sequence_ratio"),
            "missing_aligned_segment_ids": 0,
            "missing_ids_note": "無 LLM 合併步驟，故無 source_ids 遺漏；全文 = 依時間排序之 aligned 串接。",
        },
        "post_stitch_final_transcript": {
            "label": "併句後（終稿 transcript.json，flagged 優先於 stitched）",
            "normalized_hypothesis_chars": post_hyp,
            "cer": cer_post,
            "insertions": ins_post,
            "deletions": del_post,
            "substitutions": sub_post,
            "difflib_ratio": post.get("difflib_sequence_ratio"),
            "missing_aligned_segment_ids_total": union_count or total_missing,
            "missing_ids_note": "各 chunk 上 stitched/flagged 之 `source_ids` 聯集未涵蓋之 aligned `id` 數加總。",
        },
        "delta": {
            "cer_post_minus_pre": cer_delta,
            "deletion_jiwer_post_over_pre_ratio": del_ratio_vs_pre,
            "interpretation": (
                "若 del 佔比暴增且字數下降，多半為併句刪內容而非單純 ASR 替換錯字。"
                if del_pre and del_post and del_post > del_pre * 1.5
                else None
            ),
        },
    }

    out = dict(audit)
    out["insights"] = {
        "comparison_table": comparison_table,
        "chunk_breakdown": chunk_rows,
        "narrative_bullets": narrative,
        "action_hints": action_hints,
        "metrics_note": (
            gt.get("normalize_note")
            if not gt_skipped
            else "未載入 ground truth，僅輸出 chunk 與 id 統計。"
        ),
    }
    return out


def render_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    case = report.get("case_name", "-")
    lines.append(f"# Pipeline insights：`{case}`\n")

    ins = report.get("insights") or {}
    ct = ins.get("comparison_table") or {}
    baseline = ct.get("ground_truth_normalized_char_baseline")
    pre = ct.get("pre_stitch_aligned_concat") or {}
    post = ct.get("post_stitch_final_transcript") or {}
    delta = ct.get("delta") or {}

    if baseline is None:
        lines.append(
            "> 未載入或未找到 ground truth，`--no-ground-truth` 時僅下列 chunk 級表格有效。\n"
        )

    if baseline is not None:
        lines.append("## 評估指標總覽（對人工稿正規化字串）\n")
        lines.append(
            "| **評估指標** | **併句前 (Aligned 串接)** | **併句後 (終稿)** | **備註** |"
        )
        lines.append("| --- | --- | --- | --- |")

        def _cell_chars(x):
            return str(x) if x is not None else "—"

        lines.append(
            f"| **總字數** (GT 基準: {baseline}) | {_cell_chars(pre.get('normalized_hypothesis_chars'))} | "
            f"{_cell_chars(post.get('normalized_hypothesis_chars'))} | "
            "正規化後僅漢字；見 `evaluate.md`。 |"
        )
        lines.append(
            f"| **字錯率 (CER)** | {_cell_chars(pre.get('cer'))} | {_cell_chars(post.get('cer'))} | "
            f"Δ {delta.get('cer_post_minus_pre') or '—'} |"
        )
        lines.append(
            f"| **Ins / Del / Sub** | {pre.get('insertions')}/{pre.get('deletions')}/{pre.get('substitutions')} | "
            f"{post.get('insertions')}/{post.get('deletions')}/{post.get('substitutions')} | "
            f"刪除倍率(post/pre): {delta.get('deletion_jiwer_post_over_pre_ratio') or '—'} |"
        )
        lines.append(
            f"| **difflib** | {pre.get('difflib_ratio')} | {post.get('difflib_ratio')} | |"
        )
        lines.append(
            f"| **遺失 aligned segment id** | {pre.get('missing_aligned_segment_ids')} | "
            f"{post.get('missing_aligned_segment_ids_total')} | {post.get('missing_ids_note', '')} |"
        )
        lines.append("")

    cb = ins.get("chunk_breakdown") or []
    if cb:
        lines.append("## 分 Chunk：字元保留率與 id 遺漏\n")
        lines.append(
            "| **Chunk** | **字元保留率 (終稿/aligned)** | **遺失 id 數** | **簡評** |"
        )
        lines.append("| --- | --- | --- | --- |")
        for row in cb:
            idx = row.get("chunk_index", "?")
            ret = row.get("char_retention_stitch_over_aligned")
            ret_s = f"{ret:.2%}" if isinstance(ret, (int, float)) else "—"
            lines.append(
                f"| **{idx}** | {ret_s} | {row.get('missing_segment_ids')} | {row.get('verdict')} |"
            )
        lines.append("")

    bullets = ins.get("narrative_bullets") or []
    if bullets:
        lines.append("## 自動摘要\n")
        for b in bullets:
            lines.append(f"- {b}")
        lines.append("")

    hints = ins.get("action_hints") or []
    if hints:
        lines.append("## 建議方向（依報告自動條列，須由人員取捨）\n")
        for h in hints:
            lines.append(f"- {h}")
        lines.append("")

    if report.get("error"):
        lines.append(f"> ⚠️ Audit 警告：`{report['error']}`\n")

    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Pipeline 洞見報告（併句前後對照、chunk 表、Markdown）"
    )
    p.add_argument("--case", required=True)
    p.add_argument("--ground-truth", default=None)
    p.add_argument("--no-ground-truth", action="store_true")
    p.add_argument("--json", default=None, help="寫出完整 JSON（含 audit + insights）")
    p.add_argument("--markdown", default=None, help="寫出 Markdown 報告")
    p.add_argument(
        "--quiet-md",
        action="store_true",
        help="只在寫檔時安靜執行，不在終端列印長表",
    )
    args = p.parse_args(argv)

    audit = audit_case(
        args.case,
        include_ground_truth=not args.no_ground_truth,
        ground_truth_path=args.ground_truth,
    )
    full = attach_insights_layer(audit)

    md = render_markdown(full)
    if not args.quiet_md:
        print(md)

    if args.json:
        outp = Path(args.json)
        outp.parent.mkdir(parents=True, exist_ok=True)
        with open(outp, "w", encoding="utf-8") as f:
            json.dump(full, f, ensure_ascii=False, indent=2)
        print(f"\n[JSON] {outp}", file=sys.stderr)

    if args.markdown:
        outp = Path(args.markdown)
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(md, encoding="utf-8")
        print(f"\n[Markdown] {outp}", file=sys.stderr)

    return 1 if full.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
