#!/usr/bin/env python3
"""
ASR & Speaker Diarization Pipeline Evaluation Script
評估 ASR 與 Speaker Diarization 管線的準確率。

使用方法:
  1. 指定受試者評估 (輸出至 docs/eda/error/):
     python scripts/eda/evaluate_pipeline.py -s subject01
     python scripts/eda/evaluate_pipeline.py -s all

  2. 單一檔案配對評估:
     python scripts/eda/evaluate_pipeline.py -pred data/pred.json -gt data/gt.json
  
  3. 目錄批量評估:
     python scripts/eda/evaluate_pipeline.py -dir data/subject01/intermediate
"""

import argparse
import json
import sys
import os
from pathlib import Path
from datetime import datetime

try:
    import jiwer
except ImportError:
    print("錯誤: 需要安裝 'jiwer' 函式庫以計算 WER。請執行: pip install jiwer")
    sys.exit(1)

# 嘗試載入 rich 以美化終端機輸出，若無則降級使用一般 print
try:
    from rich.console import Console
    from rich.table import Table
    console = Console()
except ImportError:
    console = None

def load_segments(filepath: Path) -> list:
    """載入 JSON 並提取 segments 陣列"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 根據專案結構，可能是帶有 "segments" 的物件，也可能是純陣列
        if isinstance(data, dict):
            return data.get("segments", [])
        elif isinstance(data, list):
            return data
        else:
            return []
    except Exception as e:
        print(f"載入檔案失敗 {filepath}: {e}")
        return []

def format_for_chinese_wer(text: str) -> str:
    """
    對中文進行字元切割 (Character-level split)，因為中文通常沒有空格。
    在不分詞的情況下，插入空格計算出來的 WER 等同於 CER (Character Error Rate)，
    這是中文語音辨識的標準評估方式。
    """
    if not text:
        return ""
    # 去除原始空格與全形空格
    text = text.replace(" ", "").replace("　", "")
    # 將每個字元以空格連接
    return " ".join(list(text))

def evaluate_pair(pred_path: Path, gt_path: Path, report_file) -> dict:
    """評估單一一對預測與真實檔案，並將錯誤細節寫入報告"""
    pred_segments = load_segments(pred_path)
    gt_segments = load_segments(gt_path)

    report_file.write(f"\n{'='*60}\n")
    report_file.write(f"評估檔案:\n")
    report_file.write(f"  [Pred] {pred_path}\n")
    report_file.write(f"  [GT]   {gt_path}\n")
    report_file.write(f"{'-'*60}\n")

    # 1. 遺漏/多餘 偵測 (Segment Mismatch)
    len_pred = len(pred_segments)
    len_gt = len(gt_segments)
    mismatch_warning = ""
    if len_pred != len_gt:
        mismatch_warning = f"⚠️ [警告] Segment 數量不一致! Pred: {len_pred}, GT: {len_gt}"
        if console:
            console.print(f"[yellow]{mismatch_warning}[/yellow]")
        else:
            print(mismatch_warning)
        report_file.write(f"{mismatch_warning}\n\n")

    # 2. 字錯率計算準備 (WER)
    # 將 pred 和 gt 中所有 segments 的 text 分別依序拼接成一個長字串
    pred_full_text = " ".join([seg.get("text", "") for seg in pred_segments])
    gt_full_text = " ".join([seg.get("text", "") for seg in gt_segments])

    pred_wer_format = format_for_chinese_wer(pred_full_text)
    gt_wer_format = format_for_chinese_wer(gt_full_text)

    wer_score = 0.0
    if gt_wer_format:
        wer_score = jiwer.wer(gt_wer_format, pred_wer_format)
    
    # 3. 語者標籤準確率 (Speaker Accuracy) - 基於時間對齊 (Time-based overlap)
    correct_speakers = 0
    speaker_mismatches = []
    text_mismatches = []
    total_aligned = 0

    for p_idx, p_seg in enumerate(pred_segments):
        p_start = p_seg.get("start", 0)
        p_end = p_seg.get("end", 0)
        p_spk = p_seg.get("speaker", "")
        p_txt = p_seg.get("text", "")

        # 找尋時間重疊最多的 GT segment
        max_overlap = 0
        best_g_seg = None
        best_g_idx = -1

        for g_idx, g_seg in enumerate(gt_segments):
            g_start = g_seg.get("start", 0)
            g_end = g_seg.get("end", 0)

            overlap_start = max(p_start, g_start)
            overlap_end = min(p_end, g_end)
            overlap = max(0, overlap_end - overlap_start)

            if overlap > max_overlap:
                max_overlap = overlap
                best_g_seg = g_seg
                best_g_idx = g_idx

        if best_g_seg is not None and max_overlap > 0:
            total_aligned += 1
            g_spk = best_g_seg.get("speaker", "")
            g_txt = best_g_seg.get("text", "")

            if p_spk == g_spk:
                correct_speakers += 1
            else:
                speaker_mismatches.append((p_idx, best_g_idx, p_spk, g_spk, p_start, p_end))
            
            if p_txt != g_txt:
                text_mismatches.append((p_idx, best_g_idx, p_txt, g_txt, p_start, p_end))

    speaker_acc = (correct_speakers / total_aligned) if total_aligned > 0 else 0.0

    # 寫入詳細報告 (僅保留洞察與統計數據，不包含敏感的逐字內容)
    report_file.write(f"【整體指標】\n")
    report_file.write(f" - WER (字錯率): {wer_score:.2%}\n")
    report_file.write(f" - Speaker Accuracy (語者準確率 - 基於時間對齊): {speaker_acc:.2%} ({correct_speakers}/{total_aligned})\n")
    report_file.write(f" - 成功時間對齊的 Segment 數量: {total_aligned}\n\n")
    report_file.write(f"※ 註：為保護敏感資料，詳細的文字與語者對應錯誤紀錄已不寫入本報告，僅於終端機顯示。\n\n")

    # 輸出細節至 Terminal (不寫入檔案，僅供終端預覽)
    if speaker_mismatches or text_mismatches:
        print_func = console.print if console else print
        print_func(f"\n[bold cyan][{pred_path.name}] 的不一致細節 (僅顯示於終端機):[/bold cyan]" if console else f"\n[{pred_path.name}] 的不一致細節 (僅顯示於終端機):")
        
        if speaker_mismatches:
            print_func("[yellow]  【語者標籤錯誤紀錄】[/yellow]" if console else "  【語者標籤錯誤紀錄】")
            for m in speaker_mismatches:
                print_func(f"    [Pred {m[0]} -> GT {m[1]}] Time: {m[4]:.2f}-{m[5]:.2f} | Pred Spk: '{m[2]}' | GT Spk: '{m[3]}'")
        
        if text_mismatches:
            print_func("[yellow]  【文字不一致紀錄】[/yellow]" if console else "  【文字不一致紀錄】")
            for m in text_mismatches:
                print_func(f"    [Pred {m[0]} -> GT {m[1]}] Time: {m[4]:.2f}-{m[5]:.2f}\n      Pred: {m[2]}\n      GT:   {m[3]}")
        print_func("-" * 60)

    return {
        "file": pred_path.name,
        "wer": wer_score,
        "speaker_acc": speaker_acc,
        "correct_speakers": correct_speakers,
        "total_speakers_checked": total_aligned,
        "mismatch": len_pred != len_gt
    }

def print_summary(results: list):
    """將結果格式化並以表格形式印出在終端機"""
    if not results:
        print("沒有可用的評估結果。")
        return

    # 計算平均值
    avg_wer = sum(r["wer"] for r in results) / len(results)
    total_correct_spk = sum(r["correct_speakers"] for r in results)
    total_spk_checked = sum(r["total_speakers_checked"] for r in results)
    avg_spk_acc = (total_correct_spk / total_spk_checked) if total_spk_checked > 0 else 0.0

    if console:
        table = Table(title="📊 管線評估報告 (Pipeline Evaluation Report)")
        table.add_column("檔案 (File)", style="cyan", no_wrap=True)
        table.add_column("WER (字錯率)", justify="right", style="magenta")
        table.add_column("Speaker Acc", justify="right", style="green")
        table.add_column("Seg Mismatch?", justify="center", style="yellow")

        for res in results:
            mismatch_str = "[red]Yes[/red]" if res["mismatch"] else "No"
            table.add_row(
                res["file"],
                f"{res['wer']:.2%}",
                f"{res['speaker_acc']:.2%}",
                mismatch_str
            )
        
        console.print(table)
        console.print(f"\n🎯 [bold]整體平均 (Overall)[/bold]")
        console.print(f" - 平均 WER: [magenta]{avg_wer:.2%}[/magenta]")
        console.print(f" - 整體語者準確率: [green]{avg_spk_acc:.2%}[/green] ({total_correct_spk}/{total_spk_checked})\n")
    else:
        print("\n" + "="*50)
        print(f"{'管線評估報告':^46}")
        print("="*50)
        print(f"{'檔案':<30} | {'WER':<8} | {'Spk Acc':<9} | {'Mismatch'}")
        print("-" * 60)
        for res in results:
            mismatch_str = "Yes" if res["mismatch"] else "No"
            print(f"{res['file']:<30} | {res['wer']:>7.2%} | {res['speaker_acc']:>8.2%} | {mismatch_str}")
        print("="*50)
        print("整體平均 (Overall):")
        print(f" - 平均 WER: {avg_wer:.2%}")
        print(f" - 整體語者準確率: {avg_spk_acc:.2%} ({total_correct_spk}/{total_spk_checked})")
        print("="*50)

def main():
    parser = argparse.ArgumentParser(description="評估 ASR 與 Speaker Diarization 預測結果。")
    parser.add_argument("-s", "--subject", type=str, help="指定受試者資料夾名稱 (例如: subject01, subject21, 或 'all' 評估所有)")
    parser.add_argument("-pred", type=str, help="預測 JSON 檔案的路徑 (_flagged_for_human.json)")
    parser.add_argument("-gt", type=str, help="Ground Truth JSON 檔案的路徑 (_edited.json)")
    parser.add_argument("-dir", type=str, help="目錄路徑，將自動尋找並配對檔案進行批量評估")
    parser.add_argument("-o", "--output", type=str, help="自訂輸出報告檔案的完整路徑 (覆蓋預設行為)")

    args = parser.parse_args()

    pairs = []
    report_filename = "evaluation_report.txt"
    
    # 決定輸出目錄 (預設為 docs/eda/error)
    output_dir = Path("docs/eda/error")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if args.subject:
        data_dir = Path("data")
        if not data_dir.exists():
            print(f"錯誤: 找不到資料目錄 {data_dir.absolute()}")
            sys.exit(1)
            
        if args.subject.lower() == "all":
            search_dirs = [d for d in data_dir.iterdir() if d.is_dir()]
            report_filename = "all_subjects_evaluation_report.txt"
        else:
            search_dirs = [data_dir / args.subject]
            report_filename = f"{args.subject}_evaluation_report.txt"
            
        for d_path in search_dirs:
            if not d_path.exists():
                print(f"⚠️ 找不到目錄 {d_path}，跳過...")
                continue
            print(f"🔍 在 {d_path} 搜尋配對檔案...")
            for gt_file in d_path.rglob("*_edited.json"):
                pred_file = gt_file.parent / gt_file.name.replace("_edited.json", "_flagged_for_human.json")
                if pred_file.exists():
                    pairs.append((pred_file, gt_file))
                else:
                    # Fallback
                    for alt_suffix in ["_verified_dataset.json", "_stitched.json"]:
                        alt_pred = gt_file.parent / gt_file.name.replace("_edited.json", alt_suffix)
                        if alt_pred.exists():
                            pairs.append((alt_pred, gt_file))
                            break
                    else:
                        # Fallback for full concatenated transcript
                        if (gt_file.parent / "transcript.json").exists():
                            pairs.append((gt_file.parent / "transcript.json", gt_file))
                        elif (gt_file.parent / "final_transcript.json").exists():
                            pairs.append((gt_file.parent / "final_transcript.json", gt_file))
                        elif (gt_file.parent.parent / "output" / "transcript.json").exists():
                            pairs.append((gt_file.parent.parent / "output" / "transcript.json", gt_file))
                        elif (gt_file.parent.parent / "output" / "final_transcript.json").exists():
                            pairs.append((gt_file.parent.parent / "output" / "final_transcript.json", gt_file))
                            
    elif args.dir:
        dir_path = Path(args.dir)
        if not dir_path.is_dir():
            print(f"錯誤: 目錄 {args.dir} 不存在。")
            sys.exit(1)
            
        report_filename = f"{dir_path.name}_evaluation_report.txt"
        print(f"🔍 在 {dir_path} 搜尋配對檔案...")
        for gt_file in dir_path.rglob("*_edited.json"):
            pred_file = gt_file.parent / gt_file.name.replace("_edited.json", "_flagged_for_human.json")
            if pred_file.exists():
                pairs.append((pred_file, gt_file))
            else:
                for alt_suffix in ["_verified_dataset.json", "_stitched.json", "transcript.json"]:
                    alt_pred = gt_file.parent / gt_file.name.replace("_edited.json", alt_suffix)
                    if alt_pred.exists():
                        pairs.append((alt_pred, gt_file))
                        break
                        
    elif args.pred and args.gt:
        pred_path = Path(args.pred)
        gt_path = Path(args.gt)
        if not pred_path.exists():
            print(f"錯誤: Pred 檔案 {args.pred} 不存在。")
            sys.exit(1)
        if not gt_path.exists():
            print(f"錯誤: GT 檔案 {args.gt} 不存在。")
            sys.exit(1)
        pairs.append((pred_path, gt_path))
        report_filename = "single_evaluation_report.txt"
    else:
        parser.print_help()
        sys.exit(1)

    if not pairs:
        print("❌ 找不到任何可評估的 Pred/GT 配對檔案。")
        sys.exit(1)

    print(f"✅ 找到 {len(pairs)} 對檔案，開始評估...\n")

    # 決定最終輸出路徑
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        output_path = output_dir / report_filename

    results = []
    with open(output_path, "w", encoding="utf-8") as report_file:
        report_file.write(f"NeuroAI 管線評估報告 (Pipeline Evaluation Report)\n")
        report_file.write(f"產生時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        report_file.write(f"評估數量: {len(pairs)} 對檔案\n")
        
        for p_file, g_file in pairs:
            res = evaluate_pair(p_file, g_file, report_file)
            results.append(res)
    
    # 輸出統整表格到終端機
    print_summary(results)
    print(f"📄 詳細錯誤報告已儲存至: [ {output_path.absolute()} ]")

if __name__ == "__main__":
    main()
