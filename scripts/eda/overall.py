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
# 2. 定義分析函數
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

def analyze_audio(wav_path: Path):
    results = {}

    # --- 指標 A: VAD 破碎率 ---
    print("   -> 🔍 分析指標 A: 語音破碎率...")
    wav_tensor = read_audio(str(wav_path), sampling_rate=16000)
    speech_timestamps = get_speech_timestamps(
        wav_tensor,
        vad_model,
        sampling_rate=16000,
    )

    if len(speech_timestamps) == 0:
        results["total_utterances"] = 0
        results["fragmentation_ratio"] = 0.0
    else:
        short_utterances = [
            ts for ts in speech_timestamps
            if (ts["end"] - ts["start"]) / 16000 < 1.5
        ]
        results["total_utterances"] = len(speech_timestamps)
        results["fragmentation_ratio"] = len(short_utterances) / len(speech_timestamps)

    # --- 指標 B: 整體信噪比 (SNR) ---
    print("   -> 🎧 分析指標 B: 整體信噪比 (SNR)...")
    y, sr = librosa.load(str(wav_path), sr=16000, mono=True)
    results["snr_db"] = compute_snr_db(y)

    # --- 指標 C: 頻譜混亂度 (作為重疊/干擾的替代指標) ---
    print("   -> 🗣️ 分析指標 C: 頻譜混亂度 (干擾率估計)...")
    if len(y) > 0:
        # 擷取頻譜質心
        cent = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        # 計算質心的變化率 (一階導數)
        cent_diff = np.abs(np.diff(cent))
        
        # 經驗閾值：如果質心瞬間變化極大，通常代表多個聲音交疊或突發噪音
        if len(cent_diff) > 0:
            chaos_threshold = np.percentile(cent_diff, 85) 
            chaotic_frames = np.sum(cent_diff > chaos_threshold)
            results["chaos_ratio"] = chaotic_frames / len(cent_diff)
        else:
            results["chaos_ratio"] = 0.0
    else:
        results["chaos_ratio"] = 0.0

    return results

# ==========================================
# 3. 主程式
# ==========================================
def main():
    data_dir = Path("data")
    mp4_files = list(data_dir.glob("*/source/*.mp4"))

    if not mp4_files:
        print("❌ 找不到任何 MP4 檔案，請檢查路徑設定！")
        return

    print(f"📂 找到 {len(mp4_files)} 筆影片檔案，準備開始分析！")

    # 演習模式：先跑 2 筆測試
    # mp4_files = mp4_files[:2]

    all_results = []

    for idx, mp4_path in enumerate(mp4_files, start=1):
        case_name = mp4_path.parent.parent.name
        print(f"\n[{idx}/{len(mp4_files)}] 正在處理 Case: {case_name}")

        wav_path = mp4_path.with_suffix(".wav")

        try:
            if not wav_path.exists():
                extract_audio_from_mp4(mp4_path, wav_path)
            else:
                print(f"   -> ⏩ WAV 檔案已存在，跳過轉檔: {wav_path.name}")

            metrics = analyze_audio(wav_path)
            metrics["case_name"] = case_name
            all_results.append(metrics)

        except Exception as e:
            print(f"❌ 處理 {case_name} 時發生錯誤: {e}")

    # ==========================================
    # 4. 輸出報表
    # ==========================================
    df = pd.DataFrame(all_results)
    if not df.empty:
        df = df[
            ["case_name", "total_utterances", "fragmentation_ratio", "chaos_ratio", "snr_db"]
        ]
        output_csv = "scripts/eda/EDA_Results_ASD_Clinical.csv"
        df.to_csv(output_csv, index=False, encoding="utf-8-sig")
        print(f"\n🎉 完成！所有分析已完成，報表已儲存至: {output_csv}")
        print("\n--- 數據統計摘要 ---")
        print(df.describe(include="all"))
    else:
        print("⚠️ 沒有成功分析任何檔案，因此未輸出 CSV。")

if __name__ == "__main__":
    main()