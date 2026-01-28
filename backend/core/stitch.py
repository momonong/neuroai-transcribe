import json
import difflib
import time
from typing import List
from openai import OpenAI, APITimeoutError
import instructor
from pydantic import BaseModel, Field
import os

# 引入你的 config (為了讀取正確的 API URL)
from .config import config

# --- Agent 輸出結構 ---
class VerifiedSentence(BaseModel):
    text: str = Field(..., description="The cleaned, merged sentence.")
    source_ids: List[str] = Field(..., description="IDs of the raw segments used.")

class DatasetEntry(BaseModel):
    sentences: List[VerifiedSentence]

# --- 幻覺偵測 ---
def check_hallucination(original_text: str, rewritten_text: str) -> float:
    return difflib.SequenceMatcher(None, original_text, rewritten_text).ratio()

# --- 初始化 ---
# 1. 改動：加入 timeout 設定，並使用 config 中的 url
client = OpenAI(
    base_url=config.llm_api_url, 
    api_key=config.openai_api_key,
    timeout=180.0  # <--- 關鍵改動：設定 180 秒超時 (原本預設通常太短)
)
agent = instructor.patch(client, mode=instructor.Mode.JSON)

def process_batch_safe(batch_segments):
    input_text = "\n".join([f"[ID {s['id']}] {s['text']}" for s in batch_segments])

    system_prompt = """
    You are a Data Archivist creating a high-quality dataset for NeuroAI research.
    Your task is to merge fragmented speech segments into complete sentences.
    Rules: Verbatim Accuracy, Minimal Edits, Add Punctuation.
    """
    
    # 2. 改動：加入重試迴圈
    max_retries = 3
    for attempt in range(max_retries):
        try:
            resp = agent.chat.completions.create(
                model="gemma-2-9b-it", # 請確保這裡的模型名稱與你 Local LLM 載入的一致
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Raw Data:\n{input_text}"}
                ],
                response_model=DatasetEntry,
                temperature=0.0,
                max_retries=2 # 這是 instructor 內部的重試 (針對格式錯誤)
            )
            return resp
            
        except APITimeoutError:
            print(f"   ⚠️ Timeout (Attempt {attempt+1}/{max_retries}). Retrying...", end="\r", flush=True)
            time.sleep(2) # 休息一下再試
        except Exception as e:
            print(f"   ⚠️ Stitch Agent Error (Attempt {attempt+1}): {e}")
            time.sleep(1)
            
    return None # 三次都失敗才回傳 None

# --- 核心入口函式 ---
def run_stitching_logic(raw_data: List[dict]):
    final_results = []
    
    # 3. 改動：將視窗縮小，減少 LLM 負擔
    WINDOW_SIZE = 5 # <--- 從 10 改成 5，這會讓速度變慢一點，但穩定性大幅提升
    
    print(f"🛡️ Starting Stitching Pipeline (Total: {len(raw_data)} segments)...")
    
    total_batches = (len(raw_data) + WINDOW_SIZE - 1) // WINDOW_SIZE
    
    for i in range(0, len(raw_data), WINDOW_SIZE):
        batch = raw_data[i : i + WINDOW_SIZE]
        batch_map = {seg['id']: seg for seg in batch}
        
        current_batch_num = (i // WINDOW_SIZE) + 1
        print(f"   Processing Batch {current_batch_num}/{total_batches}...", end="", flush=True)

        result = process_batch_safe(batch)
        
        if result:
            print(f" Done. ({len(result.sentences)} sents)", flush=True)
            for sent in result.sentences:
                valid_ids = [bid for bid in sent.source_ids if bid in batch_map]
                if not valid_ids: continue
                
                original_text_combined = "".join([batch_map[bid]['text'] for bid in valid_ids])
                
                similarity = check_hallucination(original_text_combined, sent.text)
                len_ratio = len(sent.text) / (len(original_text_combined) + 1)
                is_risky = (similarity < 0.6) or (len_ratio > 1.5) or (len_ratio < 0.5)

                start_time = batch_map[valid_ids[0]]['start']
                end_time = batch_map[valid_ids[-1]]['end']
                speaker = batch_map[valid_ids[0]]['speaker']

                final_item = {
                    "start": start_time,
                    "end": end_time,
                    "speaker": speaker,
                    "text": sent.text,
                    "source_ids": valid_ids,
                    "verification_score": round(similarity, 2),
                    "status": "Verified",
                    "sentence_id": len(final_results)
                }

                if is_risky:
                    # print(f"\n   🚨 HALLUCINATION (Score: {similarity:.2f}): {sent.text}")
                    final_item['text'] = original_text_combined
                    final_item['status'] = "Rejected_Raw_Kept"

                final_results.append(final_item)
        else:
            # 失敗回退機制
            print(f" Failed. Using Raw Fallback.", flush=True)
            for item in batch:
                item['verification_score'] = 1.0
                item['status'] = "Raw_Fallback"
                item['sentence_id'] = len(final_results)
                final_item = {
                    "start": item['start'],
                    "end": item['end'],
                    "speaker": item['speaker'],
                    "text": item['text'],
                    "source_ids": [item['id']],
                    "verification_score": 1.0,
                    "status": "Raw_Fallback",
                    "sentence_id": len(final_results)
                }
                final_results.append(final_item)

    print("\n✅ Stitching complete.")
    return final_results