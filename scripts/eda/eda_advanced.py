import os
import glob
import math
import subprocess
from pathlib import Path

# ==========================================
# 0. 系統環境變數設定
# ==========================================
HF_CACHE_DIR = r"D:\hf_models"
os.environ["TORCH_HOME"] = str(Path(HF_CACHE_DIR) / "torch")

import torch
import librosa
import numpy as np
import pandas as pd

# ==========================================
# 1. 系統初始化與模型載入
# ==========================================
print("🚀 正在載入 AI 模型 (Silero VAD)...")

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

vad_model, vad_utils = torch.hub.load(
    repo_or_dir="snakers4/silero-vad",
    model="silero_vad",
    trust_repo=True,
)
(get_speech_timestamps, save_audio, read_audio, VADIterator, collect_chunks) = vad_utils

print(f"✅ 模型載入完成！使用設備: {DEVICE}")

# ==========================================
# 2. 定義進階分析函數 (特別針對 ASD 臨床與多語者情境)
# ==========================================
def extract_audio_from_mp4(mp4_path: Path, wav_path: Path):
    print(f"   -> 🎞️ 正在抽取音訊並存檔至: {wav_path.name}")
    cmd = [
        "ffmpeg", "-y", "-i", str(mp4_path),
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        str(wav_path),
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

def compute_snr_db(y: np.ndarray) -> float:
    if y is None or len(y) == 0:
        return float("nan")

    rms = librosa.feature.rms(y=y)[0]
    if rms is None or len(rms) == 0:
        return float("nan")

    noise_energy = max(float(np.percentile(rms, 10)), 1e-6)
    signal_energy = max(float(np.percentile(rms, 90)), 1e-6)

    if signal_energy <= 0 or noise_energy <= 0:
        return float("nan")

    return 20 * math.log10(signal_energy / noise_energy)

def analyze_audio_advanced(wav_path: Path):
    results = {}
    SR = 16000
    
    # 讀取音訊
    print("   -> 📡 載入音訊與 VAD 分析...")
    wav_tensor = read_audio(str(wav_path), sampling_rate=SR)
    y, sr = librosa.load(str(wav_path), sr=SR, mono=True)
    
    total_duration = len(y) / sr
    results["total_duration_sec"] = total_duration
    
    speech_timestamps = get_speech_timestamps(
        wav_tensor,
        vad_model,
        sampling_rate=SR,
    )
    
    # ==========================================
    # 指標 A: 語音長度與破碎率、停頓分析 (ASD 互動特徵)
    # ==========================================
    if len(speech_timestamps) == 0:
        results.update({
            "total_utterances": 0,
            "fragmentation_ratio": 0.0,
            "speech_ratio": 0.0,
            "avg_utterance_duration": 0.0,
            "num_short_pauses": 0,
            "num_long_pauses": 0,
            "avg_pause_duration": 0.0,
        })
    else:
        utterance_durations = [(ts["end"] - ts["start"]) / SR for ts in speech_timestamps]
        total_speech_duration = sum(utterance_durations)
        short_utterances = [d for d in utterance_durations if d < 1.5]
        
        results["total_utterances"] = len(speech_timestamps)
        results["fragmentation_ratio"] = len(short_utterances) / len(speech_timestamps)
        results["speech_ratio"] = total_speech_duration / total_duration if total_duration > 0 else 0
        results["avg_utterance_duration"] = float(np.mean(utterance_durations))
        
        pauses = []
        short_pauses = 0 # < 2 seconds (normal conversational pauses)
        long_pauses = 0  # >= 2 seconds (potential lack of response / interaction gap)
        for i in range(1, len(speech_timestamps)):
            pause_dur = (speech_timestamps[i]["start"] - speech_timestamps[i-1]["end"]) / SR
            if pause_dur > 0:
                pauses.append(pause_dur)
                if pause_dur >= 2.0:
                    long_pauses += 1
                else:
                    short_pauses += 1
                
        results["num_short_pauses"] = short_pauses
        results["num_long_pauses"] = long_pauses
        results["avg_pause_duration"] = float(np.mean(pauses)) if len(pauses) > 0 else 0.0

    # ==========================================
    # 指標 B: 整體信噪比 (SNR) 與 爆發性能量 (Bursts)
    # ==========================================
    print("   -> 🎧 分析指標 B: 信噪比與突發能量 (大聲喊叫/情緒起伏)...")
    results["snr_db"] = compute_snr_db(y)
    
    if len(y) > 0:
        rms = librosa.feature.rms(y=y)[0]
        results["mean_rms"] = float(np.mean(rms))
        results["std_rms"] = float(np.std(rms))
        results["rms_dynamic_range"] = float(np.percentile(rms, 95) - np.percentile(rms, 5))
        
        # 突發能量 (Bursts): 尋找能量突然飆高超過 98 百分位的次數 (可能代表尖叫、拍桌或大聲干擾)
        burst_threshold = np.percentile(rms, 98)
        burst_frames = np.sum(rms > burst_threshold)
        results["energy_burst_ratio"] = float(burst_frames / len(rms))
    else:
        results["mean_rms"] = 0.0
        results["std_rms"] = 0.0
        results["rms_dynamic_range"] = 0.0
        results["energy_burst_ratio"] = 0.0

    # ==========================================
    # 指標 C: 頻譜特徵、混亂度與音色特徵 (MFCC)
    # ==========================================
    print("   -> 🗣️ 分析指標 C: 頻譜特徵、MFCC 與混亂度...")
    if len(y) > 0:
        cent = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        cent_diff = np.abs(np.diff(cent))
        if len(cent_diff) > 0:
            chaos_threshold = np.percentile(cent_diff, 85) 
            chaotic_frames = np.sum(cent_diff > chaos_threshold)
            results["chaos_ratio"] = chaotic_frames / len(cent_diff)
        else:
            results["chaos_ratio"] = 0.0
            
        bw = librosa.feature.spectral_bandwidth(y=y, sr=sr)[0]
        rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
        results["mean_spectral_bandwidth"] = float(np.mean(bw))
        results["mean_spectral_rolloff"] = float(np.mean(rolloff))
        
        # Spectral Contrast: 反映頻譜峰值與谷值的差異，高對比度通常代表清晰的語音共振峰
        contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
        results["mean_spectral_contrast"] = float(np.mean(contrast))
        
        # Spectral Flatness: 接近 1 代表白噪音，接近 0 代表純音 (可用來估算音訊中非語音雜訊的比例)
        flatness = librosa.feature.spectral_flatness(y=y)[0]
        results["mean_spectral_flatness"] = float(np.mean(flatness))

        # MFCC: 提取前 5 維梅爾倒頻譜系數，反映整體的音色與聲學特徵分佈
        mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=5)
        for i in range(5):
            results[f"mfcc_{i+1}_mean"] = float(np.mean(mfccs[i]))
            results[f"mfcc_{i+1}_std"] = float(np.std(mfccs[i]))
            
    else:
        results["chaos_ratio"] = 0.0
        results["mean_spectral_bandwidth"] = 0.0
        results["mean_spectral_rolloff"] = 0.0
        results["mean_spectral_contrast"] = 0.0
        results["mean_spectral_flatness"] = 0.0
        for i in range(5):
            results[f"mfcc_{i+1}_mean"] = 0.0
            results[f"mfcc_{i+1}_std"] = 0.0

    # ==========================================
    # 指標 D: Zero Crossing Rate (語音與噪音特性)
    # ==========================================
    print("   -> 📉 分析指標 D: 過零率 (ZCR)...")
    if len(y) > 0:
        zcr = librosa.feature.zero_crossing_rate(y)[0]
        results["mean_zcr"] = float(np.mean(zcr))
        results["std_zcr"] = float(np.std(zcr))
    else:
        results["mean_zcr"] = 0.0
        results["std_zcr"] = 0.0

    # ==========================================
    # 指標 F: 音高 (Pitch / F0) 分析 (語調變化，ASD 常見單調或高亢特徵)
    # ==========================================
    print("   -> 🎵 分析指標 F: 音高 (F0) 分佈與語調變化...")
    if len(y) > 0:
        try:
            f0 = librosa.yin(y, fmin=50, fmax=500, sr=sr)
            voiced_f0 = f0[f0 > 0]
            if len(voiced_f0) > 0:
                results["mean_pitch_hz"] = float(np.mean(voiced_f0))
                results["std_pitch_hz"] = float(np.std(voiced_f0)) # 變異度大代表語調起伏大，小代表單調 (Monotone)
                results["max_pitch_hz"] = float(np.percentile(voiced_f0, 95)) # 取 95% 避免極端雜訊
            else:
                results["mean_pitch_hz"] = 0.0
                results["std_pitch_hz"] = 0.0
                results["max_pitch_hz"] = 0.0
        except Exception as e:
            print(f"      [警告] F0 分析失敗: {e}")
            results["mean_pitch_hz"] = 0.0
            results["std_pitch_hz"] = 0.0
            results["max_pitch_hz"] = 0.0
    else:
        results["mean_pitch_hz"] = 0.0
        results["std_pitch_hz"] = 0.0
        results["max_pitch_hz"] = 0.0

    return results

