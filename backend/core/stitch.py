import json
import difflib
from typing import List
from openai import OpenAI
import instructor
from pydantic import BaseModel, Field
import os

# --- Agent 輸出結構 ---
class VerifiedSentence(BaseModel):
    text: str = Field(..., description="The cleaned, merged sentence.")
    source_ids: List[str] = Field(..., description="IDs of the raw segments used.") # ID 改成 str 以相容 chunk id

class DatasetEntry(BaseModel):
    sentences: List[VerifiedSentence]

# --- 幻覺偵測 ---
def check_hallucination(original_text: str, rewritten_text: str) -> float:
    return difflib.SequenceMatcher(None, original_text, rewritten_text).ratio()

# --- 初始化 ---
# 注意：這裡假設你有跑 Local LLM (如 Ollama/LM Studio) 在 port 8000
client = OpenAI(base_url="http://host.docker.internal:8000/v1", api_key="sk-local")
agent = instructor.patch(client, mode=instructor.Mode.JSON)

def process_batch_safe(batch_segments):
    input_text = "\n".join([f"[ID {s['id']}] {s['text']}" for s in batch_segments]) # 使用 'id'

    system_prompt = """
    You are a Data Archivist creating a high-quality dataset for NeuroAI research.
    Your task is to merge fragmented speech segments into complete sentences.
    Rules: Verbatim Accuracy, Minimal Edits, Add Punctuation.
    """

    try:
        resp = agent.chat.completions.create(
            model="gemma-2-9b-it", # 或你慣用的模型
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Raw Data:\n{input_text}"}
            ],
            response_model=DatasetEntry,
            temperature=0.0
        )
        return resp
    except Exception as e:
        print(f"⚠️ Stitch Agent Error: {e}")
        return None

# --- 核心入口函式 ---
def run_stitching_logic(raw_data: List[dict]):
    final_results = []
    WINDOW_SIZE = 10 
    
    print("🛡️ Starting Stitching Pipeline...")
    
    for i in range(0, len(raw_data), WINDOW_SIZE):
        batch = raw_data[i : i + WINDOW_SIZE]
        # 建立 ID 對照表
        batch_map = {seg['id']: seg for seg in batch}

        print(f"   Processing Batch {i//WINDOW_SIZE + 1}...", end="\r")

        result = process_batch_safe(batch)
        
        if result:
            for sent in result.sentences:
                valid_ids = [bid for bid in sent.source_ids if bid in batch_map]
                if not valid_ids: continue
                
                original_text_combined = "".join([batch_map[bid]['text'] for bid in valid_ids])
                
                similarity = check_hallucination(original_text_combined, sent.text)
                len_ratio = len(sent.text) / (len(original_text_combined) + 1)
                is_risky = (similarity < 0.6) or (len_ratio > 1.5) or (len_ratio < 0.5)

                # 抓出這一段的時間範圍
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
                    "sentence_id": len(final_results) # 重新編號
                }

                if is_risky:
                    print(f"\n   🚨 HALLUCINATION (Score: {similarity:.2f}): {sent.text}")
                    final_item['text'] = original_text_combined
                    final_item['status'] = "Rejected_Raw_Kept"

                final_results.append(final_item)
        else:
            # 失敗回退
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