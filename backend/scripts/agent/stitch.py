import json
import os
import time
from typing import List
from pydantic import BaseModel, Field
import instructor
from llama_cpp import Llama
from dotenv import load_dotenv

load_dotenv()

# --- 設定路徑 ---
# 請確認這也是你下載模型的實際路徑
MODEL_PATH = r"D:/hf_models/Meta-Llama-3.1-8B-Instruct-GGUF/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
INPUT_FILE = "data/temp_chunks/chunk_3_1100278_1606067_aligned.json"
OUTPUT_FILE = "data/temp_chunks/chunk_3_1100278_1606067_stitched_pro.json"

# --- 1. 定義資料結構 (The Schema) ---
# 這就是讓 Google 面試官點頭的關鍵：強型別定義
# 我們告訴模型：你只能填這個表，不能亂說話

class MergeGroup(BaseModel):
    ids: List[int] = Field(
        ..., 
        description="A list of segment IDs (integers) that form ONE complete sentence."
    )

class MergePlan(BaseModel):
    groups: List[MergeGroup] = Field(
        ..., 
        description="A list of merge groups. Covers all segments in the batch."
    )

# --- 2. 初始化 AI 引擎 (GGUF + Instructor) ---
print(f"🤖 Initializing Llama 3.1 (GGUF) from: {MODEL_PATH}")

try:
    # n_gpu_layers=-1 代表把所有層都丟進 GPU (5090 跑 Q4 模型綽綽有餘)
    # n_ctx=8192 是上下文視窗大小
    llm = Llama(
        model_path=MODEL_PATH,
        n_gpu_layers=-1, 
        n_ctx=8192,
        verbose=False # 關閉底層囉嗦的 log
    )
    
    # Patching: 賦予 Llama 結構化輸出的能力
    # Patching: 賦予 Llama 結構化輸出的能力
    # 修改：使用 Mode.MD_JSON，這對 Llama 3 比較友善，容許它輸出 Markdown
    agent = instructor.patch(
        create=llm.create_chat_completion_openai_v1,
        mode=instructor.Mode.MD_JSON 
    )
    print("✅ Engine loaded successfully. GPU Acceleration enabled.")

except Exception as e:
    print(f"❌ Engine load failed: {e}")
    print("請確認模型路徑是否正確，或檢查 llama-cpp-python 安裝。")
    exit()

# --- 3. 核心邏輯：Agent 決策 ---
def get_merge_plan(batch_segments) -> MergePlan:
    """
    V4.1: 更保守的縫合策略，避免句子變得太長
    """
    context_str = ""
    prev_end = 0.0
    
    for i, seg in enumerate(batch_segments):
        # 計算與上一句的時間差 (Gap)
        gap = seg['start'] - prev_end if i > 0 else 0.0
        prev_end = seg['end']
        
        # 把 Gap 直接算給 AI 看，讓它不用自己做減法，判斷更精準
        # 格式: ID 0: [Gap: 0.5s] [SPEAKER_00] 文字
        gap_str = f"{gap:.2f}s" if i > 0 else "N/A"
        context_str += f"ID {seg['id_in_batch']}: [Gap: {gap_str}] [{seg['speaker']}] {seg['text']}\n"

    system_prompt = """
You are a conservative transcript editor. 
Your goal is to fix fragmented words, NOT to create long paragraphs.

**STRICT MERGING RULES:**
1. **Time Limit**: ONLY merge if the Gap is **LESS THAN 0.8 seconds**.
   - If Gap > 0.8s, DO NOT MERGE.
2. **Short & Sweet**: Avoid creating sentences longer than 30 characters.
3. **Punctuation Logic**: If the first segment sounds complete (e.g., ends with "喔", "啊", "呢"), DO NOT MERGE.
4. **Speaker**: NEVER merge different speakers.

**When in doubt, DO NOT MERGE. Keep segments separate.**

Output the JSON structure as shown in the example.
STRICTLY NO COMMENTS inside the JSON.
"""
    
    try:
        resp = agent(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Decide merge groups for:\n\n{context_str}"}
            ],
            response_model=MergePlan, 
            temperature=0.1, # 低溫保持冷靜
            max_tokens=1024,
        )
        return resp
    except Exception as e:
        print(f"\n   ⚠️ Agent Inference Error: {e}")
        return None
