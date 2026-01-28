import json
import time
from typing import List, Optional, Literal
from enum import Enum
from pydantic import BaseModel, Field
import instructor
from openai import OpenAI, APITimeoutError, APIConnectionError

# 引入配置，確保 API Key 和 URL 與 pipeline 一致
from .config import config

# --- 1. 定義資料結構 ---
class IssueCategory(str, Enum):
    LIKELY_ASR_ERROR = "Likely_ASR_Error"     # 聽起來像同音字錯誤
    CONTEXT_MISMATCH = "Context_Mismatch"     # 上下文不通順
    UNINTELLIGIBLE = "Unintelligible"         # 語意不明
    # ASD 特徵保留 (可選)
    # ECHOLALIA = "Echolalia" 

class SentenceHealth(BaseModel):
    sentence_id: int
    is_suspicious: bool = Field(..., description="True if text seems wrong/weird.")
    issue_category: Optional[IssueCategory] = Field(None)
    reason: Optional[str] = Field(None)
    
    # 👇👇👇 核心新增：建議修正欄位 👇👇👇
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
    timeout=120.0  # 設定 120 秒，避免 Local LLM 運算過久導致超時
)
agent = instructor.patch(client, mode=instructor.Mode.JSON)

def analyze_batch_safe(batch_sentences: List[dict]) -> Optional[HealthReport]:
    """
    呼叫 LLM 進行分析，帶有重試機制
    """
    # 準備 Prompt 上下文
    context = "\n".join([f"[ID {s.get('sentence_id', i)}] {s['text']}" for i, s in enumerate(batch_sentences)])
    
    # 👇👇👇 ASD 專用防呆 Prompt 👇👇👇
    system_prompt = """
    You are a Transcription QA Agent specializing in NeuroAI datasets. 
    Your job is to flag Automatic Speech Recognition (ASR) errors (e.g., homophones, typos).
    
    CRITICAL RULE:
    - This is an Autism Spectrum Disorder (ASD) dataset.
    - DO NOT flag or correct repetitive speech (echolalia), stuttering, or short phrases as errors. These are valid behavioral data.
    - ONLY flag obvious phonetic ASR mistakes (e.g., "The sky is glue" -> "The sky is blue").
    
    If you find an ASR error:
    1. Set is_suspicious = True
    2. Provide the 'suggested_correction' (what the speaker likely meant).
    
    If the sentence is just repetitive or characteristic of ASD:
    1. Set is_suspicious = False
    2. Leave suggested_correction as null.
    """

    # 3. 顯式重試迴圈
    max_retries = 3
    for attempt in range(max_retries):
        try:
            resp = agent.chat.completions.create(
                model="gemma-2-9b-it", # 確認你的模型名稱
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
    
    # 初始化欄位
    for idx, item in enumerate(data):
        if 'sentence_id' not in item:
            item['sentence_id'] = idx
        item['needs_review'] = False
        item['review_reason'] = None
        item['suggested_correction'] = None # 初始化建議欄位

    # 設定 Batch Size 為 5 (穩定性優先)
    batch_size = 5 
    total_batches = (len(data) + batch_size - 1) // batch_size

    for i in range(0, len(data), batch_size):
        batch = data[i : i + batch_size]
        
        current_batch = (i // batch_size) + 1
        print(f"   Processing Batch {current_batch}/{total_batches}...", end="", flush=True)
        
        report = analyze_batch_safe(batch)
        
        if report:
            print(f" Done.", flush=True)
            # 建立查表字典
            assessment_map = {a.sentence_id: a for a in report.assessments}
            
            for item in batch:
                sid = item['sentence_id']
                if sid in assessment_map:
                    assessment = assessment_map[sid]
                    
                    # 只有真的有問題時才標記
                    if assessment.is_suspicious:
                        item['needs_review'] = True
                        item['review_reason'] = f"[{assessment.issue_category}] {assessment.reason}"
                        # 儲存建議修正
                        item['suggested_correction'] = assessment.suggested_correction
                        
                        # (可選) Debug 顯示
                        # print(f"\n      🚩 Flagged: {item['text']} -> Suggest: {assessment.suggested_correction}")
        else:
            print(f" Failed. Skipping flags.", flush=True)
            for item in batch:
                item['review_reason'] = "Analysis_Failed"

    print("\n✅ Anomaly Detector Finished.")
    return data