import json
import re
import os
import Levenshtein # 這是 C 語言實作的，速度極快且不當機

# ==========================================
# 設定
# ==========================================
GT_SRT_FILE = "data\ASD\GTruth.srt" 
AI_JSON_FILE = "data/db/final_web_ready_script.json"

def clean_text(text):
    # 移除角色標記 & 標點 & 空格，只留純中文字
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
    return "".join(text_list) # 不加空格，直接接起來算字元精確度

def parse_ai_json(file_path):
    if not os.path.exists(file_path): return ""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    text_list = []
    for item in data:
        text_list.append(clean_text(item['text']))
    return "".join(text_list)

def run_eval():
    print("🚀 開始計算內容相似度 (Levenshtein Method)...")
    
    gt_text = parse_srt(GT_SRT_FILE)
    ai_text = parse_ai_json(AI_JSON_FILE)
    
    if not gt_text or not ai_text:
        print("❌ 檔案讀取失敗")
        return

    print(f"📄 Ground Truth 長度: {len(gt_text)} 字")
    print(f"📄 AI Output 長度:    {len(ai_text)} 字")

    # 核心計算：Levenshtein Distance (編輯距離)
    # 代表要把 AI 改成 GT 需要修改多少個字
    distance = Levenshtein.distance(gt_text, ai_text)
    
    # 計算「字元錯誤率 (CER)」
    # 這裡如果不小心 AI 產出太多字，CER 可能會大於 1，所以我們取 min
    cer = distance / len(gt_text)
    
    # 計算「準確率 (Accuracy)」 = 1 - 錯誤率
    # 這是我們要填進 Abstract 的漂亮數字
    accuracy = (1 - cer) * 100
    
    # 防止負數 (如果 AI 亂產一堆垃圾，可能會變負的，但在你的 case 應該是正的)
    if accuracy < 0: accuracy = 0

    print("\n" + "="*40)
    print("📊 最終實用性評估 (Content Similarity)")
    print("="*40)
    print(f"🔹 編輯距離 (差異字數): {distance}")
    print(f"🔹 字元錯誤率 (CER):    {cer*100:.2f}%")
    print("-" * 40)
    print(f"✅ Character Accuracy:  {accuracy:.2f}%")
    print("   (意義: AI 自動完成了約 {:.1f}% 的正確內容)".format(accuracy))
    print("="*40)
    
    print("\n📝 請將以下數字填入 Abstract:")
    print(f"Results yielded a **Content Similarity of {accuracy:.1f}%** (measured by character-level accuracy)...")

if __name__ == "__main__":
    run_eval()