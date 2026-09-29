from typing import Dict, List, Optional
from pydantic import BaseModel


class MappingIn(BaseModel):
    columns_fingerprint: str
    # Keys are logical names (major, grade, term, …); values are actual CSV column names
    mapping: Dict[str, Optional[str]]


class MappingOut(BaseModel):
    id: int
    columns_fingerprint: str
    mapping: Dict[str, Optional[str]]

    model_config = {"from_attributes": True}


class MappingSuggestion(BaseModel):
    """Returned by /mappings/suggest — auto-detected guesses for the user to confirm."""
    columns: List[str]
    suggestions: Dict[str, Optional[str]]
    fingerprint: str
