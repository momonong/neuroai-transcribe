import os
import re
import json
import argparse
from pathlib import Path
from datetime import datetime

import torch
import librosa
import soundfile as sf
import matplotlib.pyplot as plt
import matplotlib.patches as patches

from pyannote.audio import Pipeline


PIPELINE_MODEL = "pyannote/speaker-diarization-3.1"


def parse_args():
    parser = argparse.ArgumentParser(description="Formal diarization script with optional evaluation.")
    parser.add_argument("--subject", type=str, required=True, help="Subject ID, e.g. subject11")
    parser.add_argument("--audio", type=str, default=None, help="Optional explicit audio path")
    parser.add_argument("--output-root", type=str, default="data", help="Root data directory")
    parser.add_argument("--plot-dir", type=str, default="docs/eda/diarization", help="Directory to save timeline PNG")

    parser.add_argument("--full-audio", action="store_true", help="Run diarization on the full audio")
    parser.add_argument("--start-sec", type=float, default=0.0, help="Start second for partial diarization")
    parser.add_argument("--duration", type=float, default=180.0, help="Duration for partial diarization")

    parser.add_argument("--num-speakers", type=int, default=None, help="Exact number of speakers")
    parser.add_argument("--min-speakers", type=int, default=None, help="Minimum number of speakers")
    parser.add_argument("--max-speakers", type=int, default=None, help="Maximum number of speakers")

    parser.add_argument("--reference", type=str, default=None, help="Optional reference file path (.json or .srt)")
    parser.add_argument("--save-rttm", action="store_true", help="Also save RTTM output if supported")

    return parser.parse_args()


def resolve_annotation(output_obj):
    print(f"🔍 diarization output type: {type(output_obj)}")

    if hasattr(output_obj, "itertracks"):
        print("✅ Output 本身就是 Annotation，可直接 itertracks")
        return output_obj

    candidate_attrs = [
        "speaker_diarization",
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
        f"Unsupported diarization output type: {type(output_obj)}"
    )


