from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import os

from reinfer import reinfer_audio_segment, transcribe_full_audio

app = FastAPI(title="Whisper Inference Service")

class ReinferRequest(BaseModel):
    wav_path: str
    start_sec: float
    end_sec: float

class TranscribeRequest(BaseModel):
    wav_path: str

class ReinferResponse(BaseModel):
    ok: bool
    text: str = ""
    message: str = ""

@app.post("/reinfer", response_model=ReinferResponse)
def handle_reinfer(request: ReinferRequest):
    try:
        text = reinfer_audio_segment(
            wav_path=request.wav_path,
            start_sec=request.start_sec,
            end_sec=request.end_sec
        )
        return ReinferResponse(ok=True, text=text, message="Success")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/transcribe")
def handle_transcribe(request: TranscribeRequest):
    try:
        results = transcribe_full_audio(wav_path=request.wav_path)
        return {"ok": True, "results": results}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8002"))
    uvicorn.run("server:app", host="0.0.0.0", port=port, workers=1)
