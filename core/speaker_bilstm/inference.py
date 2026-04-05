from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset
from tqdm import tqdm


def _load_audio_mono_16k(audio_path: str, sample_rate: int) -> Tuple[np.ndarray, float]:
    # 與原 Neuro-AI 保持一致：librosa.load(sr=target, mono=True)
    import librosa

    waveform, _sr = librosa.load(audio_path, sr=int(sample_rate), mono=True)
    waveform = waveform.astype(np.float32, copy=False)
    duration = float(len(waveform)) / float(sample_rate)
    return waveform, duration


def _slice_audio(
    waveform: np.ndarray, sample_rate: int, start_time: float, window_size: float
) -> np.ndarray:
    start_sample = int(start_time * sample_rate)
    num_samples = int(window_size * sample_rate)
    end_sample = start_sample + num_samples
    if end_sample > len(waveform):
        out = np.zeros(num_samples, dtype=np.float32)
        valid = len(waveform) - start_sample
        if valid > 0:
            out[:valid] = waveform[start_sample:len(waveform)]
        return out
    return waveform[start_sample:end_sample].astype(np.float32, copy=False)


def _build_inference_slices(duration: float, window_size: float) -> List[float]:
    # 與 Neuro-AI SpeakerDiarizationDataset(is_training=False) 一致：
    # step = window_size（不重疊）；尾端剩餘超過半窗則補一個尾端窗；太短也至少一窗。
    slices: List[float] = []
    if duration <= 0:
        return slices
    step = float(window_size)
    start = 0.0
    while start + window_size <= duration:
        slices.append(start)
        start += step
    remaining = duration - start
    if remaining > window_size * 0.5:
        start = max(0.0, duration - window_size)
        if not slices or slices[-1] != start:
            slices.append(start)
    if not slices and duration > 0:
        slices.append(0.0)
    return slices


@dataclass
class _InferenceSample:
    waveform: np.ndarray
    duration: float


class _InferenceDataset(Dataset):
    def __init__(self, sample: _InferenceSample, config: Any):
        self.sample = sample
        self.config = config
        self.starts = _build_inference_slices(sample.duration, float(config.window_size))

    def __len__(self) -> int:
        return len(self.starts)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        st = float(self.starts[idx])
        audio = _slice_audio(
            self.sample.waveform,
            int(self.config.sample_rate),
            st,
            float(self.config.window_size),
        )
        return {
            "audio": torch.from_numpy(audio).float(),
            "start_time": st,
        }


def inference_on_audio(
    *,
    model: torch.nn.Module,
    audio_path: str,
    config: Any,
    srt_path: Optional[str] = None,
    rttm_path: Optional[str] = None,
    save_dir: Optional[str] = None,
) -> Dict[str, Any]:
    # 只保留主線需要的最小回傳：predictions（一維 np.int64）
    waveform, duration = _load_audio_mono_16k(audio_path, int(config.sample_rate))
    ds = _InferenceDataset(_InferenceSample(waveform=waveform, duration=duration), config)

    dl = DataLoader(
        ds,
        batch_size=int(getattr(config, "batch_size", 1)),
        shuffle=False,
        num_workers=0,
        drop_last=False,
    )

    model.eval()
    all_preds: List[np.ndarray] = []

    use_amp = bool(getattr(config, "use_amp", False))
    device = config.device

    with torch.no_grad():
        for batch in tqdm(dl, desc="Speaker inference", leave=False):
            audio = batch["audio"].to(device)
            if use_amp:
                from torch.cuda.amp import autocast

                with autocast():
                    logits = model(audio)
            else:
                logits = model(audio)
            preds = torch.argmax(logits, dim=-1).detach().cpu().numpy()
            all_preds.append(preds.reshape(-1))

    predictions = np.concatenate(all_preds, axis=0) if all_preds else np.zeros((0,), dtype=np.int64)
    return {"predictions": predictions}

