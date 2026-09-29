"""
engine/io.py
------------
Handles loading CSV files and normalising DataFrames to a consistent
internal schema using user-confirmed column mappings.

Internal standard column names used throughout the engine:
  student_name, major, grade, term, gender, year, student_id
"""

from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd


# ---------------------------------------------------------------------------
# SLO thresholds (kept identical to original student_assessment.py)
# ---------------------------------------------------------------------------

def slo_level(score: float) -> str:
    """Map a numeric grade to an SLO attainment category."""
    if score < 70:
        return "Not Meet"
    elif score < 80:
        return "Nearly Meet"
    elif score < 90:
        return "Meet"
    else:
        return "Exceed"


# ---------------------------------------------------------------------------
# File loading
# ---------------------------------------------------------------------------

def load_csv(filepath: Path) -> pd.DataFrame:
    """Read a CSV from disk into a DataFrame."""
    return pd.read_csv(filepath)


def get_columns(filepath: Path) -> List[str]:
    """Return column names without loading all rows."""
    return list(pd.read_csv(filepath, nrows=0).columns)


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def normalize_dataframe(
    df: pd.DataFrame,
    mapping: Dict[str, Optional[str]],
    term_label: Optional[str] = None,
) -> pd.DataFrame:
    """
    Rename columns to standard internal names using the confirmed mapping dict.

    mapping format: { "major": "Department", "grade": "Score", ... }
    Any logical key whose value is None (unmapped) is left as-is.

    After renaming:
    - If no 'term' column exists, inject term_label (or 'Unknown').
    - If 'grade' column exists, compute 'slo_level'.
    """
    rename_map: Dict[str, str] = {}
    for standard_name, actual_col in mapping.items():
        if actual_col and actual_col in df.columns:
            rename_map[actual_col] = standard_name

    df = df.rename(columns=rename_map).copy()

    if "term" not in df.columns:
        df["term"] = term_label or "Unknown"

    if "grade" in df.columns:
        df["grade"] = pd.to_numeric(df["grade"], errors="coerce")
        df["slo_level"] = df["grade"].apply(
            lambda x: slo_level(x) if pd.notna(x) else "Unknown"
        )

    return df
