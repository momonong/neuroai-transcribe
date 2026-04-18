import os
import librosa
import torch
from faster_whisper import WhisperModel
from opencc import OpenCC

_whisper_model = None
_opencc = None

def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        print("🔄 Loading Whisper Model for Inference...", flush=True)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        
        model_size = os.getenv("WHISPER_MODEL", "large-v3")
        cache_dir = os.getenv("MODEL_CACHE_DIR", "/app/models_cache")
        
        _whisper_model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            download_root=cache_dir,
            cpu_threads=4,
            num_workers=1,
        )
        print("✅ Whisper Model Loaded.", flush=True)
    return _whisper_model

def _get_opencc():
    global _opencc
    if _opencc is None:
        _opencc = OpenCC("s2twp")
    return _opencc

def reinfer_audio_segment(wav_path: str, start_sec: float, end_sec: float) -> str:
    """
    用於重新辨識小片段。
    """
    duration = end_sec - start_sec
    if duration <= 0:
        raise ValueError("end_sec must be greater than start_sec")
        
    print(f"🎧 Re-inferencing segment: {wav_path} [{start_sec:.2f}s - {end_sec:.2f}s]")
    audio, _ = librosa.load(wav_path, sr=16000, offset=start_sec, duration=duration)
    
    model = _get_whisper_model()
    # 從環境變數讀取語言，預設為 zh 避免幻聽
    language = os.getenv("WHISPER_LANGUAGE", "zh")
    beam_size = int(os.getenv("WHISPER_BEAM_SIZE", "5"))
    
    segments, info = model.transcribe(
        audio,
        language=language,
        beam_size=beam_size,
        word_timestamps=False,
        vad_filter=True,
    )
    
    full_text = " ".join([seg.text.strip() for seg in list(segments)])
    cc = _get_opencc()
    text_traditional = cc.convert(full_text)
    
    print(f"✅ Result: {text_traditional}")
    return text_traditional

def transcribe_full_audio(wav_path: str) -> list:
    """
    轉錄整個音檔，並回傳包含 Word Timestamps 的段落清單。
    """
    print(f"🎧 Transcribing full audio: {wav_path}")
    model = _get_whisper_model()
    cc = _get_opencc()
    language = os.getenv("WHISPER_LANGUAGE", "zh")
    beam_size = int(os.getenv("WHISPER_BEAM_SIZE", "5"))

    segments, info = model.transcribe(
        wav_path,
        language=language,
        beam_size=beam_size,
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
    print(f"✅ Transcription complete. ({len(results)} segments)")
    return results
