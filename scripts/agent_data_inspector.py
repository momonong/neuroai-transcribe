import json
import torch
import os
import re
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline, BitsAndBytesConfig
from torch.utils.data import Dataset
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# 1. 設定
# ==========================================
INPUT_SCRIPT = "data/db/formatted_script.json"
OUTPUT_WEB_READY = "data/db/final_web_ready_script.json"
LOCAL_MODEL_PATH = os.getenv("LLAMA_MODEL_PATH", "D:/hf_models/Llama-3.1-8B-Instruct")

# ⚡ Batch Size: 32 (5090 顯卡建議值)
BATCH_SIZE = 32

# 🧪 測試筆數：設為 0 或 None 代表跑全量
# 如果只想跑前 100 句測試，就設 100
TEST_SIZE = 0 

# ==========================================
# 2. 定義 Agent 的環境與工具
# ==========================================
class ClinicalInspector:
    def __init__(self, script_data):
        self.script = script_data
        for item in self.script:
            if 'flags' not in item: item['flags'] = []
            if 'review_status' not in item: item['review_status'] = 'pending'
        self.action_log = []

    def tool_add_flag(self, idx, flag_type, severity, note):
        target_item = next((item for item in self.script if item['id'] == idx), None)
        if target_item:
            # 避免重複標記同一種類型
            for f in target_item['flags']:
                if f['type'] == flag_type: return

            flag_entry = {
                "type": flag_type,
                "severity": severity,
                "note": note,
                "created_by": "Layer2_Agent"
            }
            target_item['flags'].append(flag_entry)
            
            # 只要有 High Severity 就亮紅燈
            if severity == "High":
                target_item['review_status'] = "needs_review"
            
            self.action_log.append(f"Action: Flagged ID {idx} as {flag_type}")

# ==========================================
# 3. 定義資料集 (包含重複偵測)
# ==========================================
# ==========================================
# 3. 定義資料集 (修正版：針對「奇怪名詞組合」)
# ==========================================
class InspectorDataset(Dataset):
    def __init__(self, script_data, tokenizer):
        self.prompts = []
        self.ids = [] 
        
        print("⚡ [System] 組裝 Prompts (Naturalness Check)...")
        
        for i in range(len(script_data)):
            curr = script_data[i]
            prev = script_data[i-1] if i > 0 else {"role": "None", "text": ""}
            
            context_str = f"""
            [上一句] {prev['role']}: "{prev['text']}"
            [當前句] {curr['role']}: "{curr['text']}"
            """
            
            # 🔥 Prompt 重點修正：教它分辨「不自然」
            prompt = f"""
            你是一個 ASR (語音轉文字) 品質檢查員。請檢查 [當前句] 是否為 **無效的轉錄結果**。
            
            【你的核心任務】
            判斷這句話是「人類口語 (包含小孩)」還是「機器產生的亂碼」。
            
            【判斷標準】
            1. **PASS (人類口語)**：
               - **簡單短句**：如 "好"、"對"、"車車"、"冰淇淋" (即使很短，只要是常見口語詞彙，PASS)。
               - **邏輯跳躍**：小孩突然說 "我要吃糖"，即使跟上一句無關，只要句子本身通順，PASS。
               - **語法破碎**：如 "那個...我要...那個" (PASS)。
            
            2. **FLAG (機器錯誤)**：
               - **單詞沙拉 (Word Salad)**：幾個不相關的中文字硬湊在一起，完全不通順。
                 (例如："雞腿針先伸唇"、"天氣書本飛機") -> **FLAG**
               - **無限迴圈**：重複字元超過 3 次以上。
                 (例如："啊啊啊啊啊啊"、"潑水潑水潑水潑水") -> **FLAG**
               - **非人類語言**：亂碼符號 (如 "???", "xkq") -> **FLAG**
            
            【工具指令】
            PASS
            FLAG | SEMANTIC_ERROR | High | <具體說明為什麼這不像人話>
            
            【輸入資料】
            {context_str}
            
            【你的指令】
            """
            
            msgs = [{"role": "user", "content": prompt}]
            full_prompt_str = tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
            self.prompts.append(full_prompt_str)
            self.ids.append(curr['id'])

    def __len__(self):
        return len(self.prompts)

    def __getitem__(self, idx):
        return self.prompts[idx]

