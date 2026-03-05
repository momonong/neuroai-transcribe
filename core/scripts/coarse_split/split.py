import os
import math
from pydub import AudioSegment
from pydub.silence import detect_silence
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

class SmartAudioSplitter:
    def __init__(self, output_dir="data/temp_chunks"):
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

    def _get_safe_filename(self, file_path):
        """用於 Log 顯示，隱藏敏感資訊"""
        tester_name = os.getenv("TESTER_NAME")
        if tester_name and tester_name in file_path:
            return file_path.replace(tester_name, "Name")
        return file_path

    def _find_quietest_point_in_window(self, audio_segment, step_ms=100):
        """
        當找不到絕對靜音時，掃描這段音訊，找出能量 (RMS) 最低的時間點 (相對時間)。
        """
        min_rms = float('inf')
        best_offset = 0
        
        # 掃描整段視窗
        for i in range(0, len(audio_segment), step_ms):
            chunk = audio_segment[i:i+step_ms]
            if chunk.rms < min_rms:
                min_rms = chunk.rms
                best_offset = i
        
        return best_offset

    def split_audio(self, file_path, num_chunks=4, silence_thresh=-40, min_silence_len=1000):
        """
        將音訊切分成 num_chunks 段。
        優先尋找 silence_thresh 以下的靜音；若失敗，則使用自適應演算法尋找局部最低點。
        """
        safe_name = self._get_safe_filename(file_path)
        print(f"Loading audio: {safe_name}...")
        
        # 讀取音訊
        try:
            audio = AudioSegment.from_file(file_path)
        except Exception as e:
            print(f"Error loading file: {e}")
            return []

        total_duration = len(audio) # 毫秒
        chunk_duration_target = total_duration / num_chunks
        split_points = [0] # 起始點
        
        print(f"Total duration: {total_duration/1000:.2f}s. Target chunk size: {chunk_duration_target/1000:.2f}s")

        for i in range(1, num_chunks):
            target_time = i * chunk_duration_target
            
            # 定義搜尋區間：前後 30 秒
            search_window_ms = 30000 
            search_start = max(0, target_time - search_window_ms)
            search_end = min(total_duration, target_time + search_window_ms)
            
            search_audio = audio[search_start:search_end]
            
            # 策略 A: 尋找絕對靜音 (Strict Silence)
            silences = detect_silence(search_audio, min_silence_len=min_silence_len, silence_thresh=silence_thresh)
            
            actual_split_point = target_time # Default fallback
            method_used = "Forced"

            if silences:
                # 找到靜音，取最接近 target 的靜音中點
                best_diff = float('inf')
                for s_start, s_end in silences:
                    abs_mid = search_start + (s_start + s_end) / 2
                    diff = abs(abs_mid - target_time)
                    if diff < best_diff:
                        best_diff = diff
                        actual_split_point = abs_mid
                method_used = "Silence Detected"
            else:
                # 策略 B: 自適應最低能量點 (Adaptive Low Energy)
                # 當環境太吵找不到絕對靜音時使用
                best_offset = self._find_quietest_point_in_window(search_audio)
                actual_split_point = search_start + best_offset
                method_used = "Adaptive Min Energy"

            print(f"Cut {i}: {method_used} at {actual_split_point/1000:.2f}s (Target: {target_time/1000:.2f}s)")
            split_points.append(actual_split_point)
            
        split_points.append(total_duration) # 終點

        # 開始輸出檔案 (轉為 WAV)
        output_files = []
        for i in range(len(split_points) - 1):
            start = split_points[i]
            end = split_points[i+1]
            
            chunk = audio[start:end]
            
            # 檔名格式: chunk_{i}.wav
            filename = f"chunk_{i+1}_{int(start)}_{int(end)}.wav"
            filepath = os.path.join(self.output_dir, filename)
            
            # 改用 WAV 格式匯出
            chunk.export(filepath, format="wav")
            
            output_files.append({
                "chunk_id": i + 1,
                "file_path": filepath,
                "start_time_ms": start,
                "end_time_ms": end,
                "duration_ms": end - start
            })
            print(f"Exported: {filename}")

        return output_files

# 執行區段
if __name__ == "__main__":
    video_file = os.getenv("VIDEO_FILE")
    if video_file:
        splitter = SmartAudioSplitter()
        metadata = splitter.split_audio(video_file)
        # print(metadata) # 可以註解掉以免洗版
    else:
        print("Error: VIDEO_FILE not found in .env")