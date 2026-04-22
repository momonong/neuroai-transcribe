import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# ==========================================
# 設定路徑與字型
# ==========================================
RESULTS_DIR = Path("scripts/eda/result")
OUTPUT_DIR = RESULTS_DIR / "analysis_report"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 若有中文字型需求，可在此設定，例如：
# plt.rcParams['font.sans-serif'] = ['Microsoft JhengHei'] 
# plt.rcParams['axes.unicode_minus'] = False

def load_data():
    basic_csv = RESULTS_DIR / "EDA_Results_Anonymized.csv"
    adv_csv = RESULTS_DIR / "EDA_Advanced_Results_Anonymized.csv"
    
    df_basic = pd.DataFrame()
    df_adv = pd.DataFrame()
    
    if basic_csv.exists():
        df_basic = pd.read_csv(basic_csv)
        print(f"✅ 載入基礎 EDA 結果: {len(df_basic)} 筆")
    else:
        print("⚠️ 找不到基礎 EDA 結果檔案")
        
    if adv_csv.exists():
        df_adv = pd.read_csv(adv_csv)
        print(f"✅ 載入進階 EDA 結果: {len(df_adv)} 筆")
    else:
        print("⚠️ 找不到進階 EDA 結果檔案")
        
    return df_basic, df_adv

def plot_distribution(df: pd.DataFrame, columns: list, title_prefix: str):
    print(f"📊 繪製分佈圖: {title_prefix}...")
    num_cols = len(columns)
    fig, axes = plt.subplots(math_ceil(num_cols/2), 2, figsize=(15, 4 * math_ceil(num_cols/2)))
    axes = axes.flatten()
    
    for i, col in enumerate(columns):
        if col in df.columns:
            sns.histplot(df[col], kde=True, ax=axes[i], color='skyblue')
            axes[i].set_title(f"Distribution of {col}")
            axes[i].set_xlabel("")
            axes[i].axvline(df[col].mean(), color='red', linestyle='dashed', linewidth=1, label=f"Mean: {df[col].mean():.2f}")
            axes[i].legend()
            
    # 移除多餘的空圖表
    for j in range(i + 1, len(axes)):
        fig.delaxes(axes[j])
        
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / f"{title_prefix}_distributions.png", dpi=300)
    plt.close()

def plot_correlation(df: pd.DataFrame, columns: list, title: str):
    print(f"🔗 繪製相關性熱力圖: {title}...")
    valid_cols = [c for c in columns if c in df.columns]
    
    if len(valid_cols) < 2:
        print("   -> 資料不足，跳過相關性分析")
        return
        
    corr = df[valid_cols].corr()
    
    plt.figure(figsize=(10, 8))
    sns.heatmap(corr, annot=True, cmap='coolwarm', vmin=-1, vmax=1, fmt=".2f", linewidths=.5)
    plt.title(f"Correlation Heatmap: {title}")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / f"{title}_correlation.png", dpi=300)
    plt.close()

def plot_scatter(df: pd.DataFrame, x_col: str, y_col: str):
    if x_col in df.columns and y_col in df.columns:
        print(f"📍 繪製散佈圖: {x_col} vs {y_col}...")
        plt.figure(figsize=(8, 6))
        sns.scatterplot(data=df, x=x_col, y=y_col, alpha=0.7, s=100, edgecolor="k")
        
        # 標示出極端值 (Subject ID)
        for i, row in df.iterrows():
            if row[x_col] > df[x_col].quantile(0.9) or row[y_col] > df[y_col].quantile(0.9):
                plt.text(row[x_col], row[y_col], row['case_name'], fontsize=9, alpha=0.7)
                
        plt.title(f"{x_col} vs {y_col}")
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / f"scatter_{x_col}_vs_{y_col}.png", dpi=300)
        plt.close()

def math_ceil(x):
    return int(-(-x // 1))

def main():
    df_basic, df_adv = load_data()
    
    if df_adv.empty:
        print("❌ 沒有進階資料可供分析。")
        return
        
    print("\n========================================")
    print("📈 開始進行臨床特徵與聲學指標分析")
    print("========================================")

    # 1. 核心 ASD 互動特徵分析
    asd_features = [
        "speech_ratio", 
        "fragmentation_ratio",
        "num_long_pauses", 
        "energy_burst_ratio", 
        "std_pitch_hz"
    ]
    plot_distribution(df_adv, asd_features, "ASD_Clinical_Features")
    plot_correlation(df_adv, asd_features, "ASD_Clinical_Features")

    # 2. 聲學品質與噪音分析 (評估轉錄難度)
    acoustic_features = [
        "snr_db", 
        "chaos_ratio", 
        "mean_zcr", 
        "mean_spectral_contrast", 
        "rms_dynamic_range"
    ]
    plot_distribution(df_adv, acoustic_features, "Acoustic_Quality")
    plot_correlation(df_adv, acoustic_features, "Acoustic_Quality")

    # 3. 跨維度散佈圖 (尋找行為模式與聲學的關聯)
    # 高碎片化通常伴隨較多的長停頓嗎？
    plot_scatter(df_adv, "fragmentation_ratio", "num_long_pauses")
    
    # 爆發能量與音高變異 (尖叫/激動情緒指標)
    plot_scatter(df_adv, "energy_burst_ratio", "std_pitch_hz")
    
    # 訊噪比 vs 語音碎片化 (環境噪音是否導致 VAD 破碎)
    plot_scatter(df_adv, "snr_db", "fragmentation_ratio")
    
    # 語音比例 vs 總時長
    plot_scatter(df_adv, "total_duration_sec", "speech_ratio")

    # 4. 產出摘要統計報表
    print("\n📝 產出統計摘要...")
    summary = df_adv.describe()
    summary.to_csv(OUTPUT_DIR / "Summary_Statistics.csv")
    
    # 找出極端個案 (Outliers)
    print("\n🚨 極端個案分析 (Top 5% 或 Bottom 5%):")
    outliers_report = []
    
    for col in asd_features:
        if col in df_adv.columns:
            threshold_high = df_adv[col].quantile(0.95)
            threshold_low = df_adv[col].quantile(0.05)
            
            high_cases = df_adv[df_adv[col] >= threshold_high]['case_name'].tolist()
            low_cases = df_adv[df_adv[col] <= threshold_low]['case_name'].tolist()
            
            outliers_report.append(f"- 【{col}】")
            outliers_report.append(f"  高極端 (>={threshold_high:.2f}): {', '.join(high_cases)}")
            outliers_report.append(f"  低極端 (<={threshold_low:.2f}): {', '.join(low_cases)}")
            
    outliers_text = "\n".join(outliers_report)
    print(outliers_text)
    
    with open(OUTPUT_DIR / "Outliers_Report.txt", "w", encoding="utf-8") as f:
        f.write("極端個案分析報告 (Outliers Report)\n")
        f.write("========================================\n")
        f.write(outliers_text)

    print(f"\n🎉 分析完成！所有圖表與報表已存入: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