# ==========================================
# 4. 初始化模型
# ==========================================
print("🧠 [Layer 2 Agent] Initializing...")
bnb_config = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.float16)

tokenizer = AutoTokenizer.from_pretrained(LOCAL_MODEL_PATH)
tokenizer.padding_side = 'left' 
if tokenizer.pad_token_id is None: tokenizer.pad_token_id = tokenizer.eos_token_id

model = AutoModelForCausalLM.from_pretrained(LOCAL_MODEL_PATH, quantization_config=bnb_config, device_map="auto", local_files_only=True)

pipe = pipeline("text-generation", model=model, tokenizer=tokenizer, max_new_tokens=128, temperature=0.1, batch_size=BATCH_SIZE, return_full_text=False)

# ==========================================
# 5. 主流程
# ==========================================
def run_batch_agent():
    if not os.path.exists(INPUT_SCRIPT):
        print(f"❌ 找不到輸入檔: {INPUT_SCRIPT}")
        return
    
    with open(INPUT_SCRIPT, 'r', encoding='utf-8') as f:
        full_data = json.load(f)
        
    # 🧪 處理測試模式
    if TEST_SIZE > 0:
        script_data = full_data[:TEST_SIZE]
        print(f"⚠️ TEST MODE: 僅處理前 {len(script_data)} 筆資料。")
    else:
        script_data = full_data
        print(f"🚀 FULL MODE: 處理全量 {len(script_data)} 筆資料。")

    inspector = ClinicalInspector(script_data)
    dataset = InspectorDataset(script_data, tokenizer)
    
    print(f"🚀 Layer 2 Agent 啟動 (Batch Size={BATCH_SIZE})...")
    
    results_iterator = pipe(dataset, batch_size=BATCH_SIZE)
    
    # 3. 解析結果
    for i, outputs in enumerate(tqdm(results_iterator, total=len(dataset))):
        current_id = dataset.ids[i]
        
        raw_res = outputs[0]['generated_text'] if isinstance(outputs, list) else outputs['generated_text']
        res = str(raw_res)
        
        # 解析指令
        lines = res.strip().split('\n')
        for line in lines:
            if "指令:" in line or "FLAG |" in line:
                clean_line = line.replace("指令:", "").strip()
                
                if "FLAG |" in clean_line:
                    parts = clean_line.split('|')
                    if len(parts) >= 4:
                        f_type = parts[1].strip()
                        f_sev = parts[2].strip()
                        f_note = parts[3].strip()
                        
                        # Python 額外防呆：醫生說話我們不標記 (除非你需要檢查醫生的重複話)
                        # item_role = next((x['role'] for x in script_data if x['id'] == current_id), "Unknown")
                        # if item_role == "Therapist": continue 

                        inspector.tool_add_flag(current_id, f_type, f_sev, f_note)

    # ==========================================
    # 6. 輸出與存檔 (修正處)
    # ==========================================
    print("\n" + "="*30)
    print(f"📊 檢查完成！")
    
    stats = {}
    for item in script_data:
        for f in item['flags']:
            stats[f['type']] = stats.get(f['type'], 0) + 1
    print(f"📈 標記統計: {stats}")
    
    # 💾 儲存檔案
    os.makedirs(os.path.dirname(OUTPUT_WEB_READY), exist_ok=True)
    with open(OUTPUT_WEB_READY, 'w', encoding='utf-8') as f:
        json.dump(script_data, f, ensure_ascii=False, indent=4)
        
    print(f"💾 資料已成功儲存至: {OUTPUT_WEB_READY}")
    
    # 印出範例
    print("\n🔍 被標記的句子範例:")
    count = 0
    for item in script_data:
        if item['flags']:
            print(f"ID {item['id']} [{item['role']}]: {item['text']}")
            for f in item['flags']:
                print(f"   -> {f['type']} | {f['note']}")
            print("-" * 20)
            count += 1
            if count >= 10: break # 只印前10個避免洗版

if __name__ == "__main__":
    run_batch_agent()