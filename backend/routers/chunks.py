"""
GET /api/temp/chunks, GET /api/temp/chunk/{filename:path}, POST /api/temp/save
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from deps import assert_project_member, assert_user_can_access_case, get_current_user
from models import Task, User
from schemas import SavePayload, SegmentReinferRequest, SegmentReinferResponse
from services import chunk_service
from services.segment_reinfer import run_segment_reinfer

router = APIRouter(prefix="/api", tags=["chunks"])


@router.get("/temp/chunks")
def list_chunks(
    case: Optional[str] = None,
    project_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if case:
        assert_user_can_access_case(db, user, case)
        files = chunk_service.list_chunks(case=case)
        return {"files": files}
    if project_id is None:
        raise HTTPException(status_code=400, detail="未指定 case 時必須提供 project_id")
    assert_project_member(db, user.id, project_id)
    names = db.scalars(select(Task.case_name).where(Task.project_id == project_id)).all()
    if not names:
        return {"files": []}
    files = chunk_service.list_chunks_for_cases(names)
    return {"files": files}


@router.get("/temp/chunk/{filename:path}")
def get_chunk(
    filename: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    case_name = chunk_service.case_name_from_relative_path(filename)
    assert_user_can_access_case(db, user, case_name)
    try:
        return chunk_service.get_chunk(filename)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/temp/save")
def save_chunk(
    payload: SavePayload,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    case_name = chunk_service.case_name_from_relative_path(payload.filename)
    assert_user_can_access_case(db, user, case_name)
    try:
        return chunk_service.save_chunk(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/temp/reinfer-segment", response_model=SegmentReinferResponse)
def reinfer_segment(
    body: SegmentReinferRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    依目前 segment 的時間範圍（chunk 相對秒）觸發重新語音辨識。
    實際 Whisper 邏輯見 services.segment_reinfer.run_segment_reinfer。
    """
    case_name = chunk_service.case_name_from_relative_path(body.filename)
    assert_user_can_access_case(db, user, case_name)

    raw = run_segment_reinfer(
        case_name=case_name,
        chunk_filename=body.filename,
        start_sec=body.start_sec,
        end_sec=body.end_sec,
        sentence_id=body.sentence_id,
    )
    return SegmentReinferResponse.model_validate(raw)
