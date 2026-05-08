import os
import glob
import torch
import librosa
import numpy as np
import pandas as pd
import parselmouth
import matplotlib.pyplot as plt
from pathlib import Path

class ADOSFullAnalyzer:
    def __init__(self, data_root="data", sample_rate=16000):
        self.data_root = Path(data_root)
        self.sr = sample_rate
        self.frame_step = 0.01  # 解析度：10 毫秒
        
        # 判斷是否使用 GPU (RTX 5090 準備發威)
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        print(f"🚀 初始化分析器... 使用運算設備: {self.device}")
        
        # 載入 Silero VAD
        self.vad_model, self.vad_utils = torch.hub.load(
            repo_or_dir='snakers4/silero-vad',
            model='silero_vad',
            force_reload=False,
            onnx=False
        )
        self.vad_model = self.vad_model.to(self.device)
        self.get_speech_timestamps = self.vad_utils[0]

    def process_all_subjects(self):
        """主迴圈：遍歷所有 subject 資料夾進行分析"""
        wav_files = glob.glob(f"{self.data_root}/subject*/source/*.wav")
        if not wav_files:
            print("❌ 找不到任何 .wav 檔案，請檢查 data/ 目錄結構！")
            return

        global_stats = []

        for wav_path in wav_files:
            subject_id = Path(wav_path).parent.parent.name
            intermediate_dir = self.data_root / subject_id / "intermediate"
            intermediate_dir.mkdir(parents=True, exist_ok=True)
            
            print(f"\n[{subject_id}] 開始深度分析: {wav_path}")
            
            # 1. 提取微觀特徵 (DataFrame)
            df_features = self._extract_frame_features(wav_path)
            
            # 2. 儲存微觀特徵 CSV
            csv_path = intermediate_dir / f"{subject_id}_acoustic_features.csv"
            df_features.to_csv(csv_path, index=False)
            
            # 3. 計算局部統計 (Local Stats)
            local_stat = self._calculate_local_statistics(subject_id, df_features)
            global_stats.append(local_stat)
            
            # 4. 生成視覺化診斷圖
            plot_path = intermediate_dir / f"{subject_id}_diagnostic_plot.png"
            self._generate_diagnostic_plot(subject_id, df_features, plot_path)
            
            print(f"✅ [{subject_id}] 分析完成！資料存於 {intermediate_dir}")

        # 5. 匯出全局趨勢報告
        df_global = pd.DataFrame(global_stats)
        global_csv_path = self.data_root / "global_analysis_summary.csv"
        df_global.to_csv(global_csv_path, index=False)
        print(f"\n🎉 所有 21 筆資料分析完畢！全局報告已儲存至: {global_csv_path}")

    def _extract_frame_features(self, audio_path):
        """提取 F0, Intensity 與 VAD，對齊到 10ms 的 Frame"""
        print("   -> 載入音訊與 Praat 特徵提取中...")
        wav_np, _ = librosa.load(audio_path, sr=self.sr)
        snd = parselmouth.Sound(audio_path)
        
        pitch = snd.to_pitch(time_step=self.frame_step)
        intensity = snd.to_intensity(time_step=self.frame_step)
        
        num_frames = int(snd.get_total_duration() / self.frame_step)
        times = np.arange(num_frames) * self.frame_step
        
        # 避免 Praat 回傳 NaN
        f0_values = [pitch.get_value_at_time(t) if not np.isnan(pitch.get_value_at_time(t)) else 0 for t in times]
        db_values = [intensity.get_value(t) if not np.isnan(intensity.get_value(t)) else 0 for t in times]
        
        df = pd.DataFrame({
            'Time_sec': times,
            'F0_Hz': f0_values,
            'Intensity_dB': db_values,
            'VAD_Speech': False
        })
        
        print("   -> 執行 Silero VAD 推論中...")
        wav_tensor = torch.from_numpy(wav_np).to(self.device)
        speech_timestamps = self.get_speech_timestamps(wav_tensor, self.vad_model, sampling_rate=self.sr)
        
        for seg in speech_timestamps:
            start_sec = seg['start'] / self.sr
            end_sec = seg['end'] / self.sr
            df.loc[(df['Time_sec'] >= start_sec) & (df['Time_sec'] <= end_sec), 'VAD_Speech'] = True
            
        return df

    def _calculate_local_statistics(self, subject_id, df):
        """從微觀資料計算出宏觀的臨床與聲學指標"""
        print("   -> 計算局部特徵統計 (Local Stats)...")
        total_duration = df['Time_sec'].max()
        
        # 1. 語音佔比
        speech_frames = df[df['VAD_Speech'] == True]
        speech_ratio = (len(speech_frames) / len(df)) * 100

        # 2. 高頻發聲 (潛在的孩童非典型發聲/尖叫, > 350Hz)
        high_pitch_frames = df[(df['VAD_Speech'] == True) & (df['F0_Hz'] > 350)]
        high_pitch_duration = len(high_pitch_frames) * self.frame_step
        
        # 3. 異常突發噪音 (非語音但能量極高, > 75dB)
        noise_frames = df[(df['VAD_Speech'] == False) & (df['Intensity_dB'] > 75)]
        noise_duration = len(noise_frames) * self.frame_step

        # 4. 對話破碎度 (計算極短的語音片段數量)
        # 利用 shift 找出 VAD 狀態改變的邊界
        df['VAD_Change'] = df['VAD_Speech'] != df['VAD_Speech'].shift(1)
        speech_segments = df[df['VAD_Speech'] & df['VAD_Change']]
        fragmented_speech_count = 0  # < 1 秒的發聲次數
        
        return {
            'Subject_ID': subject_id,
            'Duration_sec': round(total_duration, 2),
            'Speech_Ratio_%': round(speech_ratio, 2),
            'High_Pitch_Duration_sec': round(high_pitch_duration, 2),
            'NonSpeech_Noise_Duration_sec': round(noise_duration, 2),
            'Average_F0_Hz': round(speech_frames[speech_frames['F0_Hz']>0]['F0_Hz'].mean(), 2)
        }

    def _generate_diagnostic_plot(self, subject_id, df, save_path):
        """繪製多軌時間序列圖，並儲存為高解析度 PNG"""
        print("   -> 繪製並儲存聲學診斷圖...")
        
        # 為了避免 40 分鐘資料畫在一張圖太擠，我們針對資料進行降採樣 (Downsample) 來畫圖
        # 畫圖時每 0.1 秒取一筆即可
        df_plot = df.iloc[::10, :] 
        
        fig, axs = plt.subplots(3, 1, figsize=(15, 10), sharex=True)
        fig.suptitle(f'Acoustic Diagnostic Profile: {subject_id}', fontsize=16)

        # Track 1: VAD (Voice Activity)
        axs[0].plot(df_plot['Time_sec'], df_plot['VAD_Speech'], color='blue', alpha=0.7)
        axs[0].fill_between(df_plot['Time_sec'], 0, df_plot['VAD_Speech'], color='blue', alpha=0.3)
        axs[0].set_ylabel('VAD (Speech=1)')
        axs[0].set_ylim(-0.1, 1.1)

        # Track 2: Pitch (F0)
        # 只畫出有聲音且有抓到 Pitch 的點
        valid_pitch = df_plot[df_plot['F0_Hz'] > 0]
        axs[1].scatter(valid_pitch['Time_sec'], valid_pitch['F0_Hz'], color='green', s=1, alpha=0.5)
        axs[1].axhline(y=350, color='red', linestyle='--', label='Child High-Pitch Threshold (350Hz)')
        axs[1].set_ylabel('Pitch F0 (Hz)')
        axs[1].set_ylim(50, 600)
        axs[1].legend(loc="upper right")

        # Track 3: Intensity (Loudness)
        axs[2].plot(df_plot['Time_sec'], df_plot['Intensity_dB'], color='orange', alpha=0.8)
        axs[2].axhline(y=75, color='red', linestyle=':', label='Loud Noise Threshold (75dB)')
        axs[2].set_ylabel('Intensity (dB)')
        axs[2].set_xlabel('Time (Seconds)')
        axs[2].legend(loc="upper right")

        plt.tight_layout()
        plt.savefig(save_path, dpi=300)
        plt.close()


if __name__ == "__main__":
    # 將 "data" 換成你實際放置 subject 資料夾的最外層目錄名稱
    analyzer = ADOSFullAnalyzer(data_root="data")
    analyzer.process_all_subjects()