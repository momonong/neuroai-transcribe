"""
API 請求／回應的 Pydantic 模型。
"""
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

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
