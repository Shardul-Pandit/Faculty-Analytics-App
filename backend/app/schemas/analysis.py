from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class AnalysisQuery(BaseModel):
    question: str
    file_ids: List[int]                      # 1 or 2 file IDs
    mapping: Dict[str, Optional[str]]        # confirmed column mapping
    export: bool = True                      # generate Excel export automatically


class ChartData(BaseModel):
    title: str
    image_b64: str                           # base64-encoded PNG


class TableData(BaseModel):
    title: str
    rows: List[Dict[str, Any]]


class StatTest(BaseModel):
    test: str
    comparison: Optional[str] = None
    details: Dict[str, Any]


class AnalysisResult(BaseModel):
    summary: str                             # plain-English NL summary from LLM
    # Data quality warnings / all-clear note
    data_quality_notes: Optional[List[Dict[str, Any]]] = None
    tables: Optional[List[TableData]] = None
    charts: Optional[List[ChartData]] = None
    stat_tests: Optional[List[Dict[str, Any]]] = None
    export_session_id: Optional[str] = None  # used to download the Excel file
    raw_intent: Optional[Dict[str, Any]] = None
    # Pre-extracted metric cards for major-vs-major comparison UI
    comparison_cards: Optional[List[Dict[str, Any]]] = None
