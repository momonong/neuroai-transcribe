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
OUTPUT_FULL_REPORT = "data/report/final_full_analysis.json"
LOCAL_MODEL_PATH = "D:/hf_models/Llama-3.1-8B-Instruct"

# ==========================================
# 2. 萬能合併工具 (已修正格式問題)
# ==========================================
def merge_transcripts(text_data, speaker_data):
    print("🔄 正在合併 Whisper 文字與 Pyannote 語者資訊...")
    
    # 1. 處理輸入格式差異 (List vs Dict)
    if isinstance(text_data, list):
        segments = text_data
    elif isinstance(text_data, dict):
        segments = text_data.get('segments', []) or text_data.get('chunks', [])
    else:
        raise ValueError("無法識別文字檔的 JSON 結構")

    merged = []
    
    for seg in segments:
        # 2. 處理時間戳格式差異
        # 你的格式是: "timestamp": [1.0, 3.0]
        if 'timestamp' in seg and isinstance(seg['timestamp'], list):
            if seg['timestamp'] is None: continue # 跳過無效片段
            t_start = seg['timestamp'][0]
            t_end = seg['timestamp'][1]
        # 標準格式是: "start": 1.0, "end": 3.0
        elif 'start' in seg and 'end' in seg:
            t_start = seg['start']
            t_end = seg['end']
        else:
            continue # 無法取得時間，跳過

        text = seg.get('text', '').strip()
        if not text: continue

        # 3. 語者匹配邏輯 (不變)
        best_speaker = "Unknown"
        max_overlap = 0
        
        for spk_seg in speaker_data:
            s_start = spk_seg['start']
            s_end = spk_seg['end']
            
            # 計算重疊
            overlap_start = max(t_start, s_start)
            overlap_end = min(t_end, s_end)
            overlap = max(0, overlap_end - overlap_start)
            
            if overlap > max_overlap:
                max_overlap = overlap
                best_speaker = spk_seg.get('speaker', 'Unknown')
        
        merged.append({
            "start": t_start,
            "end": t_end,
            "speaker": best_speaker,
            "text": text
        })
    return merged

# ==========================================
# 3. 初始化 Llama-3 (4-bit)
# ==========================================
print("🧠 [Agent] 初始化 Llama-3.1 (4-bit Mode)...")

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.float16
)

try:
    tokenizer = AutoTokenizer.from_pretrained(LOCAL_MODEL_PATH)
    if tokenizer.pad_token_id is None: tokenizer.pad_token_id = tokenizer.eos_token_id
    
    model = AutoModelForCausalLM.from_pretrained(
        LOCAL_MODEL_PATH,
        quantization_config=bnb_config,
        device_map="auto",
        local_files_only=True
    )
    
    agent_pipe = pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
        max_new_tokens=2000, 
        temperature=0.1,
        return_full_text=False
    )
except Exception as e:
    print(f"❌ 模型載入失敗: {e}")
    exit()

# ==========================================
# 4. 執行流程
# ==========================================
if not os.path.exists(TEXT_JSON) or not os.path.exists(SPEAKER_JSON):
    print("❌ 找不到輸入檔案")
    exit()

with open(TEXT_JSON, 'r', encoding='utf-8') as f:
    text_data = json.load(f)

with open(SPEAKER_JSON, 'r', encoding='utf-8') as f:
    speaker_data = json.load(f)

# 合併
full_dialogue = merge_transcripts(text_data, speaker_data)
print(f"✅ 合併完成，共 {len(full_dialogue)} 句對話。")

# ==========================================
# 5. Layer 1: 角色鎖定
# ==========================================
print("\n🕵️ [Layer 1] 判斷角色 (Therapist vs Child)...")
preview_lines = []
# 取前 25 句，讓模型有足夠上下文判斷
for item in full_dialogue[:25]:
    preview_lines.append(f"{item['speaker']}: {item['text']}")
preview_text = "\n".join(preview_lines)