# ==========================================
# 3. 主程式
# ==========================================
def main():
    data_dir = Path("data")
    mp4_files = list(data_dir.rglob("*.mp4"))
    
    source_mp4_files = [f for f in mp4_files if "source" in f.parts or "video" in f.parts]
    if not source_mp4_files:
        source_mp4_files = mp4_files

    if not source_mp4_files:
        print("❌ 找不到任何 MP4 檔案，請檢查路徑設定！")
        return

    print(f"📂 找到 {len(source_mp4_files)} 筆影片檔案，準備開始臨床進階分析！")

    all_results = []

    for idx, mp4_path in enumerate(source_mp4_files, start=1):
        case_name = mp4_path.parent.parent.name if mp4_path.parent.name == "source" else mp4_path.stem
        print(f"\n[{idx}/{len(source_mp4_files)}] 正在處理 Case: {case_name}")

        wav_path = mp4_path.with_suffix(".wav")

        try:
            if not wav_path.exists():
                extract_audio_from_mp4(mp4_path, wav_path)
            else:
                print(f"   -> ⏩ WAV 檔案已存在: {wav_path.name}")

            metrics = analyze_audio_advanced(wav_path)
            metrics["case_name"] = case_name
            all_results.append(metrics)

        except Exception as e:
            print(f"❌ 處理 {case_name} 時發生錯誤: {e}")

    # ==========================================
    # 4. 輸出報表
    # ==========================================
    df = pd.DataFrame(all_results)
    if not df.empty:
        cols = ["case_name"] + [c for c in df.columns if c != "case_name"]
        df = df[cols]
        
        output_dir = Path("scripts/eda/result")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_csv = output_dir / "EDA_Clinical_Advanced_Results.csv"
        
        df.to_csv(output_csv, index=False, encoding="utf-8-sig")
        print(f"\n🎉 完成！所有進階分析已完成，報表已儲存至: {output_csv}")
        print("\n--- 核心指標統計摘要 ---")
        summary_cols = ["case_name", "speech_ratio", "num_long_pauses", "energy_burst_ratio", "std_pitch_hz", "chaos_ratio"]
        existing_summary_cols = [c for c in summary_cols if c in df.columns]
        print(df[existing_summary_cols].describe())
    else:
        print("⚠️ 沒有成功分析任何檔案，因此未輸出 CSV。")

if __name__ == "__main__":
    main()