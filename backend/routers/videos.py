"""
GET /api/videos, GET /api/cases
"""
from fastapi import APIRouter
from services.video_service import list_videos, list_cases

router = APIRouter(prefix="/api", tags=["videos"])


@router.get("/videos")
def get_videos():
    """掃描所有影片，供前端下拉選單使用。"""
    return list_videos()


@router.get("/cases")
def get_cases():
    """列出 data/ 底下的專案資料夾。"""
    return list_cases()
