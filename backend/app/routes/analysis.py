from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import get_db
from ..models.file_record import FileRecord
from ..models.user import User
from ..schemas.analysis import AnalysisQuery, AnalysisResult
from ..services.auth_service import get_current_user
from ..services.analysis_service import run_analysis

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("/query", response_model=AnalysisResult)
async def query(
    payload: AnalysisQuery,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Main analytics endpoint.
    Accepts 1 or 2 file IDs, a confirmed column mapping, and a natural-language question.
    Returns charts, tables, stat-test results, and a plain-English summary.
    """
    if not payload.file_ids or len(payload.file_ids) > 2:
        raise HTTPException(status_code=400, detail="Provide 1 or 2 file IDs")

    records = []
    for fid in payload.file_ids:
        rec = db.query(FileRecord).filter(
            FileRecord.id      == fid,
            FileRecord.user_id == current_user.id,
        ).first()
        if not rec:
            raise HTTPException(status_code=404, detail=f"File {fid} not found")
        records.append(rec)

    return await run_analysis(
        question   = payload.question,
        file_ids   = payload.file_ids,
        mapping    = payload.mapping,
        records    = records,
        do_export  = payload.export,
    )


@router.get("/export/{session_id}")
def download_excel(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """Download the Excel workbook generated for a previous query."""
    path = settings.outputs_dir / f"{session_id}.xlsx"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Export not found or has expired")
    return FileResponse(
        path        = str(path),
        media_type  = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename    = "analytics_export.xlsx",
    )