role_prompt = [
    {"role": "system", "content": "你是兒童職能治療專家。請根據對話判斷 SPEAKER_00 和 SPEAKER_01 誰是 'Therapist' (治療師)，誰是 'Child' (兒童)。"},
    {"role": "user", "content": f"對話片段：\n{preview_text}\n\n請直接輸出 JSON 格式，不要解釋。例如：{{\"SPEAKER_00\": \"Therapist\", \"SPEAKER_01\": \"Child\"}}"}
]

role_map = {"SPEAKER_00": "Unknown", "SPEAKER_01": "Unknown"}
try:
    role_result = agent_pipe(role_prompt)[0]['generated_text']
    print(f"🤖 角色判斷輸出: {role_result.strip()}")
    json_match = re.search(r"\{.*\}", role_result, re.DOTALL)
    if json_match:
        role_map = json.loads(json_match.group(0))
        print(f"✅ 鎖定角色: {role_map}")
except:
    print("⚠️ 角色判斷解析失敗，將使用 Unknown")

# ==========================================
# 6. Layer 2: 批次分析 (只跑前 2 個測試)
# ==========================================
print("\n📋 [Layer 2] 開始全量行為分析 (測試模式: 只跑前 2 批)...")

final_report = []
CHUNK_SIZE = 50 
# 切分 Chunks
all_chunks = [full_dialogue[i:i + CHUNK_SIZE] for i in range(0, len(full_dialogue), CHUNK_SIZE)]

# 🛑【修改點 1】只取前 2 個 chunk 來跑，節省時間
test_chunks = all_chunks[:2] 

print(f"📊 總共 {len(all_chunks)} 個批次，目前只執行前 {len(test_chunks)} 個進行測試...")

for idx, chunk in enumerate(tqdm(test_chunks)):
    chunk_text = ""
    for item in chunk:
        spk = item['speaker']
        role = role_map.get(spk, spk)
        t_str = f"{int(item['start']//60):02d}:{int(item['start']%60):02d}"
        chunk_text += f"[{t_str}] {role}: {item['text']}\n"
    
    prompt_content = f"""
    任務：分析以下自閉症治療對話。
    
    請輸出 JSON List，格式：[{{"time": "MM:SS", "role": "Child", "text": "...", "behavior": "..."}}]
    
    標記規則：
    1. **Echolalia (仿說)**：Child 重複 Therapist 的話。
    2. **Verbal_Refusal (拒絕)**：Child 說 "不要"、"不想"。
    3. **Correction (ASR修正)**：修正錯字。

    對話內容：
    {chunk_text}
    """
    
    msgs = [{"role": "user", "content": prompt_content}]
    
    try:
        res = agent_pipe(msgs)[0]['generated_text']
        
        # 🛑【修改點 2】增強解析邏輯
        # 嘗試尋找最外層的 [ ... ]
        list_match = re.search(r"\[.*\]", res, re.DOTALL)
        
        if list_match:
            try:
                # 這裡有時候模型會輸出 [JSON] 說明文字，導致解析失敗
                # 我們用較寬鬆的方式嘗試解析
                json_str = list_match.group(0)
                parsed = json.loads(json_str)
                final_report.extend(parsed)
            except json.JSONDecodeError:
                # 如果 JSON 格式壞掉，嘗試修復或僅保存原始文字
                print(f"⚠️ Batch {idx} JSON 格式有誤，已保存原始文字。")
                final_report.append({"batch_id": idx, "error": "Invalid JSON", "raw_output": res})
        else:
            final_report.append({"batch_id": idx, "error": "No JSON found", "raw_output": res})
            
    except Exception as e:
        print(f"⚠️ Batch {idx} 發生未預期錯誤: {e}")

# ==========================================
# 7. 存檔
# ==========================================
os.makedirs(os.path.dirname(OUTPUT_FULL_REPORT), exist_ok=True)
with open(OUTPUT_FULL_REPORT, 'w', encoding='utf-8') as f:
    json.dump(final_report, f, ensure_ascii=False, indent=4)

print(f"\n🎉 測試完成！請查看報告: {OUTPUT_FULL_REPORT}")
print("確認格式沒問題後，再把 [:2] 拿掉跑全量。")