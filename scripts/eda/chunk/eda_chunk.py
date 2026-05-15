import os
import argparse
import numpy as np
import pandas as pd
import torch
import torchaudio
import librosa
import soundfile as sf
import matplotlib.pyplot as plt
from pathlib import Path

def load_silero_vad(device):
    print(f"🤖 Loading Silero VAD model to {device.type.upper()}...")
    model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad', force_reload=False)
    model = model.to(device)
    get_speech_timestamps = utils[0]
    return model, get_speech_timestamps

def fast_acoustic_profiling_gpu(wav_path, target_sr=16000):
    """
    使用 GPU 進行極速音訊處理，並使用 soundfile 避開 torchaudio 的 ffmpeg 依賴問題
    """
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"🚀 Active Device: {device} (Name: {torch.cuda.get_device_name(0) if device.type == 'cuda' else 'CPU'})")
    
    print(f"⏳ Loading audio via soundfile: {wav_path}")
    # 使用 soundfile 讀取 (極快且穩定)，直接避開 torchaudio.load 的 bug
    y, sr = sf.read(wav_path, dtype='float32')
    
    # 轉換為 PyTorch Tensor
    wav_tensor = torch.from_numpy(y)
    
    # 如果是雙聲道，轉為單聲道
    if wav_tensor.ndim > 1:
        wav_tensor = wav_tensor.mean(dim=1)
        
    # 增加 batch 維度以符合 torchaudio resampler 需求: [1, T]
    wav_tensor = wav_tensor.unsqueeze(0)
        
    # 利用 GPU 極速重採樣 (Resampling)
    if sr != target_sr:
        print(f"🔄 Resampling from {sr}Hz to {target_sr}Hz on GPU...")
        resampler = torchaudio.transforms.Resample(orig_freq=sr, new_freq=target_sr).to(device)
        wav_tensor = resampler(wav_tensor.to(device)).cpu()
    
    wav_tensor = wav_tensor.squeeze() # 降回 1D tensor
    total_duration = len(wav_tensor) / target_sr

    # 載入 VAD
    model, get_speech_timestamps = load_silero_vad(device)
    
    print("🔍 Running Silero VAD inference on GPU...")
    # 將音訊送入 GPU 進行 VAD 偵測
    wav_tensor_gpu = wav_tensor.to(device)
    speech_timestamps = get_speech_timestamps(
        wav_tensor_gpu, 
        model, 
        sampling_rate=target_sr, 
        threshold=0.3, # 如果依然過濾掉太多小孩聲音，可降至 0.15
        min_speech_duration_ms=250, 
        min_silence_duration_ms=500
    )
    
    if not speech_timestamps:
        print("❌ Warning: No speech detected by Silero VAD!")
        return [], total_duration

    print("🎶 Calculating Spectral Centroids for Speaker Differentiation (CPU)...")
    y_np = wav_tensor.numpy()
    centroids = librosa.feature.spectral_centroid(y=y_np, sr=target_sr, hop_length=512)[0]
    
    segments = []
    for ts in speech_timestamps:
        start_t = ts['start'] / target_sr
        end_t = ts['end'] / target_sr
        
        start_frame = librosa.time_to_frames(start_t, sr=target_sr, hop_length=512)
        end_frame = librosa.time_to_frames(end_t, sr=target_sr, hop_length=512)
        
        if start_frame >= end_frame:
            continue
            
        seg_centroid = np.mean(centroids[start_frame:end_frame])
        
        segments.append({
            'start': start_t,
            'end': end_t,
            'duration': end_t - start_t,
            'centroid': seg_centroid
        })
        
    # Zero-Shot 語者分群 (高頻=Child, 低頻=Tester)
    all_cents = [s['centroid'] for s in segments]
    median_cent = np.median(all_cents)
    for s in segments:
        s['speaker'] = 'Child' if s['centroid'] > median_cent else 'Tester'
        
    print(f"✅ Extracted {len(segments)} valid speech segments!")
    return segments, total_duration

