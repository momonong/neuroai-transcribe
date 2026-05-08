import pandas as pd
import numpy as np
from pathlib import Path

class ADOSSingleMarkdownGenerator:
    def __init__(self, data_dir="data", output_dir="docs/eda/local"):
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 定義臨床事件閾值
        self.PITCH_THRES = 350.0  # 超過 350Hz 視為高頻/尖叫
        self.NOISE_THRES = 75.0   # 超過 75dB 且無語音視為爆音/敲擊
        self.SILENCE_SEC = 5.0    # 連續 5 秒無語音視為長沈默

    def format_time(self, seconds):
        """將秒數轉換為 MM:SS 格式"""
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"

    def extract_events(self, df, condition_mask, min_duration=0.5):
        """通用函數：從連續的 Boolean Mask 中提取事件區間"""
        df['group'] = (condition_mask != condition_mask.shift()).cumsum()
        events = []
        
        target_groups = df[condition_mask].groupby('group')
        for _, group in target_groups:
            start_t = group['Time_sec'].iloc[0]
            end_t = group['Time_sec'].iloc[-1]
            duration = end_t - start_t
            
            if duration >= min_duration:
                max_f0 = group['F0_Hz'].max() if 'F0_Hz' in group else 0
                max_db = group['Intensity_dB'].max() if 'Intensity_dB' in group else 0
                events.append({
                    'start': start_t,
                    'end': end_t,
                    'duration': duration,
                    'max_f0': max_f0,
                    'max_db': max_db
                })
        return events

    def generate_subject_details(self, subject_id, df):
        """生成單一個案的詳細區塊內容 (不存檔，只回傳字串)"""
        total_time = df['Time_sec'].max()
        speech_ratio = (df['VAD_Speech'].sum() / len(df)) * 100

        # 抓取異常事件
        pitch_mask = (df['VAD_Speech'] == True) & (df['F0_Hz'] > self.PITCH_THRES)
        pitch_events = self.extract_events(df, pitch_mask, min_duration=1.0)

        noise_mask = (df['VAD_Speech'] == False) & (df['Intensity_dB'] > self.NOISE_THRES)
        noise_events = self.extract_events(df, noise_mask, min_duration=0.5)

        silence_mask = (df['VAD_Speech'] == False)
        silence_events = self.extract_events(df, silence_mask, min_duration=self.SILENCE_SEC)

        # 組裝該個案的 Markdown 區塊
        md = f"### 🧑‍⚕️ {subject_id} 查核清單\n\n"
        md += f"> **總時長:** {self.format_time(total_time)} | **VAD 語音佔比:** {speech_ratio:.1f}%\n\n"
        
        md += "#### 🚨 1. 異常高頻發聲 (F0 > 350Hz)\n"
        if not pitch_events: md += "- 無明顯高頻事件。\n"
        for ev in pitch_events:
            md += f"- [ ] `{self.format_time(ev['start'])} - {self.format_time(ev['end'])}` (持續 {ev['duration']:.1f}s) | 最高音高: **{ev['max_f0']:.1f} Hz**\n"
        md += "\n"

        md += "#### 💥 2. 環境爆音/敲擊聲 (Intensity > 75dB 且無語音)\n"
        if not noise_events: md += "- 無明顯爆音事件。\n"
        for ev in noise_events:
            md += f"- [ ] `{self.format_time(ev['start'])} - {self.format_time(ev['end'])}` (持續 {ev['duration']:.1f}s) | 最高音量: **{ev['max_db']:.1f} dB**\n"
        md += "\n"

        md += f"#### 🔇 3. 長時間沈默 (持續超過 {self.SILENCE_SEC} 秒)\n"
        if not silence_events: md += "- 無長沈默事件。\n"
        for ev in silence_events:
            md += f"- [ ] `{self.format_time(ev['start'])} - {self.format_time(ev['end'])}` (持續 **{ev['duration']:.1f}s**)\n"
        md += "\n---\n\n"
        
        return md, len(pitch_events), len(noise_events), len(silence_events)

    def run(self):
        print(f"🚀 開始生成合併版 MD 查核日誌，輸出目錄: {self.output_dir}")
        
        csv_files = list(self.data_dir.rglob("intermediate/*_acoustic_features.csv"))
        if not csv_files:
            print("❌ 找不到特徵 CSV 檔！請確認是否已執行特徵提取腳本。")
            return

        # 準備兩大區塊：上方摘要表 (Summary) 與 下方詳細清單 (Details)
        summary_md = "## 📊 全局異常事件摘要 (Summary)\n\n"
        details_md = "## 📝 逐筆影片詳細查核清單 (Detailed Logs)\n\n"

        for csv_path in sorted(csv_files):
            subject_id = csv_path.stem.split('_')[0]  # 取出 subject01
            print(f"  -> 正在彙整 {subject_id} 的資料...")
            
            try:
                df = pd.read_csv(csv_path)
                md_text, p_cnt, n_cnt, s_cnt = self.generate_subject_details(subject_id, df)
                
                # 寫入摘要區
                summary_md += f"- **{subject_id}**: 高頻尖叫 `{p_cnt}` 處 | 環境爆音 `{n_cnt}` 處 | 長沈默 `{s_cnt}` 處\n"
                
                # 寫入詳細區
                details_md += md_text
                
            except Exception as e:
                print(f"⚠️ {subject_id} 處理失敗: {e}")

        # 最終合併寫入單一檔案
        full_content = "# 🗂️ ADOS 全資料集異常事件總索引與詳細日誌\n\n" + summary_md + "\n---\n\n" + details_md
        
        full_out_file = self.output_dir / "subjectxx_full.md"
        with open(full_out_file, "w", encoding="utf-8") as f:
            f.write(full_content)
        
        print(f"\n✅ 任務完成！已成功將所有資料彙整至單一檔案: {full_out_file.absolute()}")

if __name__ == "__main__":
    # 若你的 data 資料夾在 D:\projects\neuroai-transcribe\data
    generator = ADOSSingleMarkdownGenerator(data_dir="data", output_dir="docs/eda/local")
    generator.run()