import os
import argparse
from pathlib import Path

import torch
import librosa
import soundfile as sf
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from pyannote.audio import Pipeline


PIPELINE_MODEL = "pyannote/speaker-diarization-3.1"


def resolve_annotation(output_obj):
    """
    相容 pyannote.audio 3.x / 4.x 的輸出格式
    目標是拿到可 itertracks(...) 的 Annotation
    """
    print(f"🔍 diarization output type: {type(output_obj)}")

    if hasattr(output_obj, "itertracks"):
        print("✅ Output 本身就是 Annotation，可直接 itertracks")
        return output_obj

    candidate_attrs = [
        "speaker_diarization",  # pyannote.audio 4.x 常見
        "annotation",
        "diarization",
    ]

    for attr in candidate_attrs:
        if hasattr(output_obj, attr):
            candidate = getattr(output_obj, attr)
            print(f"🔍 found attribute: {attr}, type={type(candidate)}")
            if hasattr(candidate, "itertracks"):
                print(f"✅ 使用 output.{attr} 作為 Annotation")
                return candidate

    print("🧪 dir(output_obj):")
    print(dir(output_obj))
    raise TypeError(
        f"Unsupported diarization output type: {type(output_obj)}. "
        "請把上面的 type 與 dir 輸出貼出來。"
    )


def run_fast_diarization(wav_path, output_dir, subject_id, start_sec=0.0, duration=180.0):
    print("🚀 啟動 Pyannote Diarization 3.1")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"💻 運算設備: {device}")

    print("⏳ 載入模型權重 (請確保 HF Token 已登入並獲得授權)...")
    pipeline = Pipeline.from_pretrained(PIPELINE_MODEL, token=True)
    pipeline.to(device)

    print(f"📂 截取音訊片段: {start_sec}s - {start_sec + duration}s")
    y, sr = librosa.load(wav_path, sr=16000, offset=start_sec, duration=duration)

    temp_dir = Path(f"data/{subject_id}/source")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_wav = temp_dir / "temp_diar_test.wav"
    sf.write(str(temp_wav), y, sr)

    print("🧠 進行聲紋特徵抽取與分群...")
    raw_output = pipeline(str(temp_wav), num_speakers=2)

    annotation = resolve_annotation(raw_output)

    segments = []
    for turn, _, speaker in annotation.itertracks(yield_label=True):
        segments.append({
            "start": float(turn.start),
            "end": float(turn.end),
            "speaker": str(speaker),
            "duration": float(turn.end - turn.start),
        })

    if temp_wav.exists():
        temp_wav.unlink()

    print(f"📈 共取得 {len(segments)} 筆 segments")
    print("\n📝 前 10 筆分離紀錄:")
    for s in segments[:10]:
        print(f"[{s['start']:05.1f}s -> {s['end']:05.1f}s] {s['speaker']}")

    print("📊 繪製互動時間軸...")
    draw_interaction_timeline(segments, duration, output_dir, subject_id)


def draw_interaction_timeline(segments, total_duration, output_dir, subject_id):
    fig, ax = plt.subplots(figsize=(15, 3))

    colors = {
        "SPEAKER_00": "#1f77b4",
        "SPEAKER_01": "#2ca02c",
        "SPEAKER_02": "#ff7f0e",
    }

    speaker_names = sorted(list({seg["speaker"] for seg in segments}))
    speaker_to_y = {speaker: idx * 10 for idx, speaker in enumerate(speaker_names)}

    for seg in segments:
        speaker = seg["speaker"]
        color = colors.get(speaker, "#7f7f7f")
        y_pos = speaker_to_y[speaker]

        rect = patches.Rectangle(
            (seg["start"], y_pos),
            seg["duration"],
            8,
            linewidth=1,
            edgecolor="none",
            facecolor=color,
        )
        ax.add_patch(rect)

    y_ticks = [y + 4 for y in speaker_to_y.values()]
    y_labels = list(speaker_to_y.keys())

    ax.set_xlim(0, total_duration)
    ax.set_ylim(-5, max([0] + list(speaker_to_y.values())) + 15)
    ax.set_yticks(y_ticks)
    ax.set_yticklabels(y_labels)
    ax.set_xlabel("Time (seconds)")
    ax.set_title(f"Speaker Interaction Timeline - {subject_id} (First 3 mins)")
    ax.grid(True, axis="x", linestyle="--", alpha=0.6)

    plt.tight_layout()

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    png_path = out_dir / f"{subject_id}_diarization_timeline.png"
    plt.savefig(png_path, dpi=300)
    plt.close(fig)

    print(f"✅ 完成！時間軸圖表已儲存至: {png_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", type=str, required=True)
    parser.add_argument("--start-sec", type=float, default=0.0)
    parser.add_argument("--duration", type=float, default=180.0)
    args = parser.parse_args()

    wav_file = f"data/{args.subject}/source/{args.subject.split('_')[0]}.wav"
    out_dir = "docs/eda/diarization/"

    if os.path.exists(wav_file):
        run_fast_diarization(
            wav_file,
            out_dir,
            args.subject,
            start_sec=args.start_sec,
            duration=args.duration,
        )
    else:
        print(f"❌ 找不到音檔: {wav_file}")