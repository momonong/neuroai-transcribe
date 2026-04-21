"""
API 請求／回應的 Pydantic 模型。
"""
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from models import TaskStatus


class RegisterBody(BaseModel):
    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1)
    real_name: str = Field(..., min_length=1, max_length=255)


class LoginBody(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    """登入後變更自己的密碼。"""

    model_config = ConfigDict(extra="forbid")

    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=1)


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


class SegmentReinferRequest(BaseModel):
    """請求對 chunk 内一段時間（與前端 segment.start/end 同座標系）重新做 Whisper 辨識。"""

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(..., min_length=1, description="chunk 檔相對路徑，與 /api/temp/save 相同")
    start_sec: float = Field(..., ge=0, description="相對於原始音檔的絕對起始秒數（與前端 segment.start 一致）")
    end_sec: float = Field(..., ge=0, description="相對於原始音檔的絕對結束秒數（與前端 segment.end 一致）")
    sentence_id: Optional[float] = Field(None, description="前端 segment sentence_id，供實作端對位")

    @model_validator(mode="after")
    def end_after_start(self):
        if self.end_sec <= self.start_sec:
            raise ValueError("結束時間必須大於開始時間")
        return self


class SegmentReinferResponse(BaseModel):
    """實作 Whisper 後可回傳辨識文字；未實作時 text 為 null。"""

    ok: bool = True
    text: Optional[str] = None
    message: str = ""


class AdminCreateProjectBody(BaseModel):
    """管理員建立專案。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=10_000)


class AdminUpdateProjectBody(BaseModel):
    """管理員更新專案（至少提供一個欄位）。"""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=10_000)


class TaskUpdate(BaseModel):
    """PATCH 任務：僅傳入要更新的欄位；assignee_id 傳 null 表示未指派。"""

    model_config = ConfigDict(extra="forbid")

    status: Optional[TaskStatus] = None
    assignee_id: Optional[int] = None
    project_id: Optional[int] = None
