import os
import argparse
import json
import re
import pandas as pd
import librosa
import torch
import whisper
import numpy as np
from transformers import AutoProcessor, AutoModelForImageTextToText
from pathlib import Path

# --- 設定區 ---
# 更新為你指定的 Gemma-4 最新模型
LLM_MODEL_ID = "google/gemma-4-E4B-it"
WHISPER_MODEL_ID = "tiny"
PROBE_WINDOW_SEC = 25.0  # 擷取切點前後各 25 秒作為探針


def load_models():
    print(f"正在載入 Whisper [{WHISPER_MODEL_ID}] (用於語意探針)...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    asr_model = whisper.load_model(WHISPER_MODEL_ID, device=device)

    print(f"正在載入 LLM 大腦 [{LLM_MODEL_ID}] (Gemma-4 多模態版本)...")
    # 依照你的需求，替換為 AutoProcessor 與 AutoModelForImageTextToText
    processor = AutoProcessor.from_pretrained(LLM_MODEL_ID)

    # 依然使用 bfloat16 來最大化 4090 的 VRAM 效益
    llm_model = AutoModelForImageTextToText.from_pretrained(
        LLM_MODEL_ID, device_map="auto", torch_dtype=torch.bfloat16
    )
    return asr_model, processor, llm_model, device


def extract_probe_transcript(asr_model, y, sr, cut_time_sec):
    """擷取切點前後的音訊，並用 Whisper 快速轉成文字草稿 (具備抗幻覺機制)"""
    start_sec = max(0, cut_time_sec - PROBE_WINDOW_SEC)
    end_sec = min(len(y)/sr, cut_time_sec + PROBE_WINDOW_SEC)
    
    start_sample = int(start_sec * sr)
    end_sample = int(end_sec * sr)
    chunk = y[start_sample:end_sample]
    
    # 確保轉為 float32 (Whisper 要求的格式)
    chunk = chunk.astype(np.float32)
    
    # 使用 transcribe 啟動內建的幻覺過濾與 Fallback 機制
    result = asr_model.transcribe(
        chunk,
        language="zh",
        compression_ratio_threshold=2.4,  # 魔法參數：偵測到無限重複字眼時，強制重試並捨棄
        no_speech_threshold=0.6,          # 魔法參數：提高靜音門檻，讓模型勇敢承認「這裡沒人講話」
        logprob_threshold=-1.0            # 當模型對預測極度不自信時，直接輸出空白
    )
    
    return result["text"].strip()

def agent_reasoning(processor, llm_model, transcript, time_label, gap):
    """讓 Gemma-4 根據 ADOS 規則判斷是否為真實切分點"""

    system_prompt = f"""你是一位專精於自閉症 ADOS-2 測驗的臨床資料處理專家。
        我們偵測到一段長達 {gap:.1f} 秒的靜音斷點 (時間點: {time_label})。以下是該斷點前後 {PROBE_WINDOW_SEC} 秒的 Whisper 語音轉錄草稿：
        「{transcript}」

        你的任務是判斷是否要在這個時間點將音檔切開，代表一個「測驗任務的結束與下一個任務的開始」。請嚴格遵循以下邏輯：
        1. 【長靜音防呆】：如果靜音長度 (gap) 超過 60 秒，這代表嚴重的互動停滯或休息轉場，請一律允許切分 (is_boundary: true)。
        2. 【ASR 幻覺識別】：如果你看到毫無邏輯的無限重複字詞（如「他還沒回家他還沒回家...」或「拿東西拿東西...」），這是語音模型在背景雜音中產生的「幻覺」。這代表該區段實際上是安靜的空檔。若伴隨大於 5 秒的靜音，請判定為任務間的整理時間，允許切分 (is_boundary: true)。
        3. 【語意轉場】：若文字顯示「轉移注意力」、「開啟新話題」（如：來後面呢、看一下、這給你），代表任務切換，請允許切分 (is_boundary: true)。
        4. 【持續互動】：若文字顯示雙方「明顯還在同一個活動中緊密對話」，才判定為 false。

        請嚴格以 JSON 格式回傳，不要包含任何 Markdown 標記：
        {{
            "is_boundary": true 或 false,
            "reasoning": "你的判斷理由（繁體中文，限 30 字內）"
        }}
    """

    messages = [{"role": "user", "content": system_prompt}]

    # 透過 processor 處理輸入 (Gemma-4 的標準做法)
    # 如果 processor 本身支援 apply_chat_template，就用它來格式化對話
    if hasattr(processor, "apply_chat_template"):
        text = processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    else:
        # Fallback 保險機制，直接給純文字
        text = system_prompt

    inputs = processor(text=text, return_tensors="pt").to(llm_model.device)

    with torch.no_grad():
        outputs = llm_model.generate(**inputs, max_new_tokens=150, temperature=0.1)

    # 截斷輸入的 Prompt，只留下模型生成的回應
    generated_ids = outputs[0][inputs.input_ids.shape[1] :]
    response = processor.decode(generated_ids, skip_special_tokens=True)

    # 清理並解析 JSON
    try:
        clean_json = re.sub(r"```json|```", "", response).strip()
        decision = json.loads(clean_json)
        return decision
    except Exception as e:
        return {
            "is_boundary": False,
            "reasoning": f"解析失敗。預設不切分。Raw: {response}",
        }


def run_agentic_chunking(subject_id, wav_path, csv_path, output_dir):
    print(f"\n讀取資料: {subject_id}")
    df_cuts = pd.read_csv(csv_path)
    y, sr = librosa.load(wav_path, sr=16000)

    asr_model, processor, llm_model, device = load_models()

    print("\n啟動 Agentic 語意裁定流程 (Gemma-4 大腦)...")
    final_cuts = []

    for idx, row in df_cuts.iterrows():
        time_sec = row["time_sec"]
        time_label = row.get("time_formatted", f"{time_sec/60:.2f}m")
        gap = row["gap_duration"]

        print(
            f"\n[{idx+1}/{len(df_cuts)}] 探索候選點: {time_label} (靜音 {gap:.1f} 秒)"
        )

        # Step 1: 感知層 (Whisper) 擷取探針
        transcript = extract_probe_transcript(asr_model, y, sr, time_sec)
        print(f"   Whisper 探針: 「{transcript}」")

        # Step 2: 符號層 (Gemma-4) 進行推論
        decision = agent_reasoning(processor, llm_model, transcript, time_label, gap)
        action = "確定切分" if decision.get("is_boundary") else "❌ 忽略此點"

        print(f"   Gemma-4 裁定: {action} (理由: {decision.get('reasoning')})")

        if decision.get("is_boundary"):
            final_cuts.append(row)

    if final_cuts:
        df_final = pd.DataFrame(final_cuts)
        out_path = Path(output_dir) / f"{subject_id}_gemma4_cuts.csv"
        df_final.to_csv(out_path, index=False)
        print(
            f"\n處理完成！從 {len(df_cuts)} 個物理點中，提煉出 {len(df_final)} 個真實任務邊界。"
        )
        print(f"已儲存至: {out_path}")
    else:
        print("\nAgent 認為沒有任何點需要切分。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", type=str, required=True, help="例如: subject11")
    args = parser.parse_args()

    wav = f"data/{args.subject}/source/{args.subject.split('_')[0]}.wav"
    csv = f"docs/eda/chunk/{args.subject.split('_')[0]}_proposed_cuts.csv"
    out = "docs/eda/chunk/"

    if os.path.exists(wav) and os.path.exists(csv):
        run_agentic_chunking(args.subject, wav, csv, out)
    else:
        print("找不到 WAV 或 CSV 檔案，請確認路徑。")
        print(wav)
        print(csv)
