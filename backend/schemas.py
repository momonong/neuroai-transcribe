"""
API 請求／回應的 Pydantic 模型。
"""
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class RegisterBody(BaseModel):
    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1)
    real_name: str = Field(..., min_length=1, max_length=255)


class LoginBody(BaseModel):
    username: str
    password: str


class TranscriptSegment(BaseModel):
    sentence_id: float
    start: float
    end: float
    speaker: str
    text: str
    verification_score: float = 1.0
    status: str = "reviewed"
    needs_review: bool = False
    review_reason: Optional[str] = None
    suggested_correction: Optional[str] = None


class SavePayload(BaseModel):
    filename: str  # 相對路徑 (CaseName/chunk_x.json)
    speaker_mapping: Dict[str, str]
    segments: List[TranscriptSegment]
