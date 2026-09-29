"""
engine/analysis.py
------------------
All statistical analysis functions.  Refactored from student_assessment.py.

Rules:
- All computation happens here in Python — the LLM never performs calculations.
- Functions accept normalised DataFrames (produced by engine/io.py).
- Results are plain dicts / lists of dicts so they serialise cleanly to JSON.
"""

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats

SLO_ORDER = ["Not Meet", "Nearly Meet", "Meet", "Exceed"]


# ---------------------------------------------------------------------------
# Basic descriptive statistics
# ---------------------------------------------------------------------------

def summary_stats(df: pd.DataFrame, grade_col: str = "grade") -> Dict[str, Any]:
    """Descriptive stats for one group."""
    g = df[grade_col].dropna()
    result: Dict[str, Any] = {
        "N":      int(g.count()),
        "Mean":   round(float(g.mean()), 2),
        "SD":     round(float(g.std(ddof=1)), 2) if len(g) > 1 else 0.0,
        "Median": round(float(g.median()), 2),
        "Min":    round(float(g.min()), 2),
        "Max":    round(float(g.max()), 2),
    }
    if "slo_level" in df.columns:
        slo = df["slo_level"]
        result["% Meet+Exceed"] = round(float(slo.isin(["Meet", "Exceed"]).mean() * 100), 1)
        result["% Not Meet"]    = round(float(slo.eq("Not Meet").mean() * 100), 1)
    return result


def summary_by_group(
    df: pd.DataFrame,
    group_col: str,
    grade_col: str = "grade",
) -> List[Dict[str, Any]]:
    """Summary stats for every value of group_col (e.g. major, term)."""
    rows = []
    for name, grp in df.groupby(group_col):
        row: Dict[str, Any] = {group_col: name}
        row.update(summary_stats(grp, grade_col))
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# SLO attainment distribution
# ---------------------------------------------------------------------------

