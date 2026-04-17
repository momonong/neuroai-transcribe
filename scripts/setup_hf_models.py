import os
from huggingface_hub import hf_hub_download, snapshot_download

# ==========================================
# 設定下載目標路徑 (Ubuntu 工作站路徑)
# ==========================================
# 在 Ubuntu 上，我們通常放在 ~/hf_models
BASE_MODEL_DIR = os.path.expanduser("~/hf_models")
os.makedirs(BASE_MODEL_DIR, exist_ok=True)

print(f"🚀 開始下載模型至: {BASE_MODEL_DIR}")

# 1. 下載 Gemma-3-12b-it QAT Q4_0 GGUF
# Repo: google/gemma-3-12b-it-gguf (或是專門提供 QAT 的 repo)
print("\n📦 下載 Gemma-3-12b-it-qat-q4_0 GGUF...")
try:
    hf_hub_download(
        repo_id="google/gemma-3-12b-it-gguf",
        filename="gemma-3-12b-it-qat-q4_0.gguf",
        local_dir=BASE_MODEL_DIR,
        local_dir_use_symlinks=False
    )
except Exception as e:
    print(f"⚠️ Google Repo 下載失敗，嘗試從社群 Repo 下載: {e}")
    # 備用方案：從社群常用的 GGUF 庫下載
    hf_hub_download(
        repo_id="unsloth/gemma-3-12b-it-GGUF",
        filename="gemma-3-12b-it-Q4_K_M.gguf", # 如果找不到精確的 QAT 檔名，下載最接近的
        local_dir=BASE_MODEL_DIR,
        local_dir_use_symlinks=False
    )

# 2. 下載 Whisper Large v3 (Transformers 格式)
print("\n📦 下載 Whisper Large v3...")
snapshot_download(
    repo_id="openai/whisper-large-v3",
    local_dir=os.path.join(BASE_MODEL_DIR, "whisper-large-v3"),
    local_dir_use_symlinks=False,
    ignore_patterns=["*.msgpack", "*.h5", "*.ot"]
)

# 3. 下載 Faster-Whisper 專用格式
print("\n📦 下載 Faster-Whisper Large v3...")
snapshot_download(
    repo_id="Systran/faster-whisper-large-v3",
    local_dir=os.path.join(BASE_MODEL_DIR, "faster-whisper-large-v3"),
    local_dir_use_symlinks=False
)

print(f"\n✅ 下載完成！")
print(f"請將您的 .env 模型路徑改為: {BASE_MODEL_DIR}")
