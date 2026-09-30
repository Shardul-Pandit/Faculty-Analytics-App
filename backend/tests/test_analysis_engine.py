"""Unit tests for engine/analysis.py: the statistics behind every answer."""

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from app.engine.analysis import (
    compare_two_datasets,
    compare_two_majors,
    grade_bands,
    grade_changes,
    one_way_anova,
    overall_summary_one_file,
    rank_majors,
    rank_students,
    slo_distribution,
    summary_stats,
    welch_ttest,
)
from app.engine.io import normalize_dataframe


def frame(rows, mapping=None):
    """Build a normalised DataFrame from (name, major, grade) tuples."""
    df = pd.DataFrame(rows, columns=["student_name", "major", "grade"])
    return normalize_dataframe(df, mapping or {}, "T1")


# ---------------------------------------------------------------------------
# Descriptive statistics
# ---------------------------------------------------------------------------

def test_summary_stats_matches_hand_computed_values():
    s = summary_stats(frame([("a", "X", 70), ("b", "X", 80), ("c", "X", 90)]))
    assert s["N"] == 3
    assert s["Mean"] == 80.0
    assert s["SD"] == 10.0          # sample SD (ddof=1) of 70, 80, 90
    assert s["Median"] == 80.0
    assert (s["Min"], s["Max"]) == (70.0, 90.0)


def test_summary_stats_slo_percentages():
    # 65 -> Not Meet, 75 -> Nearly Meet, 85 -> Meet, 95 -> Exceed
    s = summary_stats(frame([("a", "X", 65), ("b", "X", 75), ("c", "X", 85), ("d", "X", 95)]))
    assert s["% Meet+Exceed"] == 50.0
    assert s["% Not Meet"] == 25.0


def test_summary_stats_single_value_has_zero_sd():
    assert summary_stats(frame([("a", "X", 88)]))["SD"] == 0.0


def test_summary_stats_ignores_missing_grades():
    s = summary_stats(frame([("a", "X", 70), ("b", "X", None), ("c", "X", 90)]))
    assert s["N"] == 2
    assert s["Mean"] == 80.0


# ---------------------------------------------------------------------------
# Statistical tests (checked against SciPy directly)
# ---------------------------------------------------------------------------

def test_welch_ttest_matches_scipy():
    a = pd.Series([70, 75, 80, 85, 90])
    b = pd.Series([60, 62, 65, 70, 71, 73])
    t, p = stats.ttest_ind(a, b, equal_var=False)
    r = welch_ttest(a, b, "A", "B")
    assert r["t_statistic"] == round(float(t), 4)
    assert r["p_value"] == round(float(p), 4)
    assert r["significant"] is bool(p < 0.05)
    assert (r["n_a"], r["n_b"]) == (5, 6)
    assert r["comparison"] == "A vs B"


def test_welch_ttest_identical_groups_not_significant():
    s = pd.Series([70.0, 80.0, 90.0])
    assert welch_ttest(s, s, "A", "B")["significant"] is False


def test_welch_ttest_reports_insufficient_data():
    r = welch_ttest(pd.Series([70.0]), pd.Series([80.0, 90.0]), "A", "B")
    assert "error" in r
    assert "p_value" not in r


def test_one_way_anova_matches_scipy():
    groups = {
        "X": pd.Series([70, 72, 74, 76]),
        "Y": pd.Series([80, 82, 84, 86]),
        "Z": pd.Series([60, 65, 70, 75]),
    }
    f, p = stats.f_oneway(*groups.values())
    r = one_way_anova(groups)
    assert r["F_statistic"] == round(float(f), 4)
    assert r["p_value"] == round(float(p), 4)
    assert r["group_ns"] == {"X": 4, "Y": 4, "Z": 4}


def test_one_way_anova_skips_groups_too_small_to_test():
    r = one_way_anova({"X": pd.Series([70, 80]), "Y": pd.Series([90]), "Z": pd.Series([60, 65])})
    assert r["groups"] == ["X", "Z"]


def test_one_way_anova_needs_two_groups():
    assert "error" in one_way_anova({"X": pd.Series([70, 80, 90])})


# ---------------------------------------------------------------------------
# SLO attainment
# ---------------------------------------------------------------------------

def test_slo_distribution_overall():
    d = slo_distribution(frame([("a", "X", 65), ("b", "X", 66), ("c", "X", 85), ("d", "X", 95)]))
    assert d["counts"] == {"Not Meet": 2, "Nearly Meet": 0, "Meet": 1, "Exceed": 1}
    assert d["percentages"]["Not Meet"] == 50.0


def test_slo_distribution_by_group_fills_missing_levels():
    d = slo_distribution(frame([("a", "X", 95), ("b", "Y", 65)]), group_col="major")
    x = next(r for r in d["counts"] if r["major"] == "X")
    assert x == {"major": "X", "Not Meet": 0, "Nearly Meet": 0, "Meet": 0, "Exceed": 1}


def test_slo_distribution_without_grades_is_empty():
    assert slo_distribution(pd.DataFrame({"major": ["X"]})) == {}


# ---------------------------------------------------------------------------
# Grade bands
# ---------------------------------------------------------------------------

