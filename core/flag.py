import json
import time
from typing import List, Optional, Literal
from enum import Enum
from pydantic import BaseModel, Field
import instructor
from openai import OpenAI, APITimeoutError, APIConnectionError

from .config import config

# --- 1. 定義資料結構 ---
class IssueCategory(str, Enum):
    LIKELY_ASR_ERROR = "Likely_ASR_Error"
    CONTEXT_MISMATCH = "Context_Mismatch"
    UNINTELLIGIBLE = "Unintelligible"

class SentenceHealth(BaseModel):
    sentence_id: int
    is_suspicious: bool = Field(..., description="True if text seems wrong/weird.")
    issue_category: Optional[IssueCategory] = Field(None)
    reason: Optional[str] = Field(None)
    suggested_correction: Optional[str] = Field(
        None, 
        description="The corrected text IF it is an ASR error. If it is just weird speech behavior (echolalia), leave this null."
    )

class HealthReport(BaseModel):
    assessments: List[SentenceHealth]

# --- 2. 初始化 Agent ---
client = OpenAI(
    base_url=config.llm_api_url, 
    api_key=config.openai_api_key, 
    timeout=120.0
)
agent = instructor.patch(client, mode=instructor.Mode.JSON)

def analyze_batch_safe(batch_sentences: List[dict]) -> Optional[HealthReport]:
    context = "\n".join([f"[ID {s.get('sentence_id', i)}] {s['text']}" for i, s in enumerate(batch_sentences)])
    
    system_prompt = """
        你是一位專業的中文逐字稿校對員 (Transcription Proofreader)。
        你的任務是檢查語音辨識 (ASR) 的結果，並標記出明顯的「同音錯字」或「語意不通」的錯誤。

        請嚴格遵守以下規則：
        1. **保留重複與結巴**：這份資料包含自閉症兒童的對話，因此「重複語句」(如：我要...我要...我要) 或「無意義的聲音」是重要的行為特徵，**絕對不要**視為錯誤，也不要修正。
        2. **僅修正明顯錯字**：只修正那些讀音相近但字錯誤的情況 (例如：「天氣很藍」-> 應為「天氣很難」 或 「我想去幹嘛」->「我想去玩」)。
        3. **繁體中文輸出**：所有修正後的建議必須使用「臺灣繁體中文」。

        輸出格式 (JSON)：
        {
            "is_suspicious": true/false,
            "suggested_correction": "修正後的句子" (若無錯誤則填 null),
            "reason": "簡短說明修正原因"
        }
    """

    max_retries = 3
    for attempt in range(max_retries):
        try:
            resp = agent.chat.completions.create(
                model="gemma-2-9b-it",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": context}
                ],
                response_model=HealthReport,
                temperature=0.1,
                max_retries=2 
            )
            return resp
            
        except (APITimeoutError, APIConnectionError) as e:
            print(f"      ⚠️ Timeout (Attempt {attempt+1}/{max_retries}). Retrying...", end="\r", flush=True)
            time.sleep(2)
        except Exception as e:
            print(f"      ⚠️ Flag Agent Error (Attempt {attempt+1}): {e}")
            time.sleep(1)
            
    return None

# --- 4. 核心入口 ---
def run_anomaly_detector(data: List[dict]) -> List[dict]:
    print(f"🛡️ Starting Anomaly/QA Detection (Total: {len(data)} sentences)...")
    
    for idx, item in enumerate(data):
        if 'sentence_id' not in item:
            item['sentence_id'] = idx
        item['needs_review'] = False
        item['review_reason'] = None
        item['suggested_correction'] = None

    batch_size = 5 
    total_batches = (len(data) + batch_size - 1) // batch_size

    for i in range(0, len(data), batch_size):
        batch = data[i : i + batch_size]
        current_batch = (i // batch_size) + 1
        print(f"   Processing Batch {current_batch}/{total_batches}...", end="", flush=True)
        
        report = analyze_batch_safe(batch)
        
        if report:
            print(f" Done.", flush=True)
            assessment_map = {a.sentence_id: a for a in report.assessments}
            
            for item in batch:
                sid = item['sentence_id']
                if sid in assessment_map:
                    assessment = assessment_map[sid]
                    if assessment.is_suspicious:
                        item['needs_review'] = True
                        item['review_reason'] = f"[{assessment.issue_category}] {assessment.reason}"
                        item['suggested_correction'] = assessment.suggested_correction
        else:
            print(f" Failed. Skipping flags.", flush=True)
            for item in batch:
                item['review_reason'] = "Analysis_Failed"

    print("\n✅ Anomaly Detector Finished.")
    return data
