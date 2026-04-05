import json
import torch
import os
import re
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline, BitsAndBytesConfig
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

# ==========================================
# 1. 設定與路徑
# ==========================================
TEXT_JSON = "data/text/full_whisper_transcript_with_timestamps.json"
SPEAKER_JSON = "data/text/stage1_whisperx_aligned.json"
OUTPUT_SCRIPT = "data/db/formatted_script.json" # 這是 Agent "寫入" 的結果
LOCAL_MODEL_PATH = "D:/hf_models/Llama-3.1-8B-Instruct"

TEST_MODE = False # True: 只跑前 3 個 Batch (快速測試)

# ==========================================
# 2. 定義「寫入工具」 (The Writer Tool)
# ==========================================
class ScriptWriter:
    def __init__(self, raw_source):
        self.raw_source = raw_source # 原始髒資料，用來查時間戳記
        self.clean_script = []       # 這是 Agent 要寫入的乾淨劇本
        self.write_count = 0

    def tool_write_line(self, original_id, role, text):
        """
        Agent 呼叫此工具來「寫入」一行乾淨的資料。
        Agent 不需要管時間戳記，Python 會自動從原始資料去抓對應的時間。
        """
        # 1. 驗證 ID 是否合法
        if original_id < 0 or original_id >= len(self.raw_source):
            print(f"⚠️ [Tool Error] Invalid ID: {original_id}")
            return

        # 2. 獲取原始物理資訊 (時間戳)
        raw_item = self.raw_source[original_id]
        
        # 3. 規範化角色名稱 (Schema Validation)
        clean_role = "Unknown"
        role_lower = role.lower()
        if "child" in role_lower: clean_role = "Child"
        elif "therapist" in role_lower or "adult" in role_lower: clean_role = "Therapist"
        
        # 4. 建構乾淨紀錄
        record = {
            "id": self.write_count,       # 新的流水號
            "source_id": original_id,     # 溯源 ID (方便除錯)
            "time_start": raw_item['start'],
            "time_end": raw_item['end'],
            "role": clean_role,           # Agent 判斷的
            "text": text.strip()          # Agent 修正的
        }
        
        # 5. 寫入資料庫
        self.clean_script.append(record)
        self.write_count += 1
        # print(f"  -> Wrote: [{clean_role}] {text}") # Debug 用

# ==========================================
# 3. 萬能合併邏輯 (物理層)
# ==========================================
def merge_transcripts(text_data, speaker_data):
    print("🔄 [System] Merging raw data streams...")
    if isinstance(text_data, list): segments = text_data
    elif isinstance(text_data, dict): segments = text_data.get('segments', [])
    else: segments = []

    merged = []
    for seg in segments:
        t_start, t_end = 0.0, 0.0
        if 'timestamp' in seg and isinstance(seg['timestamp'], list) and seg['timestamp']:
            t_start, t_end = seg['timestamp']
        elif 'start' in seg:
            t_start, t_end = seg['start'], seg['end']
        else: continue

        text = seg.get('text', '').strip()
        if not text: continue

        # 簡單語者匹配
        best_speaker = "Unknown"
        max_overlap = 0
        for spk_seg in speaker_data:
            s_start, s_end = spk_seg['start'], spk_seg['end']
            overlap = max(0, min(t_end, s_end) - max(t_start, s_start))
            if overlap > max_overlap:
                max_overlap = overlap
                best_speaker = spk_seg.get('speaker', 'Unknown')
        
        merged.append({"start": t_start, "end": t_end, "speaker": best_speaker, "text": text})
    
    print(f"✅ Merged {len(merged)} raw lines.")
    return merged

# ==========================================
# 4. 初始化模型
# ==========================================
print("🧠 [Writer Agent] Initializing Llama-3.1...")
bnb_config = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.float16)
tokenizer = AutoTokenizer.from_pretrained(LOCAL_MODEL_PATH)
if tokenizer.pad_token_id is None: tokenizer.pad_token_id = tokenizer.eos_token_id
model = AutoModelForCausalLM.from_pretrained(LOCAL_MODEL_PATH, quantization_config=bnb_config, device_map="auto", local_files_only=True)
pipe = pipeline("text-generation", model=model, tokenizer=tokenizer, max_new_tokens=512, temperature=0.1)

