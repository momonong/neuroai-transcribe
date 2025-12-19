import json
import difflib
from typing import List
from openai import OpenAI
import instructor
from pydantic import BaseModel, Field

# --- 設定 ---
INPUT_FILE = "data/temp_chunks/chunk_4_2203484_2918912_aligned.json"
OUTPUT_FILE = "data/temp_chunks/chunk_4_2203484_2918912_verified_dataset.json"

# --- 1. 定義 Agent 輸出結構 ---
class VerifiedSentence(BaseModel):
    text: str = Field(..., description="The cleaned, merged sentence.")
    source_ids: List[int] = Field(..., description="IDs of the raw segments used.")

class DatasetEntry(BaseModel):
    sentences: List[VerifiedSentence]

# --- 2. 幻覺偵測演算法 (The Guardrail) ---
def check_hallucination(original_text: str, rewritten_text: str) -> float:
    """
    計算相似度分數 (0.0 ~ 1.0)
    1.0 = 完全一樣
    0.0 = 完全不同
    """
    # 簡單的 SequenceMatcher，不需額外安裝套件
    return difflib.SequenceMatcher(None, original_text, rewritten_text).ratio()

# --- 3. 初始化 ---
client = OpenAI(base_url="http://localhost:8000/v1", api_key="sk-local")
agent = instructor.patch(client, mode=instructor.Mode.JSON)

def process_batch_safe(batch_segments):
    # 準備 Raw Text
    input_text = "\n".join([f"[ID {s['id_in_batch']}] {s['text']}" for s in batch_segments])

    # 🔥 關鍵 Prompt：賦予它「資料集建立者」的人設
    system_prompt = """
You are a Data Archivist creating a high-quality dataset for NeuroAI research.
Your task is to merge fragmented speech segments into complete sentences.

**STRICT DATASET RULES:**
1. **Verbatim Accuracy**: Do NOT change the meaning. Do NOT add words that were not spoken.
2. **Minimal Edits**: Only fix broken words (e.g., "hos...pital" -> "hospital") and merge short gaps.
3. **Punctuation**: Add proper punctuation for readability.
4. **Conservation**: If a segment is complete, keep it as is.

Output a JSON list of sentences with their source IDs.
"""

    try:
        resp = agent.chat.completions.create(
            model="gemma-3-12b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Raw Data:\n{input_text}"}
            ],
            response_model=DatasetEntry,
            temperature=0.0, # 零溫，絕對理性
            response_format={"type": "json_object"}
        )
        return resp
    except Exception as e:
        print(f"⚠️ Agent Error: {e}")
        return None

def run_verified_pipeline():
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)

    final_results = []
    WINDOW_SIZE = 10 
    
    print("🛡️ Starting Verified Dataset Pipeline...")
    
    for i in range(0, len(raw_data), WINDOW_SIZE):
        batch = raw_data[i : i + WINDOW_SIZE]
        batch_map = {idx: seg for idx, seg in enumerate(batch)}
        for idx, s in enumerate(batch): s['id_in_batch'] = idx

        print(f"   Processing Batch {i//WINDOW_SIZE}...", end="\r")

        # 1. Agent 嘗試重寫
        result = process_batch_safe(batch)
        
        if result:
            for sent in result.sentences:
                # 找出原始文字
                valid_ids = [bid for bid in sent.source_ids if bid in batch_map]
                if not valid_ids: continue
                
                original_text_combined = "".join([batch_map[bid]['text'] for bid in valid_ids])
                
                # 2. 🛡️ 執行幻覺檢測 (The Guardrail Check)
                similarity = check_hallucination(original_text_combined, sent.text)
                
                # 設定閥值：如果相似度低於 0.6 (代表改動超過 40%)
                # 且長度差異過大 (例如原句 10 字，新句 20 字)
                len_ratio = len(sent.text) / (len(original_text_combined) + 1)
                
                is_risky = (similarity < 0.6) or (len_ratio > 1.5) or (len_ratio < 0.5)

                final_item = {
                    "start": batch_map[valid_ids[0]]['start'],
                    "end": batch_map[valid_ids[-1]]['end'],
                    "speaker": batch_map[valid_ids[0]]['speaker'],
                    "text": sent.text, # 預設用 AI 改的
                    "source_ids": [batch_map[bid]['id'] for bid in valid_ids],
                    "verification_score": round(similarity, 2),
                    "status": "Verified"
                }

                if is_risky:
                    # 駁回！使用原始拼湊文字
                    print(f"\n   🚨 HALLUCINATION DETECTED! (Score: {similarity:.2f})")
                    print(f"      Original: {original_text_combined}")
                    print(f"      Rejected: {sent.text}")
                    final_item['text'] = original_text_combined # Fallback to original
                    final_item['status'] = "Rejected_Raw_Kept"

                final_results.append(final_item)
        else:
            # Fallback for failed batch
            final_results.extend(batch)

    # Save
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_results, f, ensure_ascii=False, indent=2)
    print("\nDataset creation complete.")

if __name__ == "__main__":
    run_verified_pipeline()