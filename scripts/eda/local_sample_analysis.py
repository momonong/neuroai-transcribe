import json
from pathlib import Path

def analyze_subject_local(subject_id):
    transcript_path = Path(f"data/{subject_id}/output/transcript.json")
    if not transcript_path.exists():
        return f"Error: {transcript_path} not found"
        
    with open(transcript_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    # Look for segments with low verification scores or specific patterns
    critical_segments = []
    for entry in data:
        # Heuristic: segments with many "?" might indicate transcription failure
        if entry.get("text", "").count("?") > 5:
            critical_segments.append({
                "interval": f"[{int(entry['start']//60):02d}:{int(entry['start']%60):02d} - {int(entry['end']//60):02d}:{int(entry['end']%60):02d}]",
                "reason": f"High uncertainty in transcription (Score: {entry.get('verification_score', 'N/A')})",
                "text": entry["text"][:50] + "..."
            })
            
    return critical_segments

if __name__ == "__main__":
    for sid in ["subject01", "subject15"]:
        print(f"--- {sid} ---")
        segs = analyze_subject_local(sid)
        for s in segs[:5]:
            print(f"{s['interval']}: {s['reason']}")
            print(f"  {s['text']}")