def find_default_audio(subject_id, output_root):
    source_dir = Path(output_root) / subject_id / "source"
    base_id = subject_id.split('_')[0]
    candidates = [
        source_dir / f"{subject_id}.wav",
        source_dir / f"{subject_id}.mp3",
        source_dir / f"{subject_id}.WAV",
        source_dir / f"{subject_id}.MP3",
        source_dir / f"{base_id}.wav",
        source_dir / f"{base_id}.mp3",
        source_dir / f"{base_id}.WAV",
        source_dir / f"{base_id}.MP3",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(f"找不到預設音訊檔，請確認 {source_dir} 下是否有 {subject_id}.wav 或 {base_id}.wav")


def load_audio_for_diarization(audio_path, subject_id, start_sec, duration, full_audio):
    if full_audio:
        print("📂 載入整段音訊")
        y, sr = librosa.load(str(audio_path), sr=16000)
        actual_start = 0.0
        actual_duration = len(y) / sr
    else:
        print(f"📂 截取音訊片段: {start_sec}s - {start_sec + duration}s")
        y, sr = librosa.load(str(audio_path), sr=16000, offset=start_sec, duration=duration)
        actual_start = start_sec
        actual_duration = len(y) / sr

    temp_dir = Path(f"data/{subject_id}/source")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_wav = temp_dir / "temp_diar_test.wav"
    sf.write(str(temp_wav), y, sr)

    return temp_wav, sr, actual_start, actual_duration


def build_pipeline():
    print("⏳ 載入模型權重 (請確保 HF Token 已登入並獲得授權)...")
    pipeline = Pipeline.from_pretrained(PIPELINE_MODEL, token=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"💻 運算設備: {device}")
    pipeline.to(device)
    return pipeline, device


def run_diarization(pipeline, temp_wav, num_speakers=None, min_speakers=None, max_speakers=None):
    kwargs = {}
    if num_speakers is not None:
        kwargs["num_speakers"] = num_speakers
    else:
        if min_speakers is not None:
            kwargs["min_speakers"] = min_speakers
        if max_speakers is not None:
            kwargs["max_speakers"] = max_speakers

    print(f"🧠 進行聲紋特徵抽取與分群... kwargs={kwargs}")
    raw_output = pipeline(str(temp_wav), **kwargs)
    annotation = resolve_annotation(raw_output)
    return raw_output, annotation


def annotation_to_segments(annotation, offset_sec=0.0):
    segments = []
    for turn, _, speaker in annotation.itertracks(yield_label=True):
        start = float(turn.start) + offset_sec
        end = float(turn.end) + offset_sec
        segments.append({
            "start": round(start, 3),
            "end": round(end, 3),
            "speaker": str(speaker),
            "duration": round(float(turn.end - turn.start), 3),
        })
    segments.sort(key=lambda x: (x["start"], x["end"]))
    return segments


def compute_stats(segments):
    stats = {
        "total_segments": len(segments),
        "total_speech_duration": round(sum(s["duration"] for s in segments), 3),
        "speakers": {}
    }

    by_speaker = {}
    for seg in segments:
        spk = seg["speaker"]
        by_speaker.setdefault(spk, []).append(seg)

    total_duration = stats["total_speech_duration"]
    for spk, segs in by_speaker.items():
        dur = sum(s["duration"] for s in segs)
        stats["speakers"][spk] = {
            "segments": len(segs),
            "total_duration": round(dur, 3),
            "avg_segment_duration": round(dur / len(segs), 3) if segs else 0.0,
            "ratio_of_speech": round(dur / total_duration, 4) if total_duration > 0 else 0.0,
            "first_start": segs[0]["start"],
            "last_end": segs[-1]["end"],
        }

    return stats


def save_json(data, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def draw_interaction_timeline(segments, total_duration, output_dir, subject_id, title_suffix=""):
    fig, ax = plt.subplots(figsize=(16, 3.5))

    colors = {
        "SPEAKER_00": "#1f77b4",
        "SPEAKER_01": "#2ca02c",
        "SPEAKER_02": "#ff7f0e",
        "SPEAKER_03": "#d62728",
        "SPEAKER_04": "#9467bd",
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
            facecolor=color
        )
        ax.add_patch(rect)

    y_ticks = [y + 4 for y in speaker_to_y.values()]
    y_labels = list(speaker_to_y.keys())

    x_max = max(total_duration, max((s["end"] for s in segments), default=0))
    ax.set_xlim(0, x_max)
    ax.set_ylim(-5, max([0] + list(speaker_to_y.values())) + 15)
    ax.set_yticks(y_ticks)
    ax.set_yticklabels(y_labels)
    ax.set_xlabel("Time (seconds)")
    ax.set_title(f"Speaker Interaction Timeline - {subject_id}{title_suffix}")
    ax.grid(True, axis="x", linestyle="--", alpha=0.5)

    plt.tight_layout()

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    png_path = out_dir / f"{subject_id}_diarization_timeline.png"
    plt.savefig(png_path, dpi=300)
    plt.close(fig)

    print(f"✅ 時間軸圖表已儲存至: {png_path}")
    return str(png_path)


def parse_srt_time(time_str):
    h, m, s_ms = time_str.split(":")
    s, ms = s_ms.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_srt_reference(srt_path):
    text = Path(srt_path).read_text(encoding="utf-8", errors="ignore").strip()
    blocks = re.split(r"\n\s*\n", text)

    segments = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3:
            continue

        if "-->" not in lines[1]:
            continue

        start_str, end_str = [x.strip() for x in lines[1].split("-->")]
        start = parse_srt_time(start_str)
        end = parse_srt_time(end_str)
        content = " ".join(lines[2:]).strip()

        speaker = None
        text_only = content

        match = re.match(r"^\[?([A-Za-z0-9_\-\u4e00-\u9fff]+)\]?\s*[:：]\s*(.+)$", content)
        if match:
            speaker = match.group(1).strip()
            text_only = match.group(2).strip()

        segments.append({
            "start": round(start, 3),
            "end": round(end, 3),
            "speaker": speaker,
            "text": text_only
        })

    return segments


def parse_json_reference(json_path):
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))

    if isinstance(data, dict) and "segments" in data:
        raw_segments = data["segments"]
    elif isinstance(data, list):
        raw_segments = data
    else:
        raise ValueError("Unsupported JSON reference format")

    segments = []
    for seg in raw_segments:
        if "start" not in seg or "end" not in seg:
            continue
        segments.append({
            "start": round(float(seg["start"]), 3),
            "end": round(float(seg["end"]), 3),
            "speaker": seg.get("speaker"),
            "text": seg.get("text", "")
        })

    return segments


