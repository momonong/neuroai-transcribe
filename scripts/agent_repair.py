import torch
import time
import re
import json
import os
from dotenv import load_dotenv
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

load_dotenv()

# ==========================================
# 1. 環境設定與模型載入 (使用 4-bit 量化)
# ==========================================

LLAMA_MODEL_PATH = r"D:/hf_models/Llama-3.1-8B-Instruct" 
WHISPER_JSON_FILE = r"data/text/full_whisper_transcript_with_timestamps.json"

print(f"🔄 正在載入 Agent Model: {LLAMA_MODEL_PATH} ...")
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.float16
)

try:
    tokenizer = AutoTokenizer.from_pretrained(LLAMA_MODEL_PATH)
    model = AutoModelForCausalLM.from_pretrained(
        LLAMA_MODEL_PATH,
        quantization_config=bnb_config,
        device_map="auto"
    )
    print("✅ Llama Agent 載入成功！")
except Exception as e:
    print(f"❌ 模型載入失敗，請檢查路徑或 VRAM: {e}")
    exit()

# ==========================================
# 2. 隔離挑戰片段 (Isolation of Challenge Segment)
# ==========================================

# 讀取 Whisper 產生的結構化 JSON
try:
    with open(WHISPER_JSON_FILE, "r", encoding="utf-8") as f:
        whisper_chunks = json.load(f)
except FileNotFoundError:
    print(f"❌ 錯誤：找不到 Whisper 輸出檔案 {WHISPER_JSON_FILE}。")
    exit()

# 根據時間範圍 (Ground Truth: 00:36 - 00:57) 提取對應的 Chunks
# 這裡我們手動選擇最接近的幾個 Chunks，模擬 Agent 提取上下文
TARGET_START_S = 30.0  # 30秒附近
TARGET_END_S = 48.0    # 48秒附近
 
# 提取上下文
context_chunks = [
    chunk for chunk in whisper_chunks 
    if chunk['timestamp'][0] >= TARGET_START_S and chunk['timestamp'][1] <= TARGET_END_S
]

# 將提取的 chunks 重新組合成帶有時間標記的文本，供 Agent 推理
context_text = "\n".join([
    f"[{chunk['timestamp'][0]:.2f}s - {chunk['timestamp'][1]:.2f}s] {chunk['text']}" 
    for chunk in context_chunks
])

print("\n--- 隔離後的 ASR 片段 (帶時間標記) ---")
print(context_text)
print("-" * 50)


# ==========================================
# 3. 定義 Agent 邏輯 (修復真實錯誤)
# ==========================================
print("🤖 正在執行 Agent 修復邏輯...")

# ... (在腳本的第 3 區塊) ...

clinical_prompt = f"""
You are a Clinical Scribe Agent. Your task is to perform Speaker Diarization and Contextual Restoration on the provided ASR transcript segments.

Context: The dialogue is about a child's clothing and temperature. The Clinician (C) speaks clearly, while the Child (CH) may have ambiguous speech. Use the timestamps to infer dialogue turns.
CRITICAL INSTRUCTION:
1. Infer Speaker Roles: Assign '醫師' or '兒童' based on content (e.g., '老師' and complex questions imply 醫師).
2. Contextual Restoration: Specifically check the phrase '我裡面是毛了' or similar variants. Use the context of '外套' and '熱' to infer the correct term is likely '毛衣' or '毛'.
3. Output strictly in JSON format.

JSON Schema:
{{
  "dialogue": [
    {{ "start_time": "float", "end_time": "float", "speaker": "醫師" | "兒童", "original_text": "string", "restored_text": "string", "reasoning": "string" }}
  ]
}}
Input Transcript Segments:
{context_text}
"""

messages = [{"role": "user", "content": clinical_prompt}]

# ... (Run Inference and Decode - using the robust logic from previous steps) ...

input_ids = tokenizer.apply_chat_template(
    messages, add_generation_prompt=True, return_tensors="pt"
).to(model.device)
terminators = [tokenizer.eos_token_id, tokenizer.convert_tokens_to_ids("<|eot_id|>")]

outputs = model.generate(
    input_ids,
    max_new_tokens=1024,
    eos_token_id=terminators,
    temperature=0.1, 
)
response = tokenizer.decode(outputs[0][input_ids.shape[-1]:], skip_special_tokens=True)

# ==========================================
# 4. 輸出結果與最終驗證
# ==========================================
print("\n--- Agent 修復結果 ---")

# Regex 清洗 JSON
json_match = re.search(r'\{.*\}', response, re.DOTALL)
final_data = {}
error_flag = False

if json_match:
    try:
        clean_json = json_match.group(0)
        final_data = json.loads(clean_json)
        print("✅ JSON 解析成功！")
    except Exception as e:
        print(f"❌ JSON 解析失敗: {e}")
        error_flag = True
else:
    print("❌ 未在回應中找到 JSON 區塊。")
    error_flag = True

if not error_flag:
    # 查找並輸出關鍵修復點 (Child turn with "貓的")
    critical_fix_found = False
    
    # 打印完整 JSON
    print("\n📄 完整修復結果 (Final JSON):")
    print(json.dumps(final_data, indent=2, ensure_ascii=False))

    for turn in final_data.get('dialogue', []):
        if turn.get('speaker') == '兒童' and 'original' in turn and '貓的' in turn['original']:
            print("\n✨ 關鍵修復點 (Child - Clothing turn):")
            print(f"  🔊 原始錯誤 (Whisper): {turn['original']}")
            print(f"  ✨ Agent 修復結果: {turn['restored']}")
            print(f"  🧠 推理邏輯: {turn['reasoning']}")
            critical_fix_found = True
            
    if critical_fix_found:
        print("\n🎉 測試結論: 成功！Agent 成功修復了真實 ASR 產生的語義錯誤 (e.g., '貓的' -> '毛/毛衣')。")
    else:
        print("\n⚠️ 測試結論: Agent 運作正常，但未能找到或修復預期的關鍵錯誤。")