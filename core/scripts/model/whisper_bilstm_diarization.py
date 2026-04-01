"""
Whisper Medium + BiLSTM 語者分類 checkpoint 的批次 diar 寫入。

實作依賴訓練時的前處理（例如 20s window、weighted_avg 25 步等）；
目前僅保留掛鉤，避免 pipeline 誤以為已可推論。
"""
from __future__ import annotations

from typing import Dict, List


def run_whisper_bilstm_diarization_batch(
    tasks: List[Dict],
    *,
    device: str,
    checkpoint_path: str,
) -> None:
    raise NotImplementedError(
        "Whisper+BiLSTM 語者分類尚未接線（需學弟／訓練端提供 forward 與音訊前處理）。"
        "請暫用 DIARIZATION_BACKEND=pyannote 或 placeholder；"
        f"checkpoint 預設路徑: {checkpoint_path!r}。"
    )
