"""
測試語者模型 checkpoint 能否載入，並對齊主流程的輸入／輸出 JSON 契約。

主流程（core/pipeline.py）假設：
  - *_whisper.json：list，每筆至少含 start, end, text（words 選填）
  - *_diar.json：list，每筆含 start, end, speaker（字串）

用法（專案根目錄）：
  python -m core.scripts.model.test_speaker_model_io --inspect
  python -m core.scripts.model.test_speaker_model_io --checkpoint models/whisper_medium_bilstm_best.pt --inspect
  python -m core.scripts.model.test_speaker_model_io --whisper path/to/chunk_xxx_whisper.json
  python -m core.scripts.model.test_speaker_model_io --whisper w.json --wav chunk.wav
  python -m core.scripts.model.test_speaker_model_io --whisper w.json --dry-write-diar out_diar.json

環境變數：
  SPEAKER_MODEL_PATH — checkpoint 預設路徑（未傳 --checkpoint 時）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 專案根加入 path
_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core.diarization_placeholders import whisper_to_placeholder_diar


def _patch_torch_load() -> None:
    """與 core/pipeline.py 一致，避免 PyTorch 2.6+ weights_only 預設造成載入失敗。"""
    import torch

    original_load = torch.load

    def permissive_load(*args: Any, **kwargs: Any) -> Any:
        if "weights_only" not in kwargs:
            kwargs["weights_only"] = False
        return original_load(*args, **kwargs)

    torch.load = permissive_load  # type: ignore[misc]


def default_checkpoint_path() -> Path:
    env = os.getenv("SPEAKER_MODEL_PATH")
    if env:
        return Path(env)
    return _project_root / "models" / "whisper_medium_bilstm_best.pt"


def validate_whisper_segments(data: Any) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    if not isinstance(data, list):
        return False, ["根節點必須是 JSON array（與 whisper_one_chunk 輸出一致）"]
    for i, seg in enumerate(data):
        if not isinstance(seg, dict):
            errors.append(f"segments[{i}] 必須為 object")
            continue
        for key in ("start", "end", "text"):
            if key not in seg:
                errors.append(f"segments[{i}] 缺少欄位 '{key}'")
        if "start" in seg and "end" in seg:
            try:
                if float(seg["end"]) < float(seg["start"]):
                    errors.append(f"segments[{i}]: end < start")
            except (TypeError, ValueError):
                errors.append(f"segments[{i}]: start/end 必須為數字")
    return len(errors) == 0, errors


def validate_diar_segments(data: Any) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    if not isinstance(data, list):
        return False, ["根節點必須是 JSON array（與 Pyannote 匯出／對齊模組一致）"]
    for i, seg in enumerate(data):
        if not isinstance(seg, dict):
            errors.append(f"segments[{i}] 必須為 object")
            continue
        for key in ("start", "end", "speaker"):
            if key not in seg:
                errors.append(f"segments[{i}] 缺少欄位 '{key}'")
        if "start" in seg and "end" in seg:
            try:
                if float(seg["end"]) < float(seg["start"]):
                    errors.append(f"segments[{i}]: end < start")
            except (TypeError, ValueError):
                errors.append(f"segments[{i}]: start/end 必須為數字")
        if "speaker" in seg and not isinstance(seg["speaker"], str):
            errors.append(f"segments[{i}]: speaker 必須為字串（對齊後會寫入 aligned）")
    return len(errors) == 0, errors


def inspect_checkpoint(path: Path) -> int:
    if not path.is_file():
        print(f"❌ 找不到 checkpoint: {path}")
        print("   可設定 SPEAKER_MODEL_PATH 或使用 --checkpoint")
        return 1

    _patch_torch_load()
    import torch

    print(f"📂 載入: {path}")
    try:
        obj = torch.load(str(path), map_location="cpu")
    except Exception as e:
        print(f"❌ torch.load 失敗: {e}")
        return 1

    print(f"   Python 型別: {type(obj).__name__}")

    if isinstance(obj, dict):
        print(f"   dict 頂層 keys（最多列 40 個）: {list(obj.keys())[:40]}")
        for common in ("state_dict", "model_state_dict", "model", "config", "epoch", "args"):
            if common in obj:
                v = obj[common]
                if isinstance(v, dict) and common in ("state_dict", "model_state_dict"):
                    keys = list(v.keys())
                    print(f"   └─ {common}: {len(keys)} 個 tensor 鍵，前 15 個: {keys[:15]}")
                    for k in keys[:5]:
                        t = v[k]
                        if hasattr(t, "shape"):
                            print(f"      {k!r}: shape={tuple(t.shape)}, dtype={getattr(t, 'dtype', '')}")
                else:
                    print(f"   └─ {common}: {type(v).__name__}")

    if hasattr(obj, "state_dict"):
        try:
            sd = obj.state_dict()
            keys = list(sd.keys())
            print(f"   nn.Module.state_dict: {len(keys)} keys, 前 12 個: {keys[:12]}")
        except Exception as e:
            print(f"   （讀取 state_dict 時例外）: {e}")

    # 若整份就是 state_dict
    if isinstance(obj, dict) and all(
        hasattr(v, "shape") for v in obj.values() if v is not None
    ):
        sample = [(k, tuple(v.shape)) for k, v in list(obj.items())[:8] if hasattr(v, "shape")]
        if sample:
            print("   疑似純 state_dict，範例 shape:")
            for k, sh in sample:
                print(f"      {k}: {sh}")

    print()
    print("💡 若僅有 state_dict，需在專案中實作與訓練時相同的 nn.Module 再 load_state_dict。")
    print("   本腳本只做載入與契約檢查，不包含 BiLSTM 架構定義。")
    return 0


def summarize_wav(wav_path: Path) -> int:
    try:
        import torchaudio
    except ImportError:
        print("❌ 需要 torchaudio（見 core/requirements.txt）")
        return 1
    wav, sr = torchaudio.load(str(wav_path))
    if wav.dim() == 2 and wav.size(0) > 1:
        wav = wav.mean(dim=0, keepdim=True)
    dur = wav.numel() / sr
    print(f"🎧 {wav_path.name}: sr={int(sr)}, 聲道合併後 shape={tuple(wav.shape)}, 長度約 {dur:.2f}s")
    return 0


def cmd_validate_whisper(args: argparse.Namespace) -> int:
    p = Path(args.whisper)
    if not p.is_file():
        print(f"❌ 找不到: {p}")
        return 1
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    ok, errs = validate_whisper_segments(data)
    if ok:
        print(f"✅ Whisper JSON 契約通過，共 {len(data)} 段")
    else:
        print("❌ Whisper JSON 契約失敗:")
        for e in errs[:30]:
            print(f"   - {e}")
        if len(errs) > 30:
            print(f"   ... 另有 {len(errs) - 30} 筆")
        return 1

    if args.wav:
        summarize_wav(Path(args.wav))

    if args.dry_write_diar:
        diar = whisper_to_placeholder_diar(data, speaker=args.placeholder_speaker)
        out = Path(args.dry_write_diar)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(diar, f, ensure_ascii=False, indent=2)
        ok_d, e2 = validate_diar_segments(diar)
        print(f"📝 已寫入 placeholder diar: {out}（{len(diar)} 段）")
        if not ok_d:
            print("❌ 產生的 diar 未通過驗證（不應發生）:", e2)
            return 1
        print("✅ 產生的 diar JSON 契約通過（可搭配 run_alignment 測試）")

    return 0


def cmd_validate_diar(args: argparse.Namespace) -> int:
    p = Path(args.diar)
    if not p.is_file():
        print(f"❌ 找不到: {p}")
        return 1
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    ok, errs = validate_diar_segments(data)
    if ok:
        print(f"✅ Diar JSON 契約通過，共 {len(data)} 段")
        return 0
    print("❌ Diar JSON 契約失敗:")
    for e in errs[:30]:
        print(f"   - {e}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="語者模型 checkpoint / pipeline JSON I/O 測試")
    parser.add_argument(
        "--checkpoint",
        type=str,
        default=None,
        help=".pt 路徑（預設：SPEAKER_MODEL_PATH 或 models/whisper_medium_bilstm_best.pt）",
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="載入 checkpoint 並印出結構（不含前向推論）",
    )
    parser.add_argument("--whisper", type=str, default=None, help="驗證 *_whisper.json")
    parser.add_argument("--diar", type=str, default=None, help="驗證 *_diar.json")
    parser.add_argument("--wav", type=str, default=None, help="與 --whisper 並用時摘要音訊檔")
    parser.add_argument(
        "--dry-write-diar",
        type=str,
        default=None,
        metavar="OUT.json",
        help="依 Whisper 段寫出 placeholder diar（測試對齊契約）",
    )
    parser.add_argument(
        "--placeholder-speaker",
        type=str,
        default="PLACEHOLDER_SPEAKER",
        help="--dry-write-diar 時的 speaker 字串",
    )

    args = parser.parse_args()
    code = 0

    if args.inspect or (not args.whisper and not args.diar):
        ck = Path(args.checkpoint) if args.checkpoint else default_checkpoint_path()
        code = inspect_checkpoint(ck)
        if not args.whisper and not args.diar:
            return code

    if args.whisper:
        r = cmd_validate_whisper(args)
        code = code or r

    if args.diar:
        r = cmd_validate_diar(args)
        code = code or r

    return code


if __name__ == "__main__":
    raise SystemExit(main())