def load_reference(reference_path):
    ref_path = Path(reference_path)
    if not ref_path.exists():
        raise FileNotFoundError(f"Reference file not found: {reference_path}")

    if ref_path.suffix.lower() == ".srt":
        return parse_srt_reference(ref_path)
    if ref_path.suffix.lower() == ".json":
        return parse_json_reference(ref_path)

    raise ValueError("Reference file must be .srt or .json")


def overlap_duration(a_start, a_end, b_start, b_end):
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def evaluate_diarization(pred_segments, ref_segments):
    ref_with_speaker = [r for r in ref_segments if r.get("speaker")]
    result = {
        "reference_total_segments": len(ref_segments),
        "reference_segments_with_speaker": len(ref_with_speaker),
        "prediction_total_segments": len(pred_segments),
        "comparable": False,
        "message": None,
        "summary": {},
        "segment_matches": [],
        "speaker_confusion": {}
    }

    if not ref_with_speaker:
        result["message"] = (
            "Reference loaded successfully, but no speaker labels were found. "
            "Speaker diarization evaluation was skipped."
        )
        return result

    result["comparable"] = True

    total_ref_duration = 0.0
    total_overlap = 0.0
    majority_match_count = 0

    confusion = {}

    for idx, ref in enumerate(ref_with_speaker):
        ref_start = ref["start"]
        ref_end = ref["end"]
        ref_speaker = ref["speaker"]
        duration = max(0.0, ref_end - ref_start)
        total_ref_duration += duration

        speaker_overlap = {}
        best_pred_speaker = None
        best_overlap = 0.0

        for pred in pred_segments:
            ov = overlap_duration(ref_start, ref_end, pred["start"], pred["end"])
            if ov <= 0:
                continue
            pred_spk = pred["speaker"]
            speaker_overlap[pred_spk] = speaker_overlap.get(pred_spk, 0.0) + ov

        if speaker_overlap:
            best_pred_speaker, best_overlap = max(speaker_overlap.items(), key=lambda x: x[1])
            total_overlap += best_overlap

            confusion.setdefault(ref_speaker, {})
            confusion[ref_speaker][best_pred_speaker] = confusion[ref_speaker].get(best_pred_speaker, 0.0) + best_overlap

            if best_pred_speaker == ref_speaker:
                majority_match_count += 1

        result["segment_matches"].append({
            "ref_index": idx,
            "ref_start": ref_start,
            "ref_end": ref_end,
            "ref_speaker": ref_speaker,
            "ref_text": ref.get("text", ""),
            "best_pred_speaker": best_pred_speaker,
            "best_overlap": round(best_overlap, 3),
            "coverage_ratio": round(best_overlap / duration, 4) if duration > 0 else 0.0,
            "all_overlap_by_pred_speaker": {k: round(v, 3) for k, v in speaker_overlap.items()}
        })

    result["speaker_confusion"] = {
        ref_spk: {pred_spk: round(sec, 3) for pred_spk, sec in pred_map.items()}
        for ref_spk, pred_map in confusion.items()
    }

    result["summary"] = {
        "total_reference_duration": round(total_ref_duration, 3),
        "total_majority_overlap": round(total_overlap, 3),
        "weighted_overlap_ratio": round(total_overlap / total_ref_duration, 4) if total_ref_duration > 0 else 0.0,
        "majority_match_count": majority_match_count,
        "majority_match_ratio": round(majority_match_count / len(ref_with_speaker), 4) if ref_with_speaker else 0.0,
    }

    return result


