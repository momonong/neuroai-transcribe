from __future__ import annotations

from typing import Any
from pathlib import Path
from shared.file_manager import file_manager


def _get_original_audio_path(case_name: str) -> Path:
    """Helper function to get the original audio/video path for a given case."""
    video_files_info = file_manager.find_video_files()
    for video_info in video_files_info:
        if video_info["case_name"] == case_name:
            return Path(video_info["path"])
    raise FileNotFoundError(f"Original audio/video file not found for case: {case_name}")


def run_segment_reinfer(
    *,
    case_name: str,
    chunk_filename: str,
    start_sec: float,
    end_sec: float,
    sentence_id: float | None,
) -> dict[str, Any]:
    """
    依 chunk 與 [start_sec, end_sec]（與 transcript JSON 內 segment 時間一致）執行重新辨識。

    實作建議：
    - 由 case_name / chunk_filename 解析出對應 wav 或影片路徑
    - 將 start_sec、end_sec 換算成音檔上的絕對時間（若需加上 chunk offset）
    - 呼叫 Whisper 後回傳 {"ok": True, "text": "...", "message": "..."}

    Returns:
        與 SegmentReinferResponse 對齊的 dict。
    """
    try:
        # 1. Get the original video/audio file path
        original_audio_path = _get_original_audio_path(case_name)

        # 2. Extract chunk start and end times from chunk_filename
        # chunk_filename format might be chunk_X_startMS_endMS... or chunk_X_flagged_for_human.json
        parts = Path(chunk_filename).stem.split('_')
        if len(parts) < 2:
            raise ValueError(f"Chunk filename '{chunk_filename}' does not match expected format.")
        
        chunk_start_ms = 0
        chunk_end_ms = 60000
        parsed_from_name = False
        
        if len(parts) >= 4 and parts[2].isdigit() and parts[3].isdigit():
            chunk_start_ms = int(parts[2])
            chunk_end_ms = int(parts[3])
            parsed_from_name = True
        else:
            # Fallback: Find the original wav file in intermediate folder
            chunk_idx = parts[1]
            inter_dir = file_manager.get_intermediate_dir(case_name)
            wav_files = list(inter_dir.glob(f"chunk_{chunk_idx}_*.wav"))
            if wav_files:
                wav_parts = wav_files[0].stem.split('_')
                if len(wav_parts) >= 4 and wav_parts[2].isdigit() and wav_parts[3].isdigit():
                    chunk_start_ms = int(wav_parts[2])
                    chunk_end_ms = int(wav_parts[3])
                    parsed_from_name = True

        if not parsed_from_name:
            print(f"Warning: Could not parse exact start/end for '{chunk_filename}', defaulting to 0-60s.")

        # 3. Calculate absolute segment times in the original audio
        # 前端傳來的 start_sec 與 end_sec 已是加上 chunk_offset_sec 的絕對時間，故不需再次加上 chunk_start_ms。
        absolute_start_sec = float(start_sec)
        absolute_end_sec = float(end_sec)

        # 4. Call Whisper service via HTTP (Docker microservice)
        import urllib.request
        import json
        import os
        
        # Determine whisper service URL. Inside docker network, it's 'whisper'
        # Default to localhost if running backend locally.
        whisper_host = os.getenv("WHISPER_SERVICE_HOST", "whisper")
        whisper_port = os.getenv("WHISPER_SERVICE_PORT", "8002")
        url = f"http://{whisper_host}:{whisper_port}/reinfer"
        
        payload = {
            "wav_path": str(original_audio_path.resolve()),
            "start_sec": absolute_start_sec,
            "end_sec": absolute_end_sec
        }
        
        req = urllib.request.Request(
            url, 
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        
        try:
            with urllib.request.urlopen(req) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                
            if not res_data.get("ok"):
                raise RuntimeError(res_data.get("message", "Whisper service returned error"))
                
            text = res_data.get("text", "")
            
            return {
                "ok": True,
                "text": text,
                "message": "重新辨識成功",
                "absolute_start_sec": absolute_start_sec,
                "absolute_end_sec": absolute_end_sec,
            }
        except Exception as e:
            raise RuntimeError(f"呼叫 Whisper 服務失敗: {e}")

    except FileNotFoundError as e:
        return {"ok": False, "text": None, "message": str(e)}
    except ValueError as e:
        return {"ok": False, "text": None, "message": f"解析 chunk 資訊失敗: {e}"}
    except Exception as e:
        return {"ok": False, "text": None, "message": f"重新辨識處理失敗: {e}"}
