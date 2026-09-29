from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..engine.mapping import auto_detect_mapping, columns_fingerprint
from ..models.mapping import ColumnMapping
from ..models.user import User
from ..schemas.mapping import MappingIn, MappingOut, MappingSuggestion
from ..services.auth_service import get_current_user

router = APIRouter(prefix="/mappings", tags=["mappings"])


class SuggestRequest(BaseModel):
    columns: List[str]


@router.post("/suggest", response_model=MappingSuggestion)
def suggest_mapping(
    payload: SuggestRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Given a list of column names, return auto-detected guesses
    plus the fingerprint to use when saving.
    """
    fingerprint = columns_fingerprint(payload.columns)
    suggestions = auto_detect_mapping(payload.columns)
    return MappingSuggestion(
        columns     = payload.columns,
        suggestions = suggestions,
        fingerprint = fingerprint,
    )


@router.get("/saved/{fingerprint}", response_model=MappingOut)
def get_saved_mapping(
    fingerprint: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return a previously saved mapping for these columns, if one exists."""
    mapping = db.query(ColumnMapping).filter(
        ColumnMapping.user_id              == current_user.id,
        ColumnMapping.columns_fingerprint  == fingerprint,
    ).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="No saved mapping for these columns")
    return mapping


@router.post("/save", response_model=MappingOut)
def save_mapping(
    payload: MappingIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upsert a column mapping for the current user.
    If one already exists for this fingerprint it is updated.
    """
    existing = db.query(ColumnMapping).filter(
        ColumnMapping.user_id             == current_user.id,
        ColumnMapping.columns_fingerprint == payload.columns_fingerprint,
    ).first()

    if existing:
        existing.mapping = payload.mapping
        db.commit()
        db.refresh(existing)
        return existing

    new_mapping = ColumnMapping(
        user_id              = current_user.id,
        columns_fingerprint  = payload.columns_fingerprint,
        mapping              = payload.mapping,
    )
    db.add(new_mapping)
    db.commit()
    db.refresh(new_mapping)
    return new_mapping
