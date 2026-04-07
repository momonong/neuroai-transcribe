"""
GET /api/export/{case_name}/{dataset_type}
"""
import io
import json
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
from deps import assert_user_can_access_case, get_current_user
from models import User
from shared.file_manager import file_manager

router = APIRouter(prefix="/api", tags=["export"])

SUFFIX_MAP = {
    "whisper": "_whisper.json",
    "diar": "_diar.json",
    "aligned": "_aligned.json",
    "stitched": "_stitched.json",
    "flagged": "_flagged_for_human.json",
    "edited": "_edited.json",
}


@router.get("/export/{case_name}/{dataset_type}")
async def export_dataset(
    case_name: str,
    dataset_type: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assert_user_can_access_case(db, user, case_name)
    suffix = SUFFIX_MAP.get(dataset_type)
    if not suffix:
        raise HTTPException(status_code=400, detail="Unknown dataset type")

    merged_data = file_manager.merge_chunks(case_name, suffix)
    if not merged_data:
        raise HTTPException(status_code=404, detail=f"No data found for {dataset_type}")

    json_str = json.dumps(merged_data, ensure_ascii=False, indent=2)
    filename = f"{case_name}_FULL_{dataset_type}.json"
    encoded_filename = urllib.parse.quote(filename)

    return StreamingResponse(
        io.BytesIO(json_str.encode("utf-8")),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )
