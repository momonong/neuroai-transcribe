import os
import argparse
import numpy as np
import pandas as pd
import librosa
import torch
import matplotlib.pyplot as plt
from pathlib import Path

def load_silero_vad():
    print("🤖 正在載入 Silero VAD 模型 (首次執行會自動下載幾MB的模型)...")
    model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad', force_reload=False)
    get_speech_timestamps = utils[0]
    return model, get_speech_timestamps

def fast_acoustic_profiling_silero(wav_path, sr=16000):
    """
    使用 Silero VAD 抵抗空間回音抓取時間軸，並用頻譜質心區分語者 (Zero-Shot)
    """
    print(f"⏳ 正在載入音檔: {wav_path}")
    y, sr = librosa.load(wav_path, sr=sr)
    total_duration = librosa.get_duration(y=y, sr=sr)
    
    # 轉換為 torch tensor 給 Silero 使用
    wav_tensor = torch.from_numpy(y)
    
    model, get_speech_timestamps = load_silero_vad()
    
    print("🔍 執行 Silero VAD 語音偵測 (抗噪模式)...")
    # threshold 降低到 0.3 以捕捉微弱語音，min_silence_duration_ms=500 避免把單字切斷
    speech_timestamps = get_speech_timestamps(
        wav_tensor, 
        model, 
        sampling_rate=sr, 
        threshold=0.3, 
        min_speech_duration_ms=250, 
        min_silence_duration_ms=500
    )
    
    if not speech_timestamps:
        print("❌ 嚴重警告：Silero VAD 未偵測到任何語音！請確認音檔是否有聲音。")
        return [], total_duration

    print("🎶 正在計算頻譜質心進行盲目語者分類 (Tester vs Child)...")
    centroids = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=512)[0]
    
    segments = []
    for ts in speech_timestamps:
        start_t = ts['start'] / sr
        end_t = ts['end'] / sr
        
        start_frame = librosa.time_to_frames(start_t, sr=sr, hop_length=512)
        end_frame = librosa.time_to_frames(end_t, sr=sr, hop_length=512)
        
        if start_frame >= end_frame:
            continue
            
        # 計算該片段的平均頻譜質心
        seg_centroid = np.mean(centroids[start_frame:end_frame])
        
        segments.append({
            'start': start_t,
            'end': end_t,
            'duration': end_t - start_t,
            'centroid': seg_centroid
        })
        
    # 極簡分群：以中位數為界，質心高的判為 Child，低的分為 Tester
    all_cents = [s['centroid'] for s in segments]
    median_cent = np.median(all_cents)
    for s in segments:
        s['speaker'] = 'Child' if s['centroid'] > median_cent else 'Tester'
        
    print(f"✅ 成功擷取 {len(segments)} 個有效語音片段！")
    return segments, total_duration

def analyze_interaction_dynamics(subject_id, segments, total_duration, output_dir, window_sec=60, step_sec=10):
    if not segments:
        return

    print("📈 正在分析臨床互動特徵與尋找語意切分點...")
    df = pd.DataFrame(segments)
    
    # 1. 尋找候選切分點 (大於 3.0 秒的靜音)
    candidate_cuts = []
    for i in range(1, len(df)):
        gap = df.iloc[i]['start'] - df.iloc[i-1]['end']
        if gap > 3.0: 
            candidate_cuts.append({
                'time_sec': df.iloc[i-1]['end'] + (gap / 2),
                'gap_duration': gap
            })
            
    # 2. 滑動視窗特徵提取
    windows = []
    for start_t in np.arange(0, total_duration, step_sec):
        end_t = start_t + window_sec
        mask = (df['start'] < end_t) & (df['end'] > start_t)
        w_df = df[mask]
        
        tester_time = w_df[w_df['speaker'] == 'Tester']['end'].clip(upper=end_t) - w_df[w_df['speaker'] == 'Tester']['start'].clip(lower=start_t)
        child_time = w_df[w_df['speaker'] == 'Child']['end'].clip(upper=end_t) - w_df[w_df['speaker'] == 'Child']['start'].clip(lower=start_t)
        
        t_sum = tester_time.sum()
        c_sum = child_time.sum()
        total_speech = t_sum + c_sum
        
        turns = (w_df['speaker'] != w_df['speaker'].shift()).sum() if len(w_df) > 0 else 0
        
        windows.append({
            'time_min': (start_t + window_sec/2) / 60,
            'tester_ratio': (t_sum / total_speech) if total_speech > 0 else 0,
            'child_ratio': (c_sum / total_speech) if total_speech > 0 else 0,
            'turn_rate': turns,
            'silence_ratio': max(0, (window_sec - total_speech) / window_sec)
        })
        
    w_df_features = pd.DataFrame(windows)
    
    # 3. 提議最佳切分點 (每 5 分鐘找最大的靜音缺口)
    cuts_df = pd.DataFrame(candidate_cuts)
    best_cuts = pd.DataFrame()
    if not cuts_df.empty:
        cuts_df['time_min'] = cuts_df['time_sec'] / 60
        cuts_df['bin'] = (cuts_df['time_min'] // 5).astype(int) 
        best_cuts = cuts_df.loc[cuts_df.groupby('bin')['gap_duration'].idxmax()]
        
    # --- Output & Visualization ---
    print(f"\n📊 [ {subject_id} Semantic Slicing Report ]")
    print("="*50)
    if best_cuts.empty:
        print("⚠️ 無法找到大於 3 秒的靜音切分點！")
    else:
        for idx, row in best_cuts.iterrows():
            print(f"✂️ Proposed Cut: {row['time_min']:05.2f} min (Silence Gap: {row['gap_duration']:.1f} sec)")
    print("="*50)
    
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
    
    ax1.plot(w_df_features['time_min'], w_df_features['tester_ratio'], label='Tester', color='#1f77b4', alpha=0.8)
    ax1.plot(w_df_features['time_min'], w_df_features['child_ratio'], label='Child', color='#ff7f0e', alpha=0.8)
    ax1.fill_between(w_df_features['time_min'], w_df_features['tester_ratio'], alpha=0.2, color='#1f77b4')
    ax1.fill_between(w_df_features['time_min'], w_df_features['child_ratio'], alpha=0.2, color='#ff7f0e')
    ax1.set_ylabel("Speech Ratio")
    ax1.set_title(f"{subject_id} - Interaction Dynamics & Semantic Slicing (Window={window_sec}s)")
    ax1.legend(loc='upper right')
    
    ax2.plot(w_df_features['time_min'], w_df_features['turn_rate'], label='Turn-Taking Rate', color='#2ca02c')
    ax2.set_ylabel("Turns / min")
    ax2.legend(loc='upper right')

    ax3.bar(w_df_features['time_min'], w_df_features['silence_ratio'], width=step_sec/60, color='gray', alpha=0.5, label='Silence Ratio')
    ax3.set_ylabel("Silence Ratio")
    ax3.set_xlabel("Time (Minutes)")
    ax3.legend(loc='upper right')
    
    for ax in [ax1, ax2, ax3]:
        for idx, row in best_cuts.iterrows():
            ax.axvline(x=row['time_min'], color='red', linestyle='--', alpha=0.8)
            if ax == ax1:
                ax.text(row['time_min'], 0.9, f" Cut\n{row['gap_duration']:.1f}s gap", color='red', rotation=0, fontsize=9)

    plt.tight_layout()
    
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    png_path = out_dir / f"{subject_id}_chunk_analysis.png"
    csv_path = out_dir / f"{subject_id}_proposed_cuts.csv"
    plt.savefig(png_path, dpi=300)
    best_cuts.to_csv(csv_path, index=False)
    
    print(f"📁 Analysis chart saved to: {png_path}")
    print(f"📁 Slicing proposals saved to: {csv_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EDA Smart Chunking directly from WAV")
    parser.add_argument("--subject", type=str, required=True, help="Subject ID (e.g., subject11)")
    args = parser.parse_args()
    
    wav_path = f"data/{args.subject}/source/{args.subject}.wav"
    output_dir = "docs/eda/chunk/"
    
    if os.path.exists(wav_path):
        segments, duration = fast_acoustic_profiling_silero(wav_path)
        analyze_interaction_dynamics(args.subject, segments, duration, output_dir)
    else:
        print(f"❌ Error: WAV file not found at {wav_path}")