# ==========================================
# 5. Agent 執行迴圈 (已修正 List/String 錯誤)
# ==========================================
def run_writer_agent():
    # Load Data
    with open(TEXT_JSON, 'r', encoding='utf-8') as f: t_data = json.load(f)
    with open(SPEAKER_JSON, 'r', encoding='utf-8') as f: s_data = json.load(f)
    
    raw_merged = merge_transcripts(t_data, s_data)
    
    # 初始化寫入器
    writer = ScriptWriter(raw_merged)
    
    # 批次處理
    BATCH_SIZE = 5
    total_len = len(raw_merged)
    
    if TEST_MODE:
        run_range = range(0, min(15, total_len), BATCH_SIZE)
        print(f"🚀 [測試模式] Agent 開始工作 (只處理前 {min(15, total_len)} 句)...")
    else:
        run_range = range(0, total_len, BATCH_SIZE)
        print(f"🚀 [全量模式] Agent 開始工作 (共 {total_len} 句)...")

    for i in tqdm(run_range):
        # A. 準備 Context
        batch_end = min(i + BATCH_SIZE, total_len)
        context_str = ""
        current_batch_ids = []
        
        for idx in range(i, batch_end):
            item = raw_merged[idx]
            context_str += f"ID: {idx} | Raw Speaker: {item['speaker']} | Raw Text: \"{item['text']}\"\n"
            current_batch_ids.append(idx)
        
        # B. Prompt (Agent 思考) - 已加入繁體中文強制指令
        prompt = f"""
        你是一個來自台灣的臨床轉錄 Agent (Taiwan Clinical Transcriber)。
        你的任務是將原始的 ASR 資料轉換為乾淨的劇本。
        
        【任務】
        1. 判斷真實角色 (Therapist 或 Child)。
        2. 修正錯字 (Text Normalization)。
        
        【重要規則】
        - **必須使用台灣繁體中文 (Traditional Chinese)**。
        - 修正用語需符合台灣醫療情境 (例如：不要使用中國用語)。
        
        【工具指令】
        使用以下格式寫入每一行：
        WRITE | ID | Role | Clean Text
        
        - ID: 必須對應輸入的 ID
        - Role: 只允許 'Child' 或 'Therapist'
        - Clean Text: 修正後的**繁體中文**內容
        
        【輸入 Raw Data】
        {context_str}
        
        【你的指令輸出】
        """
        
        msgs = [{"role": "user", "content": prompt}]
        
        try:
            # C. 生成指令
            outputs = pipe(msgs)
            raw_res = outputs[0]['generated_text']
            
            # 🛑【修正點】判斷回傳類型
            if isinstance(raw_res, list):
                # 如果是 List，通常最後一筆才是 AI 的回覆
                res = raw_res[-1]['content']
            elif isinstance(raw_res, dict):
                res = raw_res.get('content', '')
            else:
                # 如果是字串，直接用
                res = str(raw_res)
            
            # D. 解析與執行
            lines = res.strip().split('\n')
            for line in lines:
                if "WRITE |" in line:
                    parts = line.split('|')
                    if len(parts) >= 4:
                        try:
                            p_id = int(parts[1].strip())
                            p_role = parts[2].strip()
                            p_text = parts[3].strip()
                            
                            if p_id in current_batch_ids:
                                writer.tool_write_line(p_id, p_role, p_text)
                        except ValueError:
                            pass # 忽略解析失敗的行
                            
        except Exception as e:
            print(f"❌ Batch Error at index {i}: {e}")
            # 印出這行來除錯，看看模型到底回傳了什麼結構
            # print(f"DEBUG info: {type(outputs[0]['generated_text'])}") 

    # ==========================================
    # 6. 存檔
    # ==========================================
    print("\n" + "="*30)
    print(f"📊 寫入完成！共產出 {writer.write_count} 行乾淨劇本。")
    
    os.makedirs(os.path.dirname(OUTPUT_SCRIPT), exist_ok=True)
    with open(OUTPUT_SCRIPT, 'w', encoding='utf-8') as f:
        json.dump(writer.clean_script, f, ensure_ascii=False, indent=4)
        
    print(f"💾 檔案已儲存: {OUTPUT_SCRIPT}")
    if TEST_MODE:
        print("💡 測試完成。請將程式碼中的 `TEST_MODE = False` 執行全量。")

if __name__ == "__main__":
    run_writer_agent()