# --- 4. 執行與縫合 (The Executioner) ---
def execute_stitching(raw_batch, plan: MergePlan):
    """
    根據 AI 的計畫，執行真正的字串合併
    """
    stitched_batch = []
    processed_ids = set()
    
    # 建立 ID 到 內容 的查找表 (因為 raw_batch 是一個 list)
    # 我們這裡暫時假設 raw_batch 的 index 就是 ID，但在 batch 處理中要小心
    # 為了安全，我們重新映射
    seg_map = {seg['id_in_batch']: seg for seg in raw_batch}

    for group in plan.groups:
        # 過濾無效 ID
        valid_ids = [i for i in group.ids if i in seg_map]
        if not valid_ids: continue
        
        # 標記已處理
        for i in valid_ids: processed_ids.add(i)
        
        # 抓取第一句和最後一句的時間
        first_seg = seg_map[valid_ids[0]]
        last_seg = seg_map[valid_ids[-1]]
        
        # 合併文字
        combined_text = "".join([seg_map[i]["text"] for i in valid_ids])
        
        # 建立新物件
        new_seg = {
            "start": first_seg["start"],
            "end": last_seg["end"],
            "speaker": first_seg["speaker"],
            "text": combined_text,
            "source_ids": [seg_map[i]["id"] for i in valid_ids] # 保留原始的全域 ID
        }
        stitched_batch.append(new_seg)
    
    # 處理漏網之魚 (Orphans)
    # 如果 AI 漏掉了某些 ID，我們必須把它們加回來，不能掉資料
    for i in range(len(raw_batch)):
        if i not in processed_ids:
            seg = raw_batch[i]
            stitched_batch.append({
                "start": seg["start"],
                "end": seg["end"],
                "speaker": seg["speaker"],
                "text": seg["text"],
                "source_ids": [seg["id"]]
            })
            
    # 依照開始時間重新排序
    stitched_batch.sort(key=lambda x: x["start"])
    return stitched_batch

# --- 主程式 ---
def run_pipeline():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ Input file not found: {INPUT_FILE}")
        return

    print(f"📖 Reading fragments from: {INPUT_FILE}")
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)

    total_segments = len(raw_data)
    final_results = []
    
    # 設定 Batch Size
    WINDOW_SIZE = 10 
    
    print(f"🚀 Starting Pro Stitcher on {total_segments} segments...")
    start_time = time.time()

    for i in range(0, total_segments, WINDOW_SIZE):
        # 準備 Batch
        batch = raw_data[i : i + WINDOW_SIZE]
        
        # 為每個 Batch 加上暫時的 ID (0~9)，方便 AI 識別
        for idx, seg in enumerate(batch):
            seg['id_in_batch'] = idx
            
        print(f"   Processing Batch {i//WINDOW_SIZE + 1}...", end="\r")
        
        # 1. 取得計畫
        plan = get_merge_plan(batch)
        
        # 2. 執行合併
        if plan:
            merged = execute_stitching(batch, plan)
            final_results.extend(merged)
        else:
            # Fallback: 如果 AI 真的壞了，保留原樣
            # (注意：要移除我們剛剛加的 id_in_batch 欄位)
            clean_batch = []
            for seg in batch:
                s = seg.copy()
                s.pop('id_in_batch', None)
                clean_batch.append(s)
            final_results.extend(clean_batch)

    # 存檔
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_results, f, ensure_ascii=False, indent=2)

    end_time = time.time()
    reduction = (1 - len(final_results)/total_segments) * 100
    
    print(f"\n\n✨ Mission Complete!")
    print(f"⏱️ Time Taken: {end_time - start_time:.2f}s")
    print(f"📉 Reduction: {total_segments} -> {len(final_results)} segments ({reduction:.1f}%)")
    print(f"💾 Saved to: {OUTPUT_FILE}")

if __name__ == "__main__":
    run_pipeline()