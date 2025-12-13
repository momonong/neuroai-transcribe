import os
import numpy as np
import matplotlib.pyplot as plt
from pydub import AudioSegment
from dotenv import load_dotenv

# 載入 .env 變數
load_dotenv()

def analyze_audio_db(file_path, chunk_size_ms=100):
    """
    計算音訊每 chunk_size_ms 的 dBFS 值
    """
    file_path_show = file_path.replace(os.getenv("TESTER_NAME"),  "TesterName")
    print(f"Loading audio for analysis: {os.path.basename(file_path_show)}...")
    print("這可能需要一點時間，請稍候...")
    
    try:
        audio = AudioSegment.from_file(file_path)
    except Exception as e:
        print(f"Error loading file: {e}")
        return None, None, None

    # 為了繪圖效能，我們不需要每個 sample 都算，每 100ms 算一次平均 dBFS 即可
    chunks_db = []
    timestamps = []
    
    total_len = len(audio)
    
    # 遍歷音訊
    for i in range(0, total_len, chunk_size_ms):
        chunk = audio[i:i+chunk_size_ms]
        db = chunk.dBFS
        
        # 處理無限小的靜音 (pydub 回傳 -inf)
        if db == -float('inf'):
            db = -90 # 設定一個地板值 (Floor)
            
        chunks_db.append(db)
        timestamps.append(i / 1000) # 轉成秒

    return np.array(timestamps), np.array(chunks_db), total_len/1000

def plot_energy_distribution(file_path):
    timestamps, dbs, duration_sec = analyze_audio_db(file_path)
    
    if timestamps is None:
        return

    # --- 統計數據計算 ---
    avg_db = np.mean(dbs)
    min_db = np.min(dbs)
    max_db = np.max(dbs)
    
    # 計算分位數 (Quantiles) 來排除極端值干擾
    q10 = np.percentile(dbs, 10) # 只有 10% 的聲音比這更小 (這通常接近背景噪音底噪)
    
    print("-" * 30)
    print(f"📊 分析報告 (Analysis Report)")
    print(f"檔案時長: {duration_sec/60:.2f} 分鐘")
    print(f"最大音量 (Max): {max_db:.2f} dB")
    print(f"平均音量 (Avg): {avg_db:.2f} dB")
    print(f"最小音量 (Min): {min_db:.2f} dB")
    print(f"底部 10% 音量線 (噪音底噪參考): {q10:.2f} dB")
    print("-" * 30)

    # --- 繪圖設定 ---
    plt.figure(figsize=(15, 8))
    
    # 1. 繪製主波形
    plt.plot(timestamps, dbs, label='Volume (dBFS)', color='#1f77b4', alpha=0.6, linewidth=0.5)
    
    # 2. 標示平均線
    plt.axhline(y=avg_db, color='green', linestyle='-', linewidth=2, label=f'Average ({avg_db:.1f} dB)')
    
    # 3. 標示您原本設定的閥值 (-40dB)
    plt.axhline(y=-40, color='red', linestyle='--', linewidth=2, label='Original Threshold (-40 dB)')
    
    # 4. 標示建議的新閥值 (比底噪稍微高一點點)
    suggested_thresh = q10 + 2 # 稍微寬容一點
    plt.axhline(y=suggested_thresh, color='orange', linestyle='--', linewidth=2, label=f'Suggested Threshold (~{suggested_thresh:.1f} dB)')

    # 5. 標示理想的切分時間點 (1/4, 2/4, 3/4)
    target_cuts = [duration_sec * 0.25, duration_sec * 0.5, duration_sec * 0.75]
    for cut in target_cuts:
        plt.axvline(x=cut, color='purple', linestyle=':', linewidth=2, alpha=0.8)
        plt.text(cut, max_db, f" Target\n {cut/60:.1f}m", color='purple', ha='center', va='bottom')

    plt.title(f"Audio Energy Profile: {os.path.basename(file_path)}")
    plt.xlabel("Time (seconds)")
    plt.ylabel("Volume (dBFS)")
    plt.legend(loc='upper right')
    plt.grid(True, alpha=0.3)
    
    # 存檔
    output_file = "audio_eda_report.png"
    plt.savefig(output_file, dpi=150)
    print(f"✅ 圖表已儲存為: {output_file}")
    print("請打開圖片查看，觀察紅色虛線(-40dB)是否都在藍色波形下方？如果是，代表閥值設太低了。")

if __name__ == "__main__":
    video_file = os.getenv("VIDEO_FILE")
    if video_file:
        plot_energy_distribution(video_file)
    else:
        print("❌ Error: VIDEO_FILE not found in .env")