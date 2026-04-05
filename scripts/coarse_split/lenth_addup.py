import os
from pydub import AudioSegment
from dotenv import load_dotenv

load_dotenv()

def verify_integrity(original_file, chunk_folder="data/temp_chunks"):
    print(f"Verifying: {original_file}...")
    
    # 1. 讀取原始音軌長度
    original = AudioSegment.from_file(original_file)
    orig_len = len(original)
    
    # 2. 讀取所有切分後的 WAV 長度總和
    chunk_files = sorted([f for f in os.listdir(chunk_folder) if f.endswith(".wav")])
    total_chunk_len = 0
    
    print(f"\n--- Chunk Details ---")
    for f in chunk_files:
        path = os.path.join(chunk_folder, f)
        chunk = AudioSegment.from_file(path)
        print(f"{f}: {len(chunk)/1000:.3f} sec")
        total_chunk_len += len(chunk)
        
    print(f"\n--- Result ---")
    print(f"Original Audio Length: {orig_len/1000:.3f} sec")
    print(f"Sum of Chunks Length:  {total_chunk_len/1000:.3f} sec")
    
    diff = abs(orig_len - total_chunk_len)
    print(f"Difference: {diff} ms")
    
    if diff < 100: # 容許 100ms 內的誤差
        print("✅ VERIFICATION PASSED: No audio data lost.")
        print("(Any discrepancy with video player time is due to video/audio track mismatch)")
    else:
        print("❌ WARNING: Significant data loss detected!")

if __name__ == "__main__":
    verify_integrity(os.getenv("VIDEO_FILE"))