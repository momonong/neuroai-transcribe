"""語者模型實驗與 I/O 測試（checkpoint、與 pipeline JSON 契約）。

模組：
- test_speaker_model_io：JSON 契約與 checkpoint 粗查
- analyze_speaker_checkpoint：由 state_dict 推斷 LSTM/Linear 等結構
- whisper_bilstm_diarization：pipeline 掛鉤（實作待補）

共用 placeholder 邏輯見 `core/diarization_placeholders.py`。
"""