def main():
    args = parse_args()

    print("🚀 啟動正式版 Pyannote Diarization")

    subject_id = args.subject
    output_root = Path(args.output_root)
    subject_dir = output_root / subject_id
    source_dir = subject_dir / "source"
    intermediate_dir = subject_dir / "intermediate"
    final_output_dir = subject_dir / "output"

    audio_path = Path(args.audio) if args.audio else find_default_audio(subject_id, output_root)
    if not audio_path.exists():
        raise FileNotFoundError(f"找不到音訊檔: {audio_path}")

    pipeline, device = build_pipeline()

    temp_wav, sr, actual_start, actual_duration = load_audio_for_diarization(
        audio_path=audio_path,
        subject_id=subject_id,
        start_sec=args.start_sec,
        duration=args.duration,
        full_audio=args.full_audio
    )

    try:
        raw_output, annotation = run_diarization(
            pipeline,
            temp_wav,
            num_speakers=args.num_speakers,
            min_speakers=args.min_speakers,
            max_speakers=args.max_speakers
        )

        segments = annotation_to_segments(annotation, offset_sec=actual_start)
        stats = compute_stats(segments)

        mode_name = "full" if args.full_audio else f"clip_{int(args.start_sec)}_{int(args.start_sec + args.duration)}"
        diar_json_path = intermediate_dir / f"{subject_id}_{mode_name}_diar.json"
        diar_stats_path = intermediate_dir / f"{subject_id}_{mode_name}_diar_stats.json"

        diar_payload = {
            "subject_id": subject_id,
            "audio_path": str(audio_path),
            "pipeline_model": PIPELINE_MODEL,
            "processed_at": datetime.now().isoformat(),
            "device": str(device),
            "mode": "full_audio" if args.full_audio else "partial_audio",
            "start_sec": actual_start,
            "duration": round(actual_duration, 3),
            "num_speakers": args.num_speakers,
            "min_speakers": args.min_speakers,
            "max_speakers": args.max_speakers,
            "total_segments": len(segments),
            "segments": segments,
        }

        save_json(diar_payload, diar_json_path)
        save_json(stats, diar_stats_path)

        print(f"✅ Diarization JSON 已儲存至: {diar_json_path}")
        print(f"✅ 統計 JSON 已儲存至: {diar_stats_path}")

        if args.save_rttm and hasattr(annotation, "write_rttm"):
            rttm_path = intermediate_dir / f"{subject_id}_{mode_name}.rttm"
            with open(rttm_path, "w", encoding="utf-8") as f:
                annotation.write_rttm(f)
            print(f"✅ RTTM 已儲存至: {rttm_path}")

        title_suffix = " (Full Audio)" if args.full_audio else f" ({actual_start:.1f}s - {actual_start + actual_duration:.1f}s)"
        plot_path = draw_interaction_timeline(
            segments,
            total_duration=(actual_start + actual_duration),
            output_dir=args.plot_dir,
            subject_id=subject_id,
            title_suffix=title_suffix
        )

        print("\n📝 前 10 筆分離紀錄:")
        for s in segments[:10]:
            print(f"[{s['start']:07.2f}s -> {s['end']:07.2f}s] {s['speaker']}")

        if args.reference:
            print(f"\n📚 載入 reference: {args.reference}")
            ref_segments = load_reference(args.reference)

            eval_result = evaluate_diarization(segments, ref_segments)
            eval_payload = {
                "subject_id": subject_id,
                "prediction_file": str(diar_json_path),
                "reference_file": str(args.reference),
                "evaluated_at": datetime.now().isoformat(),
                "comparable": eval_result["comparable"],
                "message": eval_result["message"],
                "summary": eval_result["summary"],
                "speaker_confusion": eval_result["speaker_confusion"],
                "reference_total_segments": eval_result["reference_total_segments"],
                "reference_segments_with_speaker": eval_result["reference_segments_with_speaker"],
                "prediction_total_segments": eval_result["prediction_total_segments"],
                "segment_matches": eval_result["segment_matches"],
            }

            eval_path = final_output_dir / f"{subject_id}_{mode_name}_diar_eval.json"
            save_json(eval_payload, eval_path)
            print(f"✅ Evaluation JSON 已儲存至: {eval_path}")

            if eval_result["comparable"]:
                print("📊 Evaluation summary:")
                for k, v in eval_result["summary"].items():
                    print(f"  - {k}: {v}")
            else:
                print(f"ℹ️ {eval_result['message']}")

    finally:
        if temp_wav.exists():
            temp_wav.unlink()


if __name__ == "__main__":
    main()