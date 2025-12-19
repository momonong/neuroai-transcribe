import json
from typing import Literal, List, Optional
from pydantic import BaseModel, Field
import instructor
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# 指向 Local LLM
client = OpenAI(base_url="http://host.docker.internal:8000/v1", api_key="sk-local", timeout=600.0)
agent = instructor.patch(client, mode=instructor.Mode.JSON)

class SentenceHealth(BaseModel):
    sentence_id: int
    is_suspicious: bool = Field(..., description="True if text seems wrong/weird.")
    issue_category: Optional[Literal["Likely_ASR_Error", "Context_Mismatch", "Unintelligible"]] = Field(None)
    reason: Optional[str] = Field(None)

class HealthReport(BaseModel):
    assessments: List[SentenceHealth]

def run_anomaly_detector(data):
    print("\n🚨 --- Anomaly Detector Started ---")
    
    # 確保每個 item 都有 sentence_id
    for idx, item in enumerate(data):
        item['sentence_id'] = idx # 重新確保 ID 連續
        item['needs_review'] = False
        item['review_reason'] = None
        
    batch_size = 10 # 縮小一點避免 LLM 暈倒
    
    for i in range(0, len(data), batch_size):
        batch = data[i : i + batch_size]
        context = "\n".join([f"[ID {s['sentence_id']}] {s['text']}" for s in batch])
        
        print(f"   🔍 Scanning batch {i//batch_size + 1}...", end="\r")
        
        system_prompt = "You are a Transcription QA Agent. Flag homophone errors or nonsense context."

        try:
            resp = agent.chat.completions.create(
                model="gemma-2-9b-it",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": context}
                ],
                response_model=HealthReport,
                temperature=0.1
            )
            
            for assessment in resp.assessments:
                if assessment.is_suspicious:
                    target = next((x for x in batch if x['sentence_id'] == assessment.sentence_id), None)
                    if target:
                        target['needs_review'] = True
                        target['review_reason'] = f"[{assessment.issue_category}] {assessment.reason}"
                        print(f"\n      🚩 Flagged ID {assessment.sentence_id}: {target['text']}")

        except Exception as e:
            print(f"   ⚠️ Flag Error: {e}")
            continue

    return data