"""Unit tests for engine/data_quality.py: the warnings shown above every result."""

import pandas as pd

from app.engine.data_quality import check_data_quality

MAPPING = {"student_name": "Name", "major": "Major", "grade": "Grade"}


def clean_df(n_per_major=5):
    rows = []
    for major in ("Bio", "CS"):
        for i in range(n_per_major):
            rows.append({"Name": f"{major}-{i}", "Major": major, "Grade": 70 + i})
    return pd.DataFrame(rows)


def messages(notes):
    return " | ".join(n["message"] for n in notes)


def test_clean_data_returns_single_ok_note():
    notes = check_data_quality(clean_df(), None, MAPPING)
    assert notes == [{"level": "ok", "message": "No major data quality issues found."}]


def test_empty_file_is_flagged():
    notes = check_data_quality(pd.DataFrame(columns=["Name", "Major", "Grade"]), None, MAPPING)
    assert "file appears to be empty" in messages(notes)


def test_missing_grades_counted_with_percentage():
    df = clean_df()
    df.loc[0:1, "Grade"] = None
    assert "2 student records (20.0%) have no grade value" in messages(check_data_quality(df, None, MAPPING))


def test_out_of_range_grades_flagged():
    df = clean_df()
    df.loc[0, "Grade"] = 105
    df.loc[1, "Grade"] = -3
    assert "2 grade values are outside the 0–100 range" in messages(check_data_quality(df, None, MAPPING))


def test_duplicate_names_flagged():
    df = clean_df()
    df.loc[1, "Name"] = df.loc[0, "Name"]
    assert "1 duplicate student name was found" in messages(check_data_quality(df, None, MAPPING))


def test_missing_names_flagged():
    df = clean_df()
    df.loc[0, "Name"] = None
    assert "1 record is missing a student name" in messages(check_data_quality(df, None, MAPPING))


def test_small_major_groups_flagged():
    df = pd.concat([clean_df(), pd.DataFrame([{"Name": "x", "Major": "Art", "Grade": 80}])])
    msg = messages(check_data_quality(df, None, MAPPING))
    assert "fewer than 5 students (Art)" in msg


def test_second_dataset_is_labelled_separately():
    bad = clean_df()
    bad.loc[0, "Grade"] = 150
    msg = messages(check_data_quality(clean_df(), bad, MAPPING))
    assert msg.startswith("Dataset 2:")
    assert "Dataset 1" not in msg
