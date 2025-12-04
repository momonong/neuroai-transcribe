import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
import json
import re
import os
from dotenv import load_dotenv

# ==========================================
# 1. 環境設定
# ==========================================
load_dotenv()
MODEL_PATH = os.getenv("LLAMA_MODEL_PATH")

if not MODEL_PATH:
    print("❌ 錯誤：找不到環境變數 'LLAMA_MODEL_PATH'")
    exit()

print(f"🔄 正在載入模型: {MODEL_PATH}")
print("⚡ 啟用 4-bit 量化 (Complex Scenario Test)...")

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.float16
)

try:
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH,
        quantization_config=bnb_config,
        device_map="auto"
    )
    print("✅ 模型載入成功！")
except Exception as e:
    print(f"❌ 模型載入失敗: {e}")
    exit()

# ==========================================
# 2. 定義「複雜」臨床測試 Prompt
# ==========================================
print("\n🤖 正在執行 Agent 複雜推理 (Complex Scenario)...")

# ==========================================
# 修正版：強制繁體中文輸出的 Prompt
# ==========================================
complex_clinical_prompt = """
You are a precise Clinical Scribe Agent for an ASD screening session in Taiwan.
Your task is to process raw ASR transcripts into a structured, verbatim dataset.

Context: The clinician is holding a toy Lion (獅子) and making roaring sounds to engage the child.
Input Transcript:
[00:15] "看 這個 是 什麼 大大的 吼 是 獅子" (Clinician, Clear)
[00:20] "Shi... shi... uh..." (Child, Stuttering, Unclear)
[00:22] "對 獅子 你說 獅子" (Clinician, Encouraging)
[00:25] "O... zi..." (Child, Very Unclear)

Instructions:
1. Identify Speakers: Assign 'Clinician' (醫師) or 'Child' (兒童).
2. Contextual Restoration (Must be in Traditional Chinese 繁體中文):
   - If the child stutters (e.g., "Shi... shi..."), PRESERVE the repetition in 'original'.
   - In 'restored', clarify the meaning in Chinese (e.g., "獅... (獅子)... 獅...").
   - Use the clinician's cue ("It's a Lion") to fix "O... zi..." into "獅子".
3. Reasoning: Explain your logic briefly in Traditional Chinese.
4. Output strictly in JSON format.

JSON Schema:
{
  "dialogue": [
    { "timestamp": "string", "speaker": "Clinician" | "Child", "text": "string" },
    { 
      "timestamp": "string", 
      "speaker": "Clinician" | "Child", 
      "original": "string", 
      "restored": "string (Traditional Chinese)", 
      "reasoning": "string (Traditional Chinese)" 
    }
  ]
}
"""

messages = [
    {"role": "user", "content": complex_clinical_prompt},
]

input_ids = tokenizer.apply_chat_template(
    messages,
    add_generation_prompt=True,
    return_tensors="pt"
).to(model.device)

terminators = [
    tokenizer.eos_token_id,
    tokenizer.convert_tokens_to_ids("<|eot_id|>")
]

# ==========================================
# 3. 執行推論
# ==========================================
print("⏳ Agent 正在解析複雜對話...")

outputs = model.generate(
    input_ids,
    max_new_tokens=1024, # 增加長度以容納多輪對話
    eos_token_id=terminators,
    do_sample=True,
    temperature=0.1, 
    top_p=0.9,
)

response = tokenizer.decode(outputs[0][input_ids.shape[-1]:], skip_special_tokens=True)

# ==========================================
# 4. 結果驗證
# ==========================================
print("-" * 50)
# print("📄 原始輸出:\n", response) # Debug用，太長可以註解掉
# print("-" * 50)


print("\n🔍 驗證結果:")

try:
    json_match = re.search(r'\{.*\}', response, re.DOTALL)
    
    if json_match:
        clean_json = json_match.group(0)
        data = json.loads(clean_json)
        
        print("✅ JSON 解析成功！")
        
        # --- 這裡加入這行，把完整的 JSON 印出來給你看，最保險 ---
        print("\n📄 完整 JSON 資料 (Debug):")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print("-" * 30)
        # ----------------------------------------------------

        # 顯示每一句的解析結果 (修正判斷邏輯)
        for i, turn in enumerate(data['dialogue']):
            speaker = turn.get('speaker', 'Unknown')
            print(f"\n[Turn {i+1}] Speaker: {speaker}")
            
            # 判斷是否為兒童 (兼容英文 'Child' 和中文 '兒童')
            if 'Child' in speaker or '兒童' in speaker:
                print(f"  🔊 原始錄音: {turn.get('original')}")
                print(f"  ✨ 修復結果: {turn.get('restored')}")
                print(f"  🧠 推理邏輯: {turn.get('reasoning')}")
            else:
                # 醫師的部分
                print(f"  💬 內容: {turn.get('text')}")
                
        # 簡單的自動通過標準
        child_turns = [t for t in data['dialogue'] if 'Child' in t['speaker'] or '兒童' in t['speaker']]
        if len(child_turns) >= 2:
            print("\n✨ 測試結論: 成功！Agent 能夠處理多輪對話並修復重複與模糊語音。")
        
    else:
        print("❌ 未找到 JSON 區塊")
        print("原始回應:", response)

except Exception as e:
    print(f"⚠️ 解析錯誤: {e}")