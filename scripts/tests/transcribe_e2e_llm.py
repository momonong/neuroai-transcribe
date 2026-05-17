import torch
import librosa
import argparse
import os
import json
import soundfile as sf
from transformers import AutoProcessor, AutoModelForImageTextToText # 依照你的設定

# 你指定的模型
MODEL_ID = "google/gemma-4-E4B-it"

def test_e2e_transcription(subject_id, wav_path):
    """
    測試直接將音訊餵給多模態 LLM 進行端到端轉錄
    (以 30 秒為單位進行分段處理，轉錄整個檔案)
    """
    print(f"🚀 啟動 E2E 測試，載入模型: {MODEL_ID}")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    
    # 載入你指定的 Processor 與 Model
    # 加入 dtype=torch.bfloat16 以確保 4090 VRAM 不會爆掉
    processor = AutoProcessor.from_pretrained(MODEL_ID)
    model = AutoModelForImageTextToText.from_pretrained(
        MODEL_ID,
        device_map="auto",
        dtype=torch.bfloat16
    )

    print(f"\n⏳ 正在讀取整段音檔...")
    # 多模態模型通常預設接受 16kHz 的音訊
    audio_full, sr = librosa.load(wav_path, sr=16000)
    total_duration = librosa.get_duration(y=audio_full, sr=sr)
    print(f"總長度: {total_duration:.2f} 秒")

    chunk_duration = 30.0
    segments = []

    for start_sec in range(0, int(total_duration), int(chunk_duration)):
        end_sec = min(start_sec + chunk_duration, total_duration)
        print(f"\n[{start_sec:.1f}s - {end_sec:.1f}s] 🧠 正在送入 LLM 進行推理...")
        
        start_sample = int(start_sec * sr)
        end_sample = int(end_sec * sr)
        audio_chunk = audio_full[start_sample:end_sample]
        
        # 將切好的音訊暫存，確保 apply_chat_template 可以讀取正確的音訊檔
        temp_audio_path = f"/tmp/temp_{subject_id}_{start_sec}_{end_sec}.wav"
        sf.write(temp_audio_path, audio_chunk, sr)
        
        # 設計 Prompt 要求模型轉錄並辨識語者
        prompt_text = "請聆聽這段音訊，並產生帶有語者標籤（例如 測試員: 或 孩童:）的逐字稿。"
        
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "audio", "audio": temp_audio_path},
                    {"type": "text", "text": prompt_text},
                ]
            }
        ]

        try:
            inputs = processor.apply_chat_template(
                messages,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
                add_generation_prompt=True,
            ).to(model.device)
        except Exception as e:
            print(f"⚠️ 處理輸入時發生錯誤：{e}")
            if os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
            continue

        input_len = inputs["input_ids"].shape[-1]

        # 執行推論
        with torch.no_grad():
            outputs = model.generate(**inputs, max_new_tokens=512)

        # 解碼輸出
        response = processor.decode(outputs[0][input_len:], skip_special_tokens=False)
        
        try:
            generated_text = processor.parse_response(response)
            # 若回傳非字串，試著轉換處理
            if not isinstance(generated_text, str):
                generated_text = str(generated_text)
        except AttributeError:
            # Fallback，如果 processor 沒有 parse_response 方法
            generated_text = processor.decode(outputs[0][input_len:], skip_special_tokens=True)

        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)
        
        print(f"🎯 結果: {generated_text.strip()}")
        
        segments.append({
            "start": float(start_sec),
            "end": float(end_sec),
            "text": generated_text.strip(),
            "speaker": "Unknown",
            "status": "e2e_test"
        })

    print("\n" + "="*50)
    print("✅ 全檔轉錄完成")
    print("="*50)

    # 依照 OUTPUT.md 結構儲存結果
    output_dir = f"data/{subject_id}/output"
    os.makedirs(output_dir, exist_ok=True)
    
    output_data = {
        "case_name": subject_id,
        "video_file": os.path.basename(wav_path),
        "segments": segments
    }
    
    output_path = os.path.join(output_dir, f"{subject_id}_e2e_transcript.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"📁 測試結果已儲存至: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", type=str, required=True, help="例如: subject11")
    args = parser.parse_args()
    
    wav_file = f"data/{args.subject}/source/{args.subject.split('_')[0]}.wav"
    test_e2e_transcription(args.subject, wav_file)