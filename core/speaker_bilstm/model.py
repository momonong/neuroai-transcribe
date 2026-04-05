from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple, Union

import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers import WhisperModel, WhisperProcessor


class WeightedAverageLayer(nn.Module):
    """對 Whisper encoder 各層 hidden states 做可學習加權平均。"""

    def __init__(self, num_layers: int):
        super().__init__()
        self.num_layers = int(num_layers)
        self.layer_weights = nn.Parameter(torch.ones(self.num_layers) / self.num_layers)

    def forward(self, hidden_states: Tuple[torch.Tensor, ...]) -> torch.Tensor:
        stacked_states = torch.stack(hidden_states, dim=0)
        normalized_weights = F.softmax(self.layer_weights, dim=0)
        weights = normalized_weights.view(-1, 1, 1, 1)
        return (stacked_states * weights).sum(dim=0)

    def get_layer_importance(self) -> torch.Tensor:
        with torch.no_grad():
            return F.softmax(self.layer_weights, dim=0)


class BiLSTMHead(nn.Module):
    """BiLSTM head：輸入 Whisper hidden_dim，輸出 hidden_dim*2（雙向）。"""

    def __init__(
        self,
        input_dim: int,
        hidden_dim: int = 128,
        num_layers: int = 2,
        dropout: float = 0.2,
    ):
        super().__init__()
        self.input_dim = int(input_dim)
        self.hidden_dim = int(hidden_dim)
        self.num_layers = int(num_layers)
        self.output_dim = self.hidden_dim * 2

        self.lstm = nn.LSTM(
            input_size=self.input_dim,
            hidden_size=self.hidden_dim,
            num_layers=self.num_layers,
            dropout=dropout if self.num_layers > 1 else 0.0,
            batch_first=True,
            bidirectional=True,
        )
        self.layer_norm = nn.LayerNorm(self.output_dim)
        self.dropout = nn.Dropout(p=float(dropout))
        self._init_weights()

    def _init_weights(self) -> None:
        for name, param in self.lstm.named_parameters():
            if "weight_ih" in name:
                nn.init.xavier_uniform_(param.data)
            elif "weight_hh" in name:
                nn.init.orthogonal_(param.data)
            elif "bias" in name:
                param.data.fill_(0)
                n = param.size(0)
                param.data[n // 4 : n // 2].fill_(1.0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        lstm_out, _ = self.lstm(x)
        lstm_out = self.layer_norm(lstm_out)
        return self.dropout(lstm_out)


class ClassifierHead(nn.Module):
    """1x1 Conv1d，等價於 Linear(hidden->num_classes) 逐 frame 分類。"""

    def __init__(self, input_dim: int, num_classes: int = 3):
        super().__init__()
        self.classifier = nn.Conv1d(
            in_channels=int(input_dim),
            out_channels=int(num_classes),
            kernel_size=1,
            stride=1,
            padding=0,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, seq, dim) -> (batch, dim, seq) -> conv -> (batch, cls, seq) -> (batch, seq, cls)
        x = x.transpose(1, 2)
        logits = self.classifier(x)
        return logits.transpose(1, 2)


class MedianFilter1D(nn.Module):
    """對 frame-level label 做中值濾波（推論時平滑）。"""

    def __init__(self, kernel_size: int = 5):
        super().__init__()
        k = int(kernel_size)
        if k <= 0 or k % 2 == 0:
            raise ValueError("kernel_size 必須為正奇數")
        self.kernel_size = k
        self.pad = k // 2

    @staticmethod
    def _median_1d(x: torch.Tensor) -> torch.Tensor:
        return x.median(dim=-1).values

    def filter_predictions(self, predictions: torch.Tensor) -> torch.Tensor:
        # predictions: (T,) long
        if predictions.ndim != 1:
            predictions = predictions.reshape(-1)
        x = predictions.to(torch.long)
        # NOTE: torch.nn.functional.pad(mode="replicate") 不支援 1D（會拋 NotImplementedError）。
        # 手動做左右 replicate padding： [x0]*pad + x + [xT]*pad
        if x.numel() == 0:
            return x
        if self.pad > 0:
            left = x[:1].repeat(self.pad)
            right = x[-1:].repeat(self.pad)
            x_pad = torch.cat([left, x, right], dim=0)
        else:
            x_pad = x
        windows = x_pad.unfold(0, self.kernel_size, 1)
        return self._median_1d(windows).to(torch.long)


class WhisperBiLSTMModel(nn.Module):
    """
    Whisper encoder + WeightedAverage + BiLSTM + 1x1 Conv classifier.

    forward(audio) expects audio shape: (batch, num_samples) at config.sample_rate.
    """

    def __init__(self, config: Any):
        super().__init__()
        self.config = config

        self.whisper = WhisperModel.from_pretrained(config.whisper_model_name)
        self.processor = WhisperProcessor.from_pretrained(config.whisper_model_name)

        self.whisper_config = self.whisper.config
        self.hidden_dim = int(self.whisper_config.d_model)
        self.num_encoder_layers = int(self.whisper_config.encoder_layers) + 1

        if bool(getattr(config, "freeze_encoder", True)):
            for p in self.whisper.encoder.parameters():
                p.requires_grad = False

        self.weighted_avg = WeightedAverageLayer(self.num_encoder_layers)
        self.bilstm_head = BiLSTMHead(
            input_dim=self.hidden_dim,
            hidden_dim=int(getattr(config, "lstm_hidden_size", 128)),
            num_layers=int(getattr(config, "lstm_num_layers", 2)),
            dropout=float(getattr(config, "dropout", 0.2)),
        )
        self.classifier = ClassifierHead(
            input_dim=int(getattr(config, "lstm_hidden_size", 128)) * 2,
            num_classes=int(getattr(config, "num_classes", 3)),
        )
        self.median_filter = MedianFilter1D(
            kernel_size=int(getattr(config, "median_filter_size", 5))
        )

    def forward(
        self, audio: torch.Tensor, attention_mask: Optional[torch.Tensor] = None
    ) -> torch.Tensor:
        input_features = self._prepare_features(audio)
        enc = self.whisper.encoder(
            input_features,
            output_hidden_states=True,
            return_dict=True,
        )
        hidden_states = enc.hidden_states
        weighted = self.weighted_avg(hidden_states)
        lstm_features = self.bilstm_head(weighted)
        return self.classifier(lstm_features)

    def _prepare_features(self, audio: torch.Tensor) -> torch.Tensor:
        # NOTE: 保持與原 Neuro-AI 邏輯一致：逐樣本用 processor 產生 input_features，再 stack。
        batch_size = int(audio.shape[0])
        device = audio.device
        feats = []
        for i in range(batch_size):
            audio_np = audio[i].detach().cpu().numpy()
            f = self.processor(
                audio_np, sampling_rate=int(self.config.sample_rate), return_tensors="pt"
            ).input_features
            feats.append(f.squeeze(0))
        return torch.stack(feats).to(device)

    def predict(
        self, audio: torch.Tensor, return_probs: bool = False
    ) -> Union[torch.Tensor, Tuple[torch.Tensor, torch.Tensor]]:
        self.eval()
        with torch.no_grad():
            logits = self.forward(audio)
            probs = F.softmax(logits, dim=-1)
            preds = torch.argmax(logits, dim=-1)
            return (preds, probs) if return_probs else preds


def load_model(config: Any, checkpoint_path: str) -> nn.Module:
    model = WhisperBiLSTMModel(config).to(config.device)
    checkpoint = torch.load(checkpoint_path, map_location=config.device)
    sd = checkpoint.get("model_state_dict") if isinstance(checkpoint, dict) else None
    model.load_state_dict(sd if sd is not None else checkpoint)
    return model

