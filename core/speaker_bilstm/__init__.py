"""
Whisper + BiLSTM 語者分類（Child/Adult/Silence）推論子模組。

此模組是從專案內原 `Neuro-AI/` 推論路徑萃取出的「最小可用子集」，
用於主線 pipeline diarization backend（`whisper_bilstm`）。
"""

def load_model(*args, **kwargs):
    from .model import load_model as _load_model

    return _load_model(*args, **kwargs)


def inference_on_audio(*args, **kwargs):
    from .inference import inference_on_audio as _inference_on_audio

    return _inference_on_audio(*args, **kwargs)

