import shutil
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import get_db
from ..engine.io import get_columns, load_csv
from ..engine.mapping import auto_detect_mapping, columns_fingerprint
from ..models.file_record import FileRecord
from ..models.user import User
from ..schemas.file import FileRecord as FileRecordSchema
from ..schemas.file import FileUploadResponse, FileTermUpdate
from ..services.auth_service import get_current_user

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/upload", response_model=FileUploadResponse, status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    term_label: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Accept a CSV upload, save it to disk, and record metadata.
    Returns the detected columns so the frontend can show the mapping UI.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported right now.")

    # Store with a UUID prefix so filenames never collide
    unique_name = f"{uuid.uuid4().hex}_{file.filename}"
    dest = settings.uploads_dir / unique_name
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)

    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    df = load_csv(dest)
    columns   = list(df.columns)
    row_count = len(df)

    record = FileRecord(
        user_id           = current_user.id,
        original_filename = file.filename,
        stored_filename   = unique_name,
        term_label        = term_label,
        detected_columns  = columns,
        row_count         = row_count,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return FileUploadResponse(
        file_id           = record.id,
        original_filename = file.filename,
        detected_columns  = columns,
        row_count         = row_count,
        term_label        = term_label,
    )


@router.get("/list", response_model=List[FileRecordSchema])
def list_files(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return all files uploaded by the current user."""
    return (
        db.query(FileRecord)
        .filter(FileRecord.user_id == current_user.id)
        .order_by(FileRecord.upload_time.desc())
        .all()
    )


@router.patch("/{file_id}/term", response_model=FileRecordSchema)
def update_term_label(
    file_id: int,
    payload: FileTermUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Allow faculty to assign or update the term label for a file."""
    record = _get_own_record(db, file_id, current_user.id)
    record.term_label = payload.term_label
    db.commit()
    db.refresh(record)
    return record


@router.delete("/{file_id}", status_code=204)
def delete_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a file record and remove it from disk."""
    record = _get_own_record(db, file_id, current_user.id)

    stored = settings.uploads_dir / record.stored_filename
    if stored.exists():
        stored.unlink()

    db.delete(record)
    db.commit()


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _get_own_record(db: Session, file_id: int, user_id: int) -> FileRecord:
    record = db.query(FileRecord).filter(
        FileRecord.id      == file_id,
        FileRecord.user_id == user_id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    return record
