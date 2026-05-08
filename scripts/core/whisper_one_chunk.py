"""
單一 chunk 的 Whisper 轉錄，供主流程以子行程呼叫。
用法: python -m core.scripts.whisper_one_chunk <wav_path> <json_path>
子行程崩潰不會拖垮主流程，且可設 timeout。
"""
import os
import sys
import json

# 專案根目錄加入 path（腳本在 core/scripts/）
_script_dir = os.path.abspath(os.path.dirname(__file__))
_project_root = os.path.dirname(os.path.dirname(_script_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def main():
    if len(sys.argv) != 3:
        print("Usage: whisper_one_chunk <wav_path> <json_path>", file=sys.stderr)
        sys.exit(1)
    wav_path = sys.argv[1]
    json_path = sys.argv[2]

    import torch
    from opencc import OpenCC
    from faster_whisper import WhisperModel
    from core.config import config

    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    cc = OpenCC("s2twp")

    model = WhisperModel(
        config.whisper_model,
        device=device,
        compute_type=compute_type,
        download_root=config.model_cache_dir,
        cpu_threads=4,
        num_workers=1,
    )
    segments, info = model.transcribe(
        wav_path,
        beam_size=config.whisper_beam_size,
        word_timestamps=True,
        vad_filter=True,
    )
    results = []
    for seg in list(segments):
        text_traditional = cc.convert(seg.text.strip())
        words_list = []
        if seg.words:
            for w in seg.words:
                words_list.append({
                    "start": w.start,
                    "end": w.end,
                    "word": cc.convert(w.word),
                })
        results.append({
            "start": seg.start,
            "end": seg.end,
            "text": text_traditional,
            "words": words_list,
        })
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"whisper_one_chunk failed: {e}", file=sys.stderr)
        sys.exit(1)
