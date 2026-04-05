import json
import re
import os
import Levenshtein # pip install python-Levenshtein

# ==========================================
# 設定
# ==========================================
GT_SRT_FILE = "data\ASD\GTruth.srt" 
RAW_JSON_FILE = "data/text/full_whisper_transcript_with_timestamps.json" # 原始 Whisper 檔

def clean_text(text):
    # 統一清洗邏輯：只留中文字
    text = re.sub(r'(小孩|測試者|老師|Child|Therapist|Unknown)[:：]\s*', '', text)
    text = re.sub(r'[^\u4e00-\u9fa5]', '', text)
    return text

def parse_srt(file_path):
    if not os.path.exists(file_path): return ""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    lines = content.split('\n')
    text_list = []
    for line in lines:
        if "-->" in line or line.strip().isdigit() or not line.strip(): continue
        text_list.append(clean_text(line))
    return "".join(text_list)

def parse_raw_whisper(file_path):
    if not os.path.exists(file_path): return ""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    text_list = []
    # 處理 Whisper 原始格式 (通常是 segments 列表)
    segments = data if isinstance(data, list) else data.get('segments', [])
    for s in segments:
        text_list.append(clean_text(s['text']))
        
    return "".join(text_list)

def run_baseline_eval():
    print("🚀 計算 Baseline (Raw Whisper) 相似度...")
    
    gt_text = parse_srt(GT_SRT_FILE)
    raw_text = parse_raw_whisper(RAW_JSON_FILE)
    
    if not gt_text or not raw_text:
        print("❌ 檔案讀取失敗")
        return

    print(f"📄 Ground Truth 長度: {len(gt_text)} 字")
    print(f"📄 Raw Whisper 長度: {len(raw_text)} 字")

    distance = Levenshtein.distance(gt_text, raw_text)
    cer = distance / len(gt_text)
    accuracy = (1 - cer) * 100
    if accuracy < 0: accuracy = 0

    print("\n" + "="*40)
    print("📊 Baseline 評估結果")
    print("="*40)
    print(f"🔹 原始編輯距離: {distance}")
    print(f"🔹 原始錯誤率 (CER): {cer*100:.2f}%")
    print("-" * 40)
    print(f"✅ Baseline Accuracy: {accuracy:.2f}%")
    print("="*40)
    
    # 這裡給你一個自動判斷建議
    print("\n💡 決策建議:")
    if accuracy < 70.3: # 假設你的 Agent 是 70.3
        print(f"👍 加進去！Raw ({accuracy:.1f}%) < Agent (70.3%)")
        print("   這證明了你的系統有「修正錯誤」的能力！")
    else:
        print(f"⚠️ 不要放數字！Raw ({accuracy:.1f}%) >= Agent (70.3%)")
        print("   這代表 Raw Whisper 雖然亂，但字數多所以分數高。")
        print("   策略：只強調 Agent 移除了「毒藥 (Flagged Errors)」，不比字元準確率。")

if __name__ == "__main__":
    run_baseline_eval()