"""
不依 Pyannote／BiLSTM 時，依 Whisper 段時間軸產生符合 pipeline 契約的 *_diar.json。
供 DIARIZATION_BACKEND=placeholder 與測試腳本共用。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def whisper_json_path_for_wav(wav_path: str) -> Path:
    p = Path(wav_path)
    return p.parent / f"{p.stem}_whisper.json"


def whisper_to_placeholder_diar(
    whisper_segments: List[Dict[str, Any]],
    speaker: str = "PLACEHOLDER_SPEAKER",
) -> List[Dict[str, Any]]:
    """每個 Whisper ASR 段對應一條 diar（時間相同、speaker 固定）。"""
    out: List[Dict[str, Any]] = []
    for w in whisper_segments:
        out.append(
            {
                "start": float(w["start"]),
                "end": float(w["end"]),
                "speaker": speaker,
            }
        )
    return out


def write_placeholder_diar_from_whisper(
    wav_path: str,
    diar_json_path: str,
    speaker: str,
) -> bool:
    """
    讀取與 wav 同幹檔名的 *_whisper.json，寫入 diar_json_path。
    若找不到或格式錯誤回傳 False。
    """
    wj = whisper_json_path_for_wav(wav_path)
    if not wj.is_file():
        return False
    try:
        with open(wj, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, list):
        return False
    diar = whisper_to_placeholder_diar(data, speaker=speaker)
    out = Path(diar_json_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(diar, f, ensure_ascii=False, indent=2)
    return True