def slo_distribution(
    df: pd.DataFrame,
    group_col: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Returns counts and percentages of students in each SLO category.
    If group_col is given (e.g. 'major'), returns breakdown per group.
    """
    if "slo_level" not in df.columns:
        return {}

    if group_col and group_col in df.columns:
        counts = (
            df.pivot_table(
                index=group_col,
                columns="slo_level",
                values="grade",
                aggfunc="count",
                fill_value=0,
            )
        )
        for col in SLO_ORDER:
            if col not in counts.columns:
                counts[col] = 0
        counts = counts[SLO_ORDER]
        total = counts.sum(axis=1)
        pct = (counts.div(total, axis=0) * 100).round(1)
        return {
            "counts":      counts.reset_index().to_dict(orient="records"),
            "percentages": pct.reset_index().to_dict(orient="records"),
        }
    else:
        counts = df["slo_level"].value_counts().reindex(SLO_ORDER, fill_value=0)
        total  = counts.sum()
        pct    = (counts / total * 100).round(1) if total > 0 else counts * 0
        return {
            "counts":      counts.to_dict(),
            "percentages": pct.to_dict(),
        }


# ---------------------------------------------------------------------------
# Statistical tests
# ---------------------------------------------------------------------------

def welch_ttest(
    group_a: pd.Series,
    group_b: pd.Series,
    label_a: str,
    label_b: str,
) -> Dict[str, Any]:
    """Welch (unequal-variance) independent t-test — mirrors the original script."""
    a = group_a.dropna()
    b = group_b.dropna()

    base = {
        "test":       "Welch t-test",
        "comparison": f"{label_a} vs {label_b}",
        "n_a":        int(len(a)),
        "n_b":        int(len(b)),
        "mean_a":     round(float(a.mean()), 2) if len(a) else None,
        "mean_b":     round(float(b.mean()), 2) if len(b) else None,
    }

    if len(a) < 2 or len(b) < 2:
        base["error"] = "Insufficient data (need ≥ 2 per group)"
        return base

    t, p = stats.ttest_ind(a, b, equal_var=False)
    base.update({
        "t_statistic": round(float(t), 4),
        "p_value":     round(float(p), 4),
        "significant": bool(p < 0.05),
    })
    return base


def one_way_anova(groups: Dict[str, pd.Series]) -> Dict[str, Any]:
    """One-way ANOVA across multiple groups — mirrors the original script."""
    clean = {k: v.dropna() for k, v in groups.items() if len(v.dropna()) >= 2}

    if len(clean) < 2:
        return {"test": "One-way ANOVA", "error": "Need ≥ 2 groups each with ≥ 2 observations"}

    f, p = stats.f_oneway(*clean.values())
    return {
        "test":         "One-way ANOVA",
        "groups":       list(clean.keys()),
        "group_ns":     {k: int(len(v)) for k, v in clean.items()},
        "group_means":  {k: round(float(v.mean()), 2) for k, v in clean.items()},
        "F_statistic":  round(float(f), 4),
        "p_value":      round(float(p), 4),
        "significant":  bool(p < 0.05),
    }


# ---------------------------------------------------------------------------
# Rankings
# ---------------------------------------------------------------------------

def rank_majors(
    df: pd.DataFrame,
    grade_col: str = "grade",
    top_n: int = 10,
    ascending: bool = False,
) -> List[Dict[str, Any]]:
    """Rank majors by mean grade (descending = best first)."""
    if "major" not in df.columns:
        return []

    ranked = (
        df.groupby("major")[grade_col]
        .agg(Mean="mean", N="count")
        .reset_index()
        .sort_values("Mean", ascending=ascending)
    )
    ranked["Mean"] = ranked["Mean"].round(2)
    ranked.insert(0, "Rank", range(1, len(ranked) + 1))
    return ranked.head(top_n).to_dict(orient="records")


def grade_bands(
    df: pd.DataFrame,
    grade_col: str = "grade",
) -> Dict[str, Any]:
    """
    Group students into letter-grade bands.
      A  : ≥ 90
      B  : 80–89
      C  : 70–79
      D/F: < 70
    Returns counts and percentages for each band.
    """
    if grade_col not in df.columns:
        return {}
    g = df[grade_col].dropna()
    counts: Dict[str, int] = {
        "A (90+)":    int((g >= 90).sum()),
        "B (80–89)":  int(((g >= 80) & (g < 90)).sum()),
        "C (70–79)":  int(((g >= 70) & (g < 80)).sum()),
        "D/F (<70)":  int((g < 70).sum()),
    }
    total = int(g.count())
    pct: Dict[str, float] = {
        k: round(v / total * 100, 1) if total > 0 else 0.0
        for k, v in counts.items()
    }
    return {"total": total, "counts": counts, "percentages": pct}


def grade_changes(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    grade_col: str = "grade",
    top_n: int = 5,
    ascending: bool = False,
) -> List[Dict[str, Any]]:
    """
    Match students by name across two files and compute grade change.
    ascending=False → biggest improvers first.
    ascending=True  → biggest declines first (most negative change first).
    Requires 'student_name' in both DataFrames.
    Returns empty list if no match is possible.
    """
    if "student_name" not in df_a.columns or "student_name" not in df_b.columns:
        return []
    if grade_col not in df_a.columns or grade_col not in df_b.columns:
        return []

    cols_a: List[str] = ["student_name", grade_col]
    if "major" in df_a.columns:
        cols_a.append("major")

    merged = pd.merge(
        df_a[cols_a].rename(columns={grade_col: "grade_before"}),
        df_b[["student_name", grade_col]].rename(columns={grade_col: "grade_after"}),
        on="student_name",
        how="inner",
    )
    if merged.empty:
        return []

    merged["Change"] = (merged["grade_after"] - merged["grade_before"]).round(2)
    # Fixed display order: identity columns first, then before -> after -> change
    order = ["student_name"] + (["major"] if "major" in merged.columns else []) + [
        "grade_before", "grade_after", "Change",
    ]
    merged = merged[order]
    merged = (
        merged
        .sort_values("Change", ascending=ascending)
        .head(top_n)
        .reset_index(drop=True)
    )
    merged.insert(0, "Rank", range(1, len(merged) + 1))

    rename: Dict[str, str] = {
        "student_name": "Student Name",
        "grade_before": "Grade Before",
        "grade_after":  "Grade After",
        "major":        "Major",
    }
    merged = merged.rename(columns=rename)
    for col in ("Grade Before", "Grade After"):
        if col in merged.columns:
            merged[col] = merged[col].round(2)

    return merged.to_dict(orient="records")


def rank_students(
    df: pd.DataFrame,
    grade_col: str = "grade",
    top_n: int = 5,
    ascending: bool = False,
) -> List[Dict[str, Any]]:
    """
    Rank individual students by grade.
    Requires a 'student_name' column (mapped during upload).
    Returns an empty list if the column is absent.
    """
    if grade_col not in df.columns or "student_name" not in df.columns:
        return []

    cols: List[str] = ["student_name"]
    if "major" in df.columns:
        cols.append("major")
    cols.append(grade_col)
    if "term" in df.columns:
        cols.append("term")
    if "slo_level" in df.columns:
        cols.append("slo_level")

    ranked = (
        df[cols]
        .dropna(subset=[grade_col])
        .sort_values(grade_col, ascending=ascending)
        .head(top_n)
        .reset_index(drop=True)
    )
    ranked.insert(0, "Rank", range(1, len(ranked) + 1))

    # Round grades and rename for clean display
    rename: Dict[str, str] = {
        "student_name": "Student Name",
        grade_col:      "Grade",
        "major":        "Major",
        "term":         "Term",
        "slo_level":    "SLO Level",
    }
    ranked = ranked.rename(columns=rename)
    if "Grade" in ranked.columns:
        ranked["Grade"] = ranked["Grade"].round(2)

    return ranked.to_dict(orient="records")


# ---------------------------------------------------------------------------
# High-level composite analyses
# ---------------------------------------------------------------------------

def overall_summary_one_file(
    df: pd.DataFrame,
    grade_col: str = "grade",
) -> Dict[str, Any]:
    """Complete one-file summary: stats, SLO, rankings, ANOVA."""
    result: Dict[str, Any] = {
        "overall": summary_stats(df, grade_col),
    }

    if "major" in df.columns:
        result["by_major"]  = summary_by_group(df, "major", grade_col)
        result["rankings"]  = rank_majors(df, grade_col)
        result["slo_distribution"] = slo_distribution(df, group_col="major")
        groups = {m: df.loc[df["major"] == m, grade_col] for m in df["major"].unique()}
        result["anova"] = one_way_anova(groups)
    else:
        result["slo_distribution"] = slo_distribution(df)

    return result


def compare_two_datasets(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    label_a: str,
    label_b: str,
    grade_col: str = "grade",
) -> Dict[str, Any]:
    """
    Full comparison between two uploaded files (e.g. Before vs After).
    Matches the structure of the original student_assessment.py comparisons.
    """
    result: Dict[str, Any] = {
        "label_a": label_a,
        "label_b": label_b,
        "overall_stats": {
            label_a: summary_stats(df_a, grade_col),
            label_b: summary_stats(df_b, grade_col),
        },
        "ttest_overall": welch_ttest(df_a[grade_col], df_b[grade_col], label_a, label_b),
        "slo_a": slo_distribution(df_a),
        "slo_b": slo_distribution(df_b),
    }

    # Per-major t-tests if both files have a major column
    if "major" in df_a.columns and "major" in df_b.columns:
        all_majors = sorted(set(df_a["major"].unique()) | set(df_b["major"].unique()))
        per_major: List[Dict[str, Any]] = []
        for major in all_majors:
            ga = df_a.loc[df_a["major"] == major, grade_col]
            gb = df_b.loc[df_b["major"] == major, grade_col]
            per_major.append(welch_ttest(ga, gb, f"{label_a} – {major}", f"{label_b} – {major}"))
        result["per_major_tests"] = per_major
        result["by_major_a"] = summary_by_group(df_a, "major", grade_col)
        result["by_major_b"] = summary_by_group(df_b, "major", grade_col)

        # ANOVA within each file
        result["anova_a"] = one_way_anova({
            m: df_a.loc[df_a["major"] == m, grade_col] for m in df_a["major"].unique()
        })
        result["anova_b"] = one_way_anova({
            m: df_b.loc[df_b["major"] == m, grade_col] for m in df_b["major"].unique()
        })

    return result


def compare_two_majors(
    df: pd.DataFrame,
    major_a: str,
    major_b: str,
    grade_col: str = "grade",
) -> Dict[str, Any]:
    """Compare two specific majors within a single (combined) dataset."""
    da = df.loc[df["major"] == major_a, grade_col]
    db = df.loc[df["major"] == major_b, grade_col]
    return {
        "ttest":   welch_ttest(da, db, major_a, major_b),
        "stats_a": summary_stats(df[df["major"] == major_a], grade_col),
        "stats_b": summary_stats(df[df["major"] == major_b], grade_col),
        "slo_a":   slo_distribution(df[df["major"] == major_a]),
        "slo_b":   slo_distribution(df[df["major"] == major_b]),
    }
