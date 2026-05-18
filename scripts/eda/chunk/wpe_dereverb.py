import os
import argparse
import numpy as np
import librosa
import soundfile as sf
import matplotlib.pyplot as plt
from pathlib import Path
from nara_wpe.wpe import wpe
from nara_wpe.utils import stft, istft

def analyze_and_dereverb(wav_path, output_dir, subject_id, start_sec=1119.0, duration=15.0):
    print(f"📂 正在讀取音檔: {wav_path} (擷取 {start_sec}s - {start_sec+duration}s)")
    
    # 讀取音檔 (WPE 通常在 16kHz 下運作良好)
    y, sr = librosa.load(wav_path, sr=16000, offset=start_sec, duration=duration)
    
    # WPE 需要的輸入維度是 (channels, samples)
    # 如果是單聲道，我們增加一個維度變成 (1, samples)
    if y.ndim == 1:
        y = np.expand_dims(y, axis=0)
    
    # --- 1. STFT 轉換到頻域 ---
    print("🌊 進行 STFT (短時傅立葉變換)...")
    stft_options = dict(size=512, shift=128)
    Y = stft(y, **stft_options).transpose(2, 0, 1) 
    # nara_wpe 需要的維度: (Frequencies, Frames, Channels)
    
    # --- 2. 執行 WPE 去殘響 ---
    print("🪄 施展物理魔法：執行 WPE 演算法...")
    # 參數設定 (參考論文標準值)
    # taps: 要消除多長的歷史回音 (10 幀大約是 80 毫秒的殘響)
    # delay: 保留幾幀的早期反射音不消除 (3 幀大約是 24 毫秒，這對 ASR 是有益的)
    Z = wpe(Y, taps=10, delay=3, iterations=3, statistics_mode='full')
    
    # --- 3. ISTFT 轉回時域 ---
    print("🌊 進行 ISTFT 轉回音訊波形...")
    z = istft(Z.transpose(1, 2, 0), size=512, shift=128)
    
    # 存檔
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_wav = out_dir / f"{subject_id}_wpe_processed.wav"
    orig_wav = out_dir / f"{subject_id}_original_clip.wav"
    
    # 確保輸出長度一致並存檔 (取第一個 channel)
    sf.write(orig_wav, y[0], sr)
    sf.write(out_wav, z[0][:y.shape[1]], sr)
    
    # --- 4. 繪製頻譜對比圖 (資料分析) ---
    print("📊 正在繪製聲學分析對比圖...")
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    
    # 原始頻譜
    D_orig = librosa.amplitude_to_db(np.abs(librosa.stft(y[0])), ref=np.max)
    img1 = librosa.display.specshow(D_orig, sr=sr, x_axis='time', y_axis='log', ax=axes[0], cmap='magma')
    axes[0].set_title(f'Original Noisy & Reverberant Speech ({subject_id})')
    fig.colorbar(img1, ax=axes[0], format="%+2.0f dB")
    
    # WPE 處理後頻譜
    D_wpe = librosa.amplitude_to_db(np.abs(librosa.stft(z[0][:y.shape[1]])), ref=np.max)
    img2 = librosa.display.specshow(D_wpe, sr=sr, x_axis='time', y_axis='log', ax=axes[1], cmap='magma')
    axes[1].set_title('After WPE Dereverberation (Cleaned Speech)')
    fig.colorbar(img2, ax=axes[1], format="%+2.0f dB")
    
    plt.tight_layout()
    png_path = out_dir / f"{subject_id}_wpe_comparison.png"
    plt.savefig(png_path, dpi=300)
    
    print(f"✅ 處理完成！")
    print(f"🎧 原始音檔: {orig_wav}")
    print(f"🎧 WPE 音檔: {out_wav}")
    print(f"🖼️ 分析圖表: {png_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", type=str, required=True, help="例如: subject11")
    args = parser.parse_args()
    
    # 支援帶有後綴的 subject_id (例如 subject11_test)
    base_id = args.subject.split('_')[0]
    wav_file = f"data/{args.subject}/source/{base_id}.wav"
    out = f"data/{args.subject}/output/"
    
    if os.path.exists(wav_file):
        # 預設擷取第 18 分鐘 (1119秒)，也就是之前產生幻覺的那段
        analyze_and_dereverb(wav_file, out, args.subject, start_sec=1119.0, duration=15.0)
    else:
        print(f"❌ 找不到音檔: {wav_file}")