import pandas as pd
from pathlib import Path
import csv

def generate_local_reports():
    csv_path = Path("scripts/eda/result/EDA_Clinical_Advanced_Results.csv")
    mapping_path = Path("data_anonymization_mapping.csv")
    output_dir = Path("docs/eda/local")
    
    # Clean old reports
    if output_dir.exists():
        for f in output_dir.glob("*.md"):
            f.unlink()
    else:
        output_dir.mkdir(parents=True, exist_ok=True)

    if not csv_path.exists():
        print("Error: CSV results not found.")
        return

    # Load mapping
    mapping = {}
    with open(mapping_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mapping[row['original']] = row['anonymized']

    df = pd.read_csv(csv_path)

    for _, row in df.iterrows():
        original_name = row['case_name']
        sid = mapping.get(original_name, original_name)
        
        report_path = output_dir / f"{sid}.md"
        
        snr = row['snr_db']
        frag = row['fragmentation_ratio']
        speech = row['speech_ratio']
        pauses = row['num_long_pauses']
        bursts = row['energy_burst_ratio']
        pitch_std = row['std_pitch_hz']
        
        quality_score = 10
        if snr < 12: quality_score -= 2
        if frag > 0.6: quality_score -= 2
        if speech < 0.2: quality_score -= 2
        if pauses > 100: quality_score -= 1
        if bursts > 0.02: quality_score -= 1
        
        content = f"""# 個案分析報告：{sid}

## 1. 聲學與環境品質 (Acoustic & Environment Profiling)
- **訊噪比 (SNR):** {snr:.2f} dB ({"🔴 低 - 建議進行強效降噪" if snr < 12 else "🟢 良好"})
- **能量爆發 (Energy Bursts):** {bursts:.4f} ({"🔴 高 - 可能包含尖叫或音訊剪輯失真" if bursts > 0.02 else "🟢 正常"})
- **頻譜質心混亂度 (Chaos Ratio):** {row['chaos_ratio']:.4f} (重疊語音或干擾指標)

## 2. 語者特徵與發聲行為 (Speaker Characteristics & Vocalizations)
- **語音佔比 (Speech Ratio):** {speech:.2%} (整體說話時間比例)
- **語音破碎度 (Fragmentation Ratio):** {frag:.2%} (短於 1.5 秒的語句比例)
- **音高變異性 (Pitch Std Dev):** {pitch_std:.2f} Hz ({"🔴 高變異 - 可能存在非典型語調" if pitch_std > 120 else "🟢 正常範圍"})

## 3. 互動與語意動態 (Interaction & Overlapping Dynamics)
- **長沈默 (>2s):** {int(pauses)} 次 (反映互動延遲或無反應)
- **平均語句長度:** {row['avg_utterance_duration']:.2f} 秒

## 4. 下游影響與分析洞察 (Downstream Impact & Insights)
- **整體品質評分 (對 ASR/Diarization 友善度):** {quality_score}/10
- **主要風險:** {"⚠️ 轉錄失敗或 VAD 遺漏風險極高。" if quality_score < 7 else "✅ 適合標準流程處理，穩定度高。"}
- **處理建議:** {"建議套用頻譜減法並調整 VAD 門檻。" if snr < 12 or speech < 0.2 else "建議使用標準處理管線。"}

---
*由自動化 EDA 模組生成*
"""
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(content)
            
    print(f"Generated {len(df)} anonymized local reports in {output_dir}")

if __name__ == "__main__":
    generate_local_reports()
