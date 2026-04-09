import sys
import json
import argparse
import os

# 專案根目錄加入 path
_script_dir = os.path.abspath(os.path.dirname(__file__))
_project_root = os.path.dirname(_script_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

def main():
    parser = argparse.ArgumentParser(description="Re-infer a segment of audio using Whisper.")
    parser.add_argument("wav_path", help="Path to the original audio/video file.")
    parser.add_argument("start_sec", type=float, help="Absolute start time in seconds.")
    parser.add_argument("end_sec", type=float, help="Absolute end time in seconds.")
    args = parser.parse_args()

    try:
        import librosa
        import torch
        from opencc import OpenCC
        from faster_whisper import WhisperModel
        from core.config import config

        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        cc = OpenCC("s2twp")

        duration = args.end_sec - args.start_sec
        if duration <= 0:
            raise ValueError("end_sec 必須大於 start_sec")

        # 使用 librosa 讀取特定時間段的音訊，並自動轉為 16kHz
        audio, _ = librosa.load(args.wav_path, sr=16000, offset=args.start_sec, duration=duration)

        model = WhisperModel(
            config.whisper_model,
            device=device,
            compute_type=compute_type,
            download_root=config.model_cache_dir,
            cpu_threads=4,
            num_workers=1,
        )

        segments, info = model.transcribe(
            audio,
            beam_size=config.whisper_beam_size,
            word_timestamps=False,
            vad_filter=True,
        )
        
        full_text = " ".join([seg.text.strip() for seg in list(segments)])
        text_traditional = cc.convert(full_text)
        
        # 輸出 JSON 格式供 stdout 解析
        print(json.dumps({"ok": True, "text": text_traditional}, ensure_ascii=False))
        sys.exit(0)
        
    except Exception as e:
        print(json.dumps({"ok": False, "message": str(e)}, ensure_ascii=False))
        sys.exit(1)

if __name__ == "__main__":
    main()
