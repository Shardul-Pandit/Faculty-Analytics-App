"""
engine/mapping.py
-----------------
Auto-detection of which CSV column corresponds to each logical field,
plus fingerprinting for saved-mapping reuse.
"""

import hashlib
import json
from typing import Dict, List, Optional

# Canonical logical field names the rest of the app works with
LOGICAL_FIELDS = [
    "student_name",
    "major",
    "grade",
    "term",
    "gender",
    "year",
    "student_id",
]

# Keyword sets for each field — first keyword that matches wins
_FIELD_KEYWORDS: Dict[str, List[str]] = {
    "student_name": ["studentname", "student_name", "name", "fullname", "full_name", "student"],
    "major":        ["major", "program", "department", "dept", "field", "concentration", "discipline"],
    "grade":        ["assignmentgrade", "assignment_grade", "grade", "score", "points", "mark", "percent", "result", "finalgrade", "final_grade"],
    "term":         ["semester", "term", "session", "period", "semesterterm", "semester_term", "semname"],
    "gender":       ["gender", "sex"],
    "year":         ["year", "classstanding", "class_standing", "standing", "level", "yearlevel", "classlevel"],
    "student_id":   ["studentid", "student_id", "id", "sid", "number", "studentnumber"],
}


def auto_detect_mapping(columns: List[str]) -> Dict[str, Optional[str]]:
    """
    Try to match each logical field to the best actual column name.
    Returns { logical_name: actual_column | None }.
    """
    # Build a lookup: normalised_column_name -> original_column_name
    normalised: Dict[str, str] = {
        col.lower().replace(" ", "").replace("_", ""): col
        for col in columns
    }

    mapping: Dict[str, Optional[str]] = {field: None for field in LOGICAL_FIELDS}

    for field, keywords in _FIELD_KEYWORDS.items():
        for kw in keywords:
            clean_kw = kw.replace("_", "")
            if clean_kw in normalised:
                mapping[field] = normalised[clean_kw]
                break

    return mapping


def columns_fingerprint(columns: List[str]) -> str:
    """
    Produce a short stable hash from a set of column names.
    Used to look up previously saved mappings for the same schema.
    """
    sorted_cols = sorted(c.strip().lower() for c in columns)
    key = json.dumps(sorted_cols)
    return hashlib.sha256(key.encode()).hexdigest()[:16]
