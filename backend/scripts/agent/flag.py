import os
import json
import time
from typing import Literal, List, Optional
from pydantic import BaseModel, Field
import instructor
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# --- 設定 ---
INPUT_FILE = "data/temp_chunks/chunk_1_0_747928_verified_dataset.json"
OUTPUT_FILE = "data/temp_chunks/chunk_1_0_747928_flagged_for_human.json"

base_url = os.getenv("LLM_API_URL", "http://localhost:8000/v1")
api_key = os.getenv("OPENAI_API_KEY", "sk-local") 

client = OpenAI(base_url=base_url, api_key=api_key, timeout=600.0)
agent = instructor.patch(client, mode=instructor.Mode.JSON)

# =========================================================
# 🚩 The Flag Schema (只標記，不修改)
# =========================================================

class SentenceHealth(BaseModel):
    sentence_id: int
    is_suspicious: bool = Field(..., description="Set to True if the text seems wrong, weird, or nonsensical.")
    
    issue_category: Optional[Literal["Likely_ASR_Error", "Context_Mismatch", "Unintelligible"]] = Field(
        None, description="What kind of weirdness is this?"
    )
    
    reason: Optional[str] = Field(
        None, description="Briefly explain WHY this looks like an error (e.g., 'Phonetically similar to X but context suggests Y')."
    )

class HealthReport(BaseModel):
    assessments: List[SentenceHealth]

# =========================================================
# 🕵️ The Detector Logic
# =========================================================

def run_anomaly_detector(data):
    print("\n🚨 --- Anomaly Detector Started (High Sensitivity Mode) ---")
    
    # 加上 ID 並初始化標記欄位
    for idx, item in enumerate(data):
        item['sentence_id'] = idx
        item['needs_review'] = False
        item['review_reason'] = None
        
    batch_size = 20 
    
    for i in range(0, len(data), batch_size):
        batch = data[i : i + batch_size]
        
        # 準備上下文
        context = "\n".join([f"[ID {s['sentence_id']}] {s['text']}" for s in batch])
        
        print(f"   🔍 Scanning batch {i//batch_size + 1}...", end="\r")
        
        system_prompt = """
        You are a Transcription Quality Control Agent.
        Your job is to **FLAG suspicious sentences** that look like ASR (Automatic Speech Recognition) errors.
        
        **DETECTION CRITERIA (Be Sensitive!):**
        1. **Homophone Nonsense**: The sentence sounds right but means something crazy.
           - Example: "騎士" (Knight) in a daily conversation -> Suspect "其實" (Actually).
           - Example: "公具" -> Suspect "工具".
        2. **Context Clashes**: The word clearly doesn't fit the topic.
        
        **IGNORE (Do NOT Flag):**
        - Reduplication ("球球", "收收") -> This is valid Child Speech.
        - Stuttering ("我...我...") -> Valid.
        - Simple grammar mistakes -> Valid for children.
        
        Your Output: Mark `is_suspicious=True` if you think a human should check it.
        """

        try:
            resp = agent.chat.completions.create(
                model="gemma-3-12b",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": context}
                ],
                response_model=HealthReport,
                temperature=0.1, 
                response_format={"type": "json_object"}
            )
            
            for assessment in resp.assessments:
                if assessment.is_suspicious:
                    target = next((x for x in batch if x['sentence_id'] == assessment.sentence_id), None)
                    if not target: continue
                    
                    # 寫入標記
                    target['needs_review'] = True
                    target['review_reason'] = f"[{assessment.issue_category}] {assessment.reason}"
                    
                    # 在終端機印出來給你看，讓你心裡有底
                    print(f"\n      🚩 Flagged ID {assessment.sentence_id}: {target['text']}")
                    print(f"         Reason: {assessment.reason}")

        except Exception as e:
            print(f"\n   ⚠️ Error: {e}")
            continue

    print("\n   ✅ Detection complete.")
    return data

if __name__ == "__main__":
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)
        
    final_data = run_anomaly_detector(raw_data)
    
    # 計算抓到幾隻蟲
    flagged_count = sum(1 for item in final_data if item.get('needs_review'))
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)
        
    print(f"\n📊 Report Summary:")
    print(f"   Total Sentences: {len(final_data)}")
    print(f"   Suspicious Sentences: {flagged_count}")
    print(f"   Saved to: {OUTPUT_FILE}")