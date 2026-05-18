import whisper
import argparse
import os

def test_transcription(subject_id):
    # 路徑指向 data/{subject}/output/
    orig_wav = f"data/{subject_id}/output/{subject_id}_original_clip.wav"
    wpe_wav = f"data/{subject_id}/output/{subject_id}_wpe_processed.wav"

    if not os.path.exists(orig_wav) or not os.path.exists(wpe_wav):
        print(f"❌ 找不到必要的音檔，請先執行 wpe_dereverb.py 產生片段。\n缺少: {orig_wav} 或 {wpe_wav}")
        return

    print("🤖 載入 Whisper 模型 (large-v3)...")
    model = whisper.load_model("large-v3", device="cuda")
    
    print("\n🎧 1. 轉錄 [原始未處理] 音檔...")
    res_orig = model.transcribe(orig_wav, language="zh")
    print(f"❌ 原始結果: {res_orig['text']}")
    
    print("\n🎧 2. 轉錄 [WPE 去殘響] 音檔...")
    res_wpe = model.transcribe(wpe_wav, language="zh")
    print(f"✅ WPE 結果: {res_wpe['text']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", type=str, required=True)
    args = parser.parse_args()
    test_transcription(args.subject)