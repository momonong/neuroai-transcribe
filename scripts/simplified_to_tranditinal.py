import json
import os
from opencc import OpenCC

# 👇👇👇 請在這裡貼上你要修正的檔案路徑 👇👇👇
target_file_path = r"data\test\intermediate\chunk_4_2015431_2714709_flagged_for_human.json"

def convert_to_traditional(file_path):
    # 1. 檢查檔案是否存在
    if not os.path.exists(file_path):
        print(f"❌ 找不到檔案: {file_path}")
        return

    print(f"📂 正在讀取: {file_path}...")
    
    # 2. 初始化 OpenCC (簡體 -> 台灣繁體)
    cc = OpenCC('s2twp')

    try:
        # 讀取 JSON
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 判斷結構 (List 或是 Dict)
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            # 嘗試找可能的列表 key
            for key in ["segments", "data", "results"]:
                if key in data and isinstance(data[key], list):
                    items = data[key]
                    break
        
        if not items:
            print("⚠️ 無法識別的 JSON 結構，未進行轉換。")
            return

        # 3. 開始轉換
        count = 0
        for item in items:
            # A. 轉換主要文字 'text'
            if "text" in item and isinstance(item["text"], str):
                converted = cc.convert(item["text"])
                if converted != item["text"]:
                    item["text"] = converted
                    count += 1
            
            # B. 轉換 LLM 的建議 'suggested_correction'
            if "suggested_correction" in item and isinstance(item["suggested_correction"], str):
                item["suggested_correction"] = cc.convert(item["suggested_correction"])

            # C. 轉換 LLM 的理由 'reason'
            if "reason" in item and isinstance(item["reason"], str):
                item["reason"] = cc.convert(item["reason"])

        # 4. 寫回檔案
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"✅ 轉換成功！已將 {count} 個段落轉為繁體中文。")
        print(f"💾 檔案已覆蓋: {file_path}")

    except Exception as e:
        print(f"❌ 發生錯誤: {e}")

if __name__ == "__main__":
    convert_to_traditional(target_file_path)