"""
從訓練 checkpoint 的 model_state_dict 推斷模組結構（無需訓練腳本）。

會嘗試辨識：LSTM/BiLSTM、Linear、LayerNorm、Conv1d、Embedding 等，並列出非 whisper 參數樹狀摘要。
若 checkpoint 含 `config`，會一併印出（便於對齊類別數、維度等）。

用法（專案根）：
  python -m core.scripts.model.analyze_speaker_checkpoint
  python -m core.scripts.model.analyze_speaker_checkpoint --checkpoint models/whisper_medium_bilstm_best.pt
  python -m core.scripts.model.analyze_speaker_checkpoint --checkpoint path/to.pt --dump-keys bilstm
  python -m core.scripts.model.analyze_speaker_checkpoint --list-non-whisper-keys
  python -m core.scripts.model.analyze_speaker_checkpoint --include-whisper-linear
  python -m core.scripts.model.analyze_speaker_checkpoint --no-config

環境變數：SPEAKER_MODEL_PATH

注意：Windows 終端機若使用 cp950，請設定 UTF-8（例如 chcp 65001）以避免中文亂碼。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, DefaultDict, Dict, List, Optional, Set, Tuple

_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def _patch_torch_load() -> None:
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


def _is_tensor_like(v: Any) -> bool:
    try:
        import torch

        return isinstance(v, torch.Tensor)
    except Exception:
        return False


# PyTorch LSTM: weight_ih_l0, weight_hh_l0, bias_ih_l0, bias_hh_l0 [, _reverse]
_LSTM_IH = re.compile(r"^(?P<prefix>.+)\.weight_ih_l(?P<layer>\d+)(?P<rev>_reverse)?$")


def _collect_lstm_groups(sd: Dict[str, Any]) -> Dict[str, List[Tuple[str, Any]]]:
    """prefix -> list of (key, tensor) for weight_ih entries (used to infer hidden/input)."""
    groups: DefaultDict[str, List[Tuple[str, Any]]] = defaultdict(list)
    for k, t in sd.items():
        if not _is_tensor_like(t) or t.dim() != 2:
            continue
        m = _LSTM_IH.match(k)
        if m:
            groups[m.group("prefix")].append((k, t))
    return dict(groups)


def _infer_lstm_block(prefix: str, items: List[Tuple[str, Any]]) -> List[str]:
    """Return human-readable lines for one LSTM module path."""
    import torch

    lines: List[str] = []
    by_layer_rev: Dict[Tuple[int, bool], Any] = {}
    for k, t in items:
        m = _LSTM_IH.match(k)
        if not m:
            continue
        layer = int(m.group("layer"))
        rev = bool(m.group("rev"))
        by_layer_rev[(layer, rev)] = t

    if not by_layer_rev:
        return lines

    layers = sorted({lr[0] for lr in by_layer_rev.keys()})
    bidirectional = any(lr[1] for lr in by_layer_rev.keys())

    lines.append(f"  [推斷] {prefix} -> torch.nn.LSTM 類（含 weight_ih_l*）")
    lines.append(f"        層數(num_layers)推斷: {len(layers)}  |  bidirectional={bidirectional}")

    for layer in layers:
        for rev in (False, True):
            t = by_layer_rev.get((layer, rev))
            if t is None:
                continue
            h = t.shape[0] // 4
            inp = t.shape[1]
            tag = "reverse" if rev else "forward"
            lines.append(
                f"        - l{layer} {tag}: weight_ih -> hidden~{h}, input_dim={inp} "
                f"(shape={tuple(t.shape)})"
            )
    return lines


def _linear_like_keys(sd: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    keys_set = set(sd.keys())
    for k, t in sd.items():
        if not _is_tensor_like(t) or t.dim() != 2:
            continue
        if _LSTM_IH.match(k):
            continue
        if k.endswith(".weight"):
            base = k[:-7]
            if f"{base}.bias" in keys_set:
                out.append(k)
    return sorted(out)


def _layernorm_keys(sd: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    keys_set = set(sd.keys())
    for k, t in sd.items():
        if not _is_tensor_like(t) or t.dim() != 1:
            continue
        if k.endswith(".weight"):
            base = k[:-7]
            bk = f"{base}.bias"
            if bk in keys_set and _is_tensor_like(sd[bk]) and sd[bk].shape == t.shape:
                out.append(base)
    return sorted(set(out))


def _conv1d_keys(sd: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for k, t in sd.items():
        if not _is_tensor_like(t) or t.dim() != 3:
            continue
        if k.endswith(".weight"):
            out.append(k)
    return sorted(out)


def _embedding_keys(sd: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    keys_set = set(sd.keys())
    for k, t in sd.items():
        if not _is_tensor_like(t) or t.dim() != 2:
            continue
        if not k.endswith(".weight"):
            continue
        if _LSTM_IH.match(k):
            continue
        base = k[:-7]
        if f"{base}.bias" in keys_set:
            continue
        # Heuristic: embedding tables are often named embed / embedding
        leaf = base.split(".")[-1].lower()
        if "embed" in leaf or "token" in leaf:
            out.append(k)
    return sorted(out)


def _top_level_prefix(key: str) -> str:
    return key.split(".", 1)[0]


def _summarize_whisper_branch(sd: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    wkeys = [k for k in sd if k.startswith("whisper.")]
    if not wkeys:
        return ["  （無 whisper.* 前綴）"]
    sub = defaultdict(int)
    for k in wkeys:
        parts = k.split(".")
        if len(parts) >= 3:
            sub[".".join(parts[:3])] += 1
        else:
            sub[parts[1] if len(parts) > 1 else k] += 1
    lines.append(f"  whisper.* 參數總數: {len(wkeys)}")
    lines.append("  子區塊（前 25 個 path 前綴計數）:")
    for p, c in sorted(sub.items(), key=lambda x: -x[1])[:25]:
        lines.append(f"    {p}: {c} tensors")
    return lines


def _non_whisper_keys(sd: Dict[str, Any]) -> List[str]:
    return sorted(k for k in sd if not k.startswith("whisper."))


def analyze_state_dict(
    sd: Dict[str, Any],
    dump_keys_prefix: Optional[str],
    *,
    include_whisper_linear: bool = False,
) -> str:
    lines: List[str] = []
    lines.append("=== model_state_dict 結構推斷 ===\n")

    lstm_groups = _collect_lstm_groups(sd)
    if lstm_groups:
        lines.append("-- LSTM / BiLSTM --")
        for prefix in sorted(lstm_groups.keys()):
            lines.extend(_infer_lstm_block(prefix, lstm_groups[prefix]))
        lines.append("")

    lin_weights = _linear_like_keys(sd)
    nw_lin = [wk for wk in lin_weights if not wk.startswith("whisper.")]
    w_lin = [wk for wk in lin_weights if wk.startswith("whisper.")]

    lines.append("-- Linear（非 whisper：分類頭等）--")
    if not nw_lin:
        lines.append("  （無二維 Linear；若分類層為 Conv1d 1x1，見下方 Conv1d 一節）")
    for wk in nw_lin:
        t = sd[wk]
        base = wk[:-7]
        bout = t.shape[0]
        bin_ = t.shape[1]
        lines.append(f"  {base}: Linear in_features={bin_}, out_features={bout}")
        if bout <= 64:
            lines.append(f"    -> 若為最後分類層，類別數可能為 {bout}")
    lines.append("")
    lines.append(
        f"-- Linear（whisper 子模組）: 共 {len(w_lin)} 個（明細冗長，預設省略）--"
    )
    if include_whisper_linear and w_lin:
        cap = 40
        for wk in w_lin[:cap]:
            t = sd[wk]
            base = wk[:-7]
            lines.append(
                f"  {base}: in={t.shape[1]}, out={t.shape[0]}"
            )
        if len(w_lin) > cap:
            lines.append(f"  ... 另有 {len(w_lin) - cap} 個")
    elif w_lin:
        lines.append("  使用 --include-whisper-linear 可列出前 40 個")
    lines.append("")

    ln = _layernorm_keys(sd)
    nw_ln = [b for b in ln if not b.startswith("whisper.")]
    w_ln_ct = len(ln) - len(nw_ln)
    if nw_ln or w_ln_ct:
        lines.append("-- LayerNorm（推斷）--")
        for base in nw_ln:
            t = sd[f"{base}.weight"]
            lines.append(f"  {base}: normalized_shape={tuple(t.shape)}")
        if w_ln_ct:
            lines.append(f"  （whisper 內另有約 {w_ln_ct} 個 LayerNorm，已省略）")
        lines.append("")

    convs = _conv1d_keys(sd)
    non_whisper_conv = [k for k in convs if not k.startswith("whisper.")]
    if non_whisper_conv:
        lines.append("-- Conv1d（三維 .weight，非 whisper）--")
        for k in non_whisper_conv[:40]:
            t = sd[k]
            oc, ic, ks = t.shape
            lines.append(f"  {k[:-7]}: out_channels={oc}, in_channels={ic}, kernel={ks}")
            if ks == 1 and oc <= 64:
                lines.append(
                    f"    -> 1x1 Conv 常等同 Linear({ic}->{oc})；類別數可能為 {oc}"
                )
        lines.append("")

    emb = _embedding_keys(sd)
    non_w_emb = [k for k in emb if not k.startswith("whisper.")]
    if non_w_emb:
        lines.append("-- Embedding（啟發式：*.weight 二維、無 bias、名稱含 embed）--")
        for k in non_w_emb:
            lines.append(f"  {k[:-7]}: shape={tuple(sd[k].shape)}")
        lines.append("")

    nw = _non_whisper_keys(sd)
    lines.append(f"-- 非 whisper 參數筆數: {len(nw)} / 總計 {len(sd)} --")
    top_counts: DefaultDict[str, int] = defaultdict(int)
    for k in nw:
        top_counts[_top_level_prefix(k)] += 1
    for name, cnt in sorted(top_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  [{name}] {cnt} keys")

    if dump_keys_prefix:
        lines.append(f"\n-- 篩選 key 包含 {dump_keys_prefix!r} --")
        for k in nw:
            if dump_keys_prefix.lower() in k.lower():
                t = sd[k]
                if _is_tensor_like(t):
                    lines.append(f"  {k}: shape={tuple(t.shape)}, dtype={t.dtype}")
                else:
                    lines.append(f"  {k}: ({type(t).__name__})")

    return "\n".join(lines)


def pretty_config(cfg: Any, max_len: int = 12000) -> str:
    try:
        s = json.dumps(cfg, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        s = repr(cfg) + f"\n(json 失敗: {e})"
    if len(s) > max_len:
        orig = len(s)
        s = s[:max_len] + f"\n\n... (截斷，原長 {orig} 字元)"
    return s


def main() -> int:
    parser = argparse.ArgumentParser(
        description="從 checkpoint 推斷模型結構（state_dict + config）"
    )
    parser.add_argument(
        "--checkpoint",
        type=str,
        default=None,
        help="checkpoint .pt 路徑",
    )
    parser.add_argument(
        "--dump-keys",
        type=str,
        default=None,
        metavar="SUBSTR",
        help="列出非 whisper 且 key 含此子字串的參數與 shape",
    )
    parser.add_argument(
        "--no-config",
        action="store_true",
        help="不印出 checkpoint['config']",
    )
    parser.add_argument(
        "--include-whisper-linear",
        action="store_true",
        help="列出 whisper 內前 40 個 Linear（預設只顯示筆數）",
    )
    parser.add_argument(
        "--list-non-whisper-keys",
        action="store_true",
        help="列出所有非 whisper.* 的 state_dict key（含 shape）",
    )
    args = parser.parse_args()

    path = Path(args.checkpoint) if args.checkpoint else default_checkpoint_path()
    if not path.is_file():
        print(f"[ERROR] 找不到檔案: {path}")
        return 1

    _patch_torch_load()
    import torch

    print(f"[LOAD] {path}\n")
    try:
        ckpt = torch.load(str(path), map_location="cpu")
    except Exception as e:
        print(f"[ERROR] torch.load 失敗: {e}")
        return 1

    if not isinstance(ckpt, dict):
        print(f"頂層型別為 {type(ckpt).__name__}，本腳本預期為 dict（含 model_state_dict）。")
        return 1

    if "config" in ckpt and not args.no_config:
        print("=== checkpoint['config'] ===")
        print(pretty_config(ckpt["config"]))
        print()

    for k in ("epoch", "history"):
        if k in ckpt:
            v = ckpt[k]
            if k == "history" and isinstance(v, list) and len(v) > 5:
                print(f"=== {k} (list 長度 {len(v)}，最後 3 筆) ===")
                print(pretty_config(v[-3:]))
            else:
                print(f"=== {k} ===")
                print(pretty_config(v))
            print()

    sd = ckpt.get("model_state_dict") or ckpt.get("state_dict")
    if sd is None:
        print("[ERROR] 找不到 model_state_dict / state_dict")
        return 1
    if not isinstance(sd, dict):
        print("[ERROR] state_dict 不是 dict")
        return 1

    whisper_summary = _summarize_whisper_branch(sd)
    print("\n".join(whisper_summary))
    print()

    if args.list_non_whisper_keys:
        print("=== 非 whisper.* 的 key（全表）===")
        for k in _non_whisper_keys(sd):
            t = sd[k]
            if _is_tensor_like(t):
                print(f"  {k}: shape={tuple(t.shape)}")
            else:
                print(f"  {k}: ({type(t).__name__})")
        print()

    print(
        analyze_state_dict(
            sd,
            args.dump_keys,
            include_whisper_linear=args.include_whisper_linear,
        )
    )

    print(
        "\n=== 說明 ===\n"
        "- LSTM 的 input_dim 在第一層 forward 反映「進入 LSTM 的特徵維度」；\n"
        "  若前一塊是 Whisper encoder 輸出，應與 encoder 時間步的 hidden 維度一致（Medium 常為 1024）。\n"
        "- 最後一層 Linear 的 out_features 常等於分類類別數（需與訓練標籤對齊）。\n"
        "- 若推斷與實際不符，請用 --dump-keys <子字串> 搜尋非 whisper 的 key。\n"
        "- 仍須自行實作與此 state_dict 鍵名一致的 nn.Module 才能 forward。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