def test_grade_band_boundaries():
    grades = [90, 89.99, 80, 79.99, 70, 69.99]
    b = grade_bands(frame([(str(i), "X", g) for i, g in enumerate(grades)]))
    assert b["counts"] == {"A (90+)": 1, "B (80–89)": 2, "C (70–79)": 2, "D/F (<70)": 1}
    assert b["total"] == 6


def test_grade_band_percentages_sum_to_100():
    rng = np.random.default_rng(0)
    b = grade_bands(frame([(str(i), "X", g) for i, g in enumerate(rng.uniform(40, 100, 200))]))
    assert sum(b["percentages"].values()) == pytest.approx(100, abs=0.2)


def test_grade_bands_without_grade_column_is_empty():
    assert grade_bands(pd.DataFrame({"major": ["X"]})) == {}


# ---------------------------------------------------------------------------
# Rankings and grade changes
# ---------------------------------------------------------------------------

def test_rank_majors_orders_by_mean():
    df = frame([("a", "X", 70), ("b", "Y", 90), ("c", "Z", 80), ("d", "Y", 80)])
    assert [r["major"] for r in rank_majors(df)] == ["Y", "Z", "X"]
    assert [r["major"] for r in rank_majors(df, ascending=True)] == ["X", "Z", "Y"]
    assert rank_majors(df)[0] == {"Rank": 1, "major": "Y", "Mean": 85.0, "N": 2}


def test_rank_students_top_n_and_order():
    df = frame([("a", "X", 70), ("b", "X", 95), ("c", "Y", 85), ("d", "Y", None)])
    top = rank_students(df, top_n=2)
    assert [r["Student Name"] for r in top] == ["b", "c"]
    assert top[0]["Rank"] == 1 and top[0]["Grade"] == 95.0


def test_rank_students_needs_a_name_column():
    assert rank_students(pd.DataFrame({"grade": [80.0]})) == []


def test_grade_changes_improvers_and_column_order():
    before = frame([("a", "X", 60), ("b", "X", 70), ("c", "Y", 80)])
    after = frame([("a", "X", 75), ("b", "X", 72), ("c", "Y", 79)])
    rows = grade_changes(before, after)
    assert [r["Student Name"] for r in rows] == ["a", "b", "c"]
    assert rows[0]["Change"] == 15.0
    assert list(rows[0]) == ["Rank", "Student Name", "Major", "Grade Before", "Grade After", "Change"]


def test_grade_changes_declines_first_when_ascending():
    before = frame([("a", "X", 60), ("b", "X", 70), ("c", "Y", 80)])
    after = frame([("a", "X", 75), ("b", "X", 72), ("c", "Y", 79)])
    assert grade_changes(before, after, ascending=True)[0]["Student Name"] == "c"


def test_grade_changes_only_matches_students_in_both_files():
    before = frame([("a", "X", 60), ("only_before", "X", 50)])
    after = frame([("a", "X", 65), ("only_after", "X", 99)])
    assert [r["Student Name"] for r in grade_changes(before, after)] == ["a"]


def test_grade_changes_with_no_overlap_is_empty():
    assert grade_changes(frame([("a", "X", 60)]), frame([("b", "X", 70)])) == []


# ---------------------------------------------------------------------------
# Composite analyses
# ---------------------------------------------------------------------------

def test_overall_summary_includes_major_breakdown():
    df = frame([("a", "X", 70), ("b", "X", 75), ("c", "Y", 85), ("d", "Y", 90)])
    r = overall_summary_one_file(df)
    assert {"overall", "by_major", "rankings", "slo_distribution", "anova"} <= r.keys()


def test_compare_two_datasets_runs_overall_and_per_major_tests():
    a = frame([("a", "X", 60), ("b", "X", 65), ("c", "Y", 70), ("d", "Y", 72)])
    b = frame([("a", "X", 80), ("b", "X", 85), ("c", "Y", 75), ("d", "Y", 78)])
    r = compare_two_datasets(a, b, "Before", "After")
    assert r["ttest_overall"]["comparison"] == "Before vs After"
    assert len(r["per_major_tests"]) == 2
    assert set(r["overall_stats"]) == {"Before", "After"}


def test_compare_two_majors():
    df = frame([("a", "X", 70), ("b", "X", 80), ("c", "Y", 85), ("d", "Y", 95)])
    r = compare_two_majors(df, "X", "Y")
    assert r["stats_a"]["Mean"] == 75.0 and r["stats_b"]["Mean"] == 90.0
    assert r["ttest"]["comparison"] == "X vs Y"


# ---------------------------------------------------------------------------
# Regression tests on the bundled sample data (the numbers in the README)
# ---------------------------------------------------------------------------

def test_sample_data_cs_vs_biology(before_df, after_df):
    combined = pd.concat([before_df, after_df], ignore_index=True)
    r = compare_two_majors(combined, "Computer Science", "Biology")
    assert r["stats_a"]["Mean"] == 79.17
    assert r["stats_b"]["Mean"] == 76.89
    assert r["ttest"]["p_value"] == 0.3362
    assert r["ttest"]["significant"] is False


def test_sample_data_grade_bands(before_df, after_df):
    b = grade_bands(pd.concat([before_df, after_df], ignore_index=True))
    assert b["total"] == 115
    assert list(b["counts"].values()) == [10, 32, 46, 27]


def test_sample_data_top_improver(before_df, after_df):
    top = grade_changes(before_df, after_df)[0]
    assert (top["Student Name"], top["Change"]) == ("Student 031", 17.4)