def analyze_interaction_dynamics(subject_id, segments, total_duration, output_dir, window_sec=60, step_sec=10):
    if not segments:
        return

    print("📈 Analyzing Interaction Dynamics & Proposing Semantic Cuts...")
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
        # 使用 .copy() 避免 pandas 的 SettingWithCopyWarning
        best_cuts = cuts_df.loc[cuts_df.groupby('bin')['gap_duration'].idxmax()].copy()
        
        # 【新增】將秒數轉換為 MM:SS 格式
        best_cuts['time_formatted'] = best_cuts['time_sec'].apply(
            lambda x: f"{int(x // 60):02d}:{int(x % 60):02d}"
        )
        
    # --- Output & Visualization ---
    print(f"\n📊 [ {subject_id} Semantic Slicing Report ]")
    print("="*50)
    if best_cuts.empty:
        print("⚠️ Warning: No silence gaps > 3s found.")
    else:
        for idx, row in best_cuts.iterrows():
            # 【修改】終端機印出 MM:SS
            print(f"✂️ Proposed Cut: {row['time_formatted']} (Silence Gap: {row['gap_duration']:>5.1f} sec)")
    print("="*50)
    
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
    
    # Plot 1: Speech Ratio
    ax1.plot(w_df_features['time_min'], w_df_features['tester_ratio'], label='Tester', color='#1f77b4', alpha=0.8)
    ax1.plot(w_df_features['time_min'], w_df_features['child_ratio'], label='Child', color='#ff7f0e', alpha=0.8)
    ax1.fill_between(w_df_features['time_min'], w_df_features['tester_ratio'], alpha=0.2, color='#1f77b4')
    ax1.fill_between(w_df_features['time_min'], w_df_features['child_ratio'], alpha=0.2, color='#ff7f0e')
    ax1.set_ylabel("Speech Ratio")
    ax1.set_title(f"{subject_id} - Semantic Slicing Profiling (Window={window_sec}s)")
    ax1.legend(loc='upper right')
    
    # Plot 2: Turn-Taking
    ax2.plot(w_df_features['time_min'], w_df_features['turn_rate'], label='Turn-Taking Rate', color='#2ca02c')
    ax2.set_ylabel("Turns / min")
    ax2.legend(loc='upper right')

    # Plot 3: Silence Ratio
    ax3.bar(w_df_features['time_min'], w_df_features['silence_ratio'], width=step_sec/60, color='gray', alpha=0.5, label='Silence Ratio')
    ax3.set_ylabel("Silence Ratio")
    ax3.set_xlabel("Time (Minutes)")
    ax3.legend(loc='upper right')
    
    # Plot Slicing Lines
    for ax in [ax1, ax2, ax3]:
        for idx, row in best_cuts.iterrows():
            ax.axvline(x=row['time_min'], color='red', linestyle='--', alpha=0.8)
            if ax == ax1:
                # 【修改】圖片上的標籤也換成 MM:SS
                ax.text(row['time_min'], 0.85, f" {row['time_formatted']}\n {row['gap_duration']:.1f}s gap", color='red', rotation=0, fontsize=9)

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
    parser = argparse.ArgumentParser(description="GPU-Accelerated EDA Smart Chunking")
    parser.add_argument("--subject", type=str, required=True, help="Subject ID (e.g., subject11)")
    args = parser.parse_args()
    
    wav_path = f"data/{args.subject}/source/{args.subject}.wav"
    output_dir = "docs/eda/chunk/"
    
    if os.path.exists(wav_path):
        # 1. GPU 極速輪廓萃取
        segments, duration = fast_acoustic_profiling_gpu(wav_path)
        # 2. 互動動態分析
        analyze_interaction_dynamics(args.subject, segments, duration, output_dir)
    else:
        print(f"❌ Error: WAV file not found at {wav_path}")