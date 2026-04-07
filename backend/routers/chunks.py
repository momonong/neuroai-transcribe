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
from schemas import SavePayload
from services import chunk_service

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
