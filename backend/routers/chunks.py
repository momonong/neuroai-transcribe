"""
GET /api/temp/chunks, GET /api/temp/chunk/{filename:path}, POST /api/temp/save
"""
from typing import Optional
from fastapi import APIRouter, HTTPException
from schemas import SavePayload
from services import chunk_service

router = APIRouter(prefix="/api", tags=["chunks"])


@router.get("/temp/chunks")
def list_chunks(case: Optional[str] = None):
    """列出 JSON 檔案（智慧篩選：每 chunk ID 只回傳最高優先級檔案）。"""
    files = chunk_service.list_chunks(case=case)
    return {"files": files}


@router.get("/temp/chunk/{filename:path}")
def get_chunk(filename: str):
    """讀取單一 chunk；若不存在 404，例外 500。"""
    try:
        return chunk_service.get_chunk(filename)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/temp/save")
def save_chunk(payload: SavePayload):
    """存檔 API：寫入 _edited.json，回傳 saved_to。"""
    try:
        return chunk_service.save_chunk(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
