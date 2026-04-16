"""
將 Whisper + BiLSTM 語者分類接到主 pipeline：產生 *_diar.json。
這是 core 內部的執行單元，位於 core/speaker_bilstm/diarization_wrapper.py。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np


def _project_root() -> Path:
    # 此檔案在 core/speaker_bilstm/diarization_wrapper.py
    return Path(__file__).resolve().parents[2]


def _patch_torch_load() -> None:
    import torch

    o = torch.load

    def _load(*args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("weights_only", False)
        return o(*args, **kwargs)

    torch.load = _load  # type: ignore[misc]


def _labels_to_time_segments(
    labels: np.ndarray, step_size_ms: float
) -> List[Tuple[int, float, float]]:
    """與 Neuro-AI evaluate.GanttChartVisualizer._labels_to_segments 一致。"""
    segments: List[Tuple[int, float, float]] = []
    if len(labels) == 0:
        return segments
    step_sec = step_size_ms / 1000.0
    current_label = int(labels[0])
    start_frame = 0
    for i in range(len(labels)):
        lab = int(labels[i])
        if lab != current_label:
            t0 = start_frame * step_sec
            t1 = i * step_sec
            segments.append((current_label, t0, t1))
            current_label = lab
            start_frame = i
    t0 = start_frame * step_sec
    t1 = len(labels) * step_sec
    segments.append((current_label, t0, t1))
    return segments


def _predictions_to_diar_list(
    predictions: np.ndarray,
    step_size_ms: float,
    class_names: List[str],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for label_id, t0, t1 in _labels_to_time_segments(predictions, step_size_ms):
        name = (
            class_names[label_id]
            if 0 <= label_id < len(class_names)
            else f"class_{label_id}"
        )
        rows.append(
            {
                "start": float(t0),
                "end": float(t1),
                "speaker": name,
            }
        )
    return rows


class _NeuroInferConfig:
    def __init__(
        self,
        *,
        device: str,
        ckpt_cfg: Dict[str, Any],
        batch_size: int,
    ):
        self.model_size = str(ckpt_cfg.get("model_size", "medium"))
        self.freeze_encoder = bool(ckpt_cfg.get("freeze_encoder", True))
        self.lstm_hidden_size = int(ckpt_cfg.get("lstm_hidden_size", 128))
        self.lstm_num_layers = int(ckpt_cfg.get("lstm_num_layers", 2))
        self.dropout = float(ckpt_cfg.get("dropout", 0.2))
        self.num_classes = int(ckpt_cfg.get("num_classes", 3))
        self.sample_rate = int(ckpt_cfg.get("sample_rate", 16000))
        self.window_size = float(ckpt_cfg.get("window_size", 20.0))
        self.step_size_ms = float(ckpt_cfg.get("step_size_ms", 20.0))
        self.train_overlap_ratio = float(ckpt_cfg.get("train_overlap_ratio", 0.5))
        self.batch_size = batch_size
        self.num_workers = 0
        self.pin_memory = False
        import torch

        self.device = torch.device(device)
        self.use_amp = device == "cuda"
        self.median_filter_size = int(ckpt_cfg.get("median_filter_size", 5))

    @property
    def whisper_model_name(self) -> str:
        return f"openai/whisper-{self.model_size}"


def _class_names_from_core_config() -> List[str]:
    try:
        from core.config import config

        if len(config.speaker_class_labels) >= 3:
            return config.speaker_class_labels[:3]
    except Exception:
        pass
    return ["Child", "Adult", "Silence"]


def run_whisper_bilstm_diarization_batch(
    tasks: List[Dict],
    *,
    device: str,
    checkpoint_path: str,
) -> None:
    ck_path = Path(checkpoint_path)
    if not ck_path.is_file():
        raise FileNotFoundError(f"找不到 checkpoint: {ck_path}")

    _patch_torch_load()
    import torch

    ckpt = torch.load(str(ck_path), map_location="cpu")
    ckpt_cfg: Dict[str, Any] = {}
    if isinstance(ckpt, dict) and isinstance(ckpt.get("config"), dict):
        ckpt_cfg = dict(ckpt["config"])

    batch_size = int(os.getenv("SPEAKER_INFER_BATCH_SIZE", "1"))
    infer_cfg = _NeuroInferConfig(
        device=device, ckpt_cfg=ckpt_cfg, batch_size=max(1, batch_size)
    )
    use_median = os.getenv("SPEAKER_BILSTM_USE_MEDIAN", "1").lower() in (
        "1",
        "true",
        "yes",
    )
    class_names = _class_names_from_core_config()

    try:
        import torch
        from core.speaker_bilstm import inference_on_audio, load_model

        print(
            f"   [whisper_bilstm] 載入模型（HF Whisper + checkpoint）…",
            flush=True,
        )
        model = load_model(infer_cfg, str(ck_path))
        model.eval()

        for idx, task in enumerate(tasks):
            wav_path = task["wav"]
            json_path = task["json"]
            print(
                f"   [{idx+1}/{len(tasks)}] BiLSTM diar: {os.path.basename(wav_path)}",
                flush=True,
            )

            out = inference_on_audio(
                model=model,
                audio_path=wav_path,
                config=infer_cfg,
                srt_path=None,
                rttm_path=None,
                save_dir=None,
            )
            preds = np.asarray(out["predictions"], dtype=np.int64).reshape(-1)

            if use_median and hasattr(model, "median_filter"):
                preds_t = torch.as_tensor(preds, dtype=torch.long, device="cpu")
                preds = model.median_filter.filter_predictions(preds_t).numpy().reshape(-1)

            diar = _predictions_to_diar_list(
                preds, infer_cfg.step_size_ms, class_names
            )
            Path(json_path).parent.mkdir(parents=True, exist_ok=True)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(diar, f, ensure_ascii=False, indent=2)

        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    finally:
        pass
