"""
engine/data_quality.py
-----------------------
Lightweight data quality checks on normalized DataFrames.

Returns a list of note dicts:
  [{"level": "warning" | "ok", "message": "..."}]

Checks performed:
  - missing grade values
  - grade values outside 0–100
  - missing student names
  - duplicate student names
  - missing major values
  - majors with fewer than 5 students (small group warning)

If no problems are found a single "ok" entry is returned so the frontend
always has something to display.
"""

from typing import Any, Dict, List, Optional

import pandas as pd


def check_data_quality(
    df_a: pd.DataFrame,
    df_b: Optional[pd.DataFrame],
    mapping: Dict[str, Optional[str]],
) -> List[Dict[str, Any]]:
    """
    Run data quality checks on one or two normalised DataFrames.
    Returns a list of note dicts, each with "level" and "message".
    """
    notes: List[Dict[str, Any]] = []

    datasets = [("Dataset 1", df_a)]
    if df_b is not None:
        datasets.append(("Dataset 2", df_b))

    for label, df in datasets:
        _check_df(df, label, mapping, notes)

    if not notes:
        notes.append({
            "level":   "ok",
            "message": "No major data quality issues found.",
        })

    return notes


def _check_df(
    df: pd.DataFrame,
    label: str,
    mapping: Dict[str, Optional[str]],
    notes: List[Dict[str, Any]],
) -> None:
    n_rows = len(df)
    if n_rows == 0:
        notes.append({
            "level":   "warning",
            "message": f"{label}: file appears to be empty.",
        })
        return

    grade_col = mapping.get("grade")
    name_col  = mapping.get("student_name")
    major_col = mapping.get("major")

    # ── Grades ────────────────────────────────────────────────────────────────
    if grade_col and grade_col in df.columns:
        n_missing = int(df[grade_col].isna().sum())
        if n_missing:
            pct = round(n_missing / n_rows * 100, 1)
            notes.append({
                "level":   "warning",
                "message": (
                    f"{label}: {n_missing} student record"
                    f"{'s' if n_missing > 1 else ''} ({pct}%) "
                    f"{'have' if n_missing > 1 else 'has'} no grade value."
                ),
            })

        numeric_grades = pd.to_numeric(df[grade_col], errors="coerce").dropna()
        out_of_range = int(((numeric_grades < 0) | (numeric_grades > 100)).sum())
        if out_of_range:
            notes.append({
                "level":   "warning",
                "message": (
                    f"{label}: {out_of_range} grade value"
                    f"{'s are' if out_of_range > 1 else ' is'} outside the 0–100 range."
                ),
            })

    # ── Student names ─────────────────────────────────────────────────────────
    if name_col and name_col in df.columns:
        name_series = df[name_col].astype(str).str.strip()
        n_missing_names = int(df[name_col].isna().sum()) + int((name_series == "").sum())
        if n_missing_names:
            notes.append({
                "level":   "warning",
                "message": (
                    f"{label}: {n_missing_names} record"
                    f"{'s are' if n_missing_names > 1 else ' is'} missing a student name."
                ),
            })

        n_dupes = int(df[name_col].dropna().duplicated().sum())
        if n_dupes:
            notes.append({
                "level":   "warning",
                "message": (
                    f"{label}: {n_dupes} duplicate student name"
                    f"{'s were' if n_dupes > 1 else ' was'} found — "
                    "this may affect student-level analysis."
                ),
            })

    # ── Majors ────────────────────────────────────────────────────────────────
    if major_col and major_col in df.columns:
        major_series = df[major_col].astype(str).str.strip()
        n_missing_major = int(df[major_col].isna().sum()) + int((major_series == "").sum())
        if n_missing_major:
            pct = round(n_missing_major / n_rows * 100, 1)
            notes.append({
                "level":   "warning",
                "message": (
                    f"{label}: {n_missing_major} record"
                    f"{'s' if n_missing_major > 1 else ''} ({pct}%) "
                    f"{'are' if n_missing_major > 1 else 'is'} missing a major."
                ),
            })

        group_sizes = df[major_col].value_counts()
        small_groups = group_sizes[group_sizes < 5]
        if not small_groups.empty:
            names = ", ".join(str(n) for n in small_groups.index[:3])
            suffix = "…" if len(small_groups) > 3 else ""
            notes.append({
                "level":   "warning",
                "message": (
                    f"{label}: Some majors have fewer than 5 students "
                    f"({names}{suffix}). "
                    "Group comparisons for these may not be reliable."
                ),
            })
