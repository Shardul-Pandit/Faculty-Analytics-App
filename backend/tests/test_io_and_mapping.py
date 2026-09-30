"""Unit tests for CSV loading/normalisation (engine/io.py) and column auto-mapping (engine/mapping.py)."""

import pandas as pd
import pytest

from app.engine.io import get_columns, load_csv, normalize_dataframe, slo_level
from app.engine.mapping import LOGICAL_FIELDS, auto_detect_mapping, columns_fingerprint


# ---------------------------------------------------------------------------
# SLO thresholds
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("score, level", [
    (0, "Not Meet"),
    (69.99, "Not Meet"),
    (70, "Nearly Meet"),
    (79.99, "Nearly Meet"),
    (80, "Meet"),
    (89.99, "Meet"),
    (90, "Exceed"),
    (100, "Exceed"),
])
def test_slo_level_thresholds(score, level):
    assert slo_level(score) == level


# ---------------------------------------------------------------------------
# Loading and normalising
# ---------------------------------------------------------------------------

def test_load_csv_and_get_columns(tmp_path):
    path = tmp_path / "grades.csv"
    path.write_text("Name,Dept,Score\nA,Bio,88\nB,CS,72\n")
    assert get_columns(path) == ["Name", "Dept", "Score"]
    assert len(load_csv(path)) == 2


def test_normalize_renames_mapped_columns_and_adds_slo():
    raw = pd.DataFrame({"Name": ["A"], "Dept": ["Bio"], "Score": [88]})
    df = normalize_dataframe(raw, {"student_name": "Name", "major": "Dept", "grade": "Score"})
    assert {"student_name", "major", "grade", "slo_level"} <= set(df.columns)
    assert df.loc[0, "slo_level"] == "Meet"


def test_normalize_injects_term_label_when_file_has_no_term():
    df = normalize_dataframe(pd.DataFrame({"Score": [80]}), {"grade": "Score"}, "FA24")
    assert df.loc[0, "term"] == "FA24"


def test_normalize_uses_unknown_term_without_label():
    df = normalize_dataframe(pd.DataFrame({"Score": [80]}), {"grade": "Score"})
    assert df.loc[0, "term"] == "Unknown"


def test_normalize_keeps_existing_term_column():
    raw = pd.DataFrame({"Sem": ["SP25"], "Score": [80]})
    df = normalize_dataframe(raw, {"term": "Sem", "grade": "Score"}, "ignored")
    assert df.loc[0, "term"] == "SP25"


def test_normalize_coerces_non_numeric_grades():
    df = normalize_dataframe(pd.DataFrame({"Score": ["85", "absent"]}), {"grade": "Score"})
    assert df.loc[0, "grade"] == 85
    assert pd.isna(df.loc[1, "grade"])
    assert df.loc[1, "slo_level"] == "Unknown"


def test_normalize_ignores_unmapped_and_missing_columns():
    raw = pd.DataFrame({"Score": [80]})
    df = normalize_dataframe(raw, {"grade": "Score", "major": None, "gender": "NotInFile"})
    assert "major" not in df.columns and "gender" not in df.columns


def test_normalize_does_not_mutate_input():
    raw = pd.DataFrame({"Score": [80]})
    normalize_dataframe(raw, {"grade": "Score"})
    assert list(raw.columns) == ["Score"]


# ---------------------------------------------------------------------------
# Column auto-detection
# ---------------------------------------------------------------------------

def test_auto_detect_on_sample_schema():
    m = auto_detect_mapping(["StudentName", "Major", "Year", "Gender", "AssignmentGrade"])
    assert m == {
        "student_name": "StudentName",
        "major": "Major",
        "grade": "AssignmentGrade",
        "term": None,
        "gender": "Gender",
        "year": "Year",
        "student_id": None,
    }


def test_auto_detect_is_case_space_and_underscore_insensitive():
    m = auto_detect_mapping(["Student Name", "FINAL_GRADE", "semester"])
    assert m["student_name"] == "Student Name"
    assert m["grade"] == "FINAL_GRADE"
    assert m["term"] == "semester"


@pytest.mark.parametrize("column, field", [
    ("Department", "major"),
    ("Program", "major"),
    ("Score", "grade"),
    ("Points", "grade"),
    ("Session", "term"),
    ("Sex", "gender"),
    ("Class Standing", "year"),
    ("SID", "student_id"),
])
def test_auto_detect_synonyms(column, field):
    assert auto_detect_mapping([column])[field] == column


def test_auto_detect_always_returns_every_field():
    m = auto_detect_mapping(["Unrelated", "Columns"])
    assert set(m) == set(LOGICAL_FIELDS)
    assert all(v is None for v in m.values())


# ---------------------------------------------------------------------------
# Fingerprints for saved-mapping reuse
# ---------------------------------------------------------------------------

def test_fingerprint_ignores_order_case_and_whitespace():
    assert columns_fingerprint(["Name", "Score"]) == columns_fingerprint([" score", "NAME "])


def test_fingerprint_differs_for_different_schemas():
    assert columns_fingerprint(["Name", "Score"]) != columns_fingerprint(["Name", "Grade"])


def test_fingerprint_is_short_and_stable():
    fp = columns_fingerprint(["Name", "Score"])
    assert len(fp) == 16
    assert fp == columns_fingerprint(["Name", "Score"])
