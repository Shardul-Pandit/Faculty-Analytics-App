"""
Unit tests for the rule-based parser and template summaries in
services/analysis_service.py: the last tier of the failover chain, used
whenever no LLM provider is configured or every provider has failed.
"""

import pytest

from app.services.analysis_service import (
    _parse_major_pair,
    _rule_based_intent,
    _template_summary,
)


@pytest.mark.parametrize("question, intent", [
    ("Which students improved the most?", "top_improvers"),
    ("Who made the biggest gains?", "top_improvers"),
    ("Which students declined the most?", "biggest_declines"),
    ("Show grade distribution", "grade_bands"),
    ("How many got a letter grade of A?", "grade_bands"),
    ("Which student performed the best?", "best_student"),
    ("Who had the lowest grade?", "worst_student"),
    ("Which major has the highest mean grade?", "best_major"),
    ("What is the weakest major?", "worst_major"),
    ("Show the SLO attainment distribution", "slo_distribution"),
    ("Summarize the overall performance of students", "summary_one_file"),
])
def test_rule_based_intent(question, intent):
    assert _rule_based_intent(question, has_two_files=True)["intent_type"] == intent


def test_major_comparison_resolves_abbreviations():
    intent = _rule_based_intent("Compare CS vs Biology students", has_two_files=False)
    assert intent["intent_type"] == "compare_majors"
    assert (intent["compare_major_a"], intent["compare_major_b"]) == ("Computer Science", "Biology")


def test_term_comparison_needs_two_files():
    question = "Compare before and after"
    assert _rule_based_intent(question, has_two_files=True)["intent_type"] == "compare_terms"
    assert _rule_based_intent(question, has_two_files=False)["intent_type"] == "summary_one_file"


def test_intent_has_the_shape_the_dispatcher_expects():
    intent = _rule_based_intent("anything", has_two_files=False)
    assert set(intent["filters"]) == {"major", "term", "gender", "year"}
    assert {"intent_type", "compare_major_a", "compare_major_b", "top_n", "file_scope"} <= intent.keys()


@pytest.mark.parametrize("question, expected", [
    ("Compare CS vs Biology", ("Computer Science", "Biology")),
    ("compare psych and business majors", ("Psychology", "Business")),
    ("Computer Science versus Economics", ("Computer Science", "Economics")),
    ("Compare CS vs Underwater Basketweaving", (None, None)),   # unknown major
    ("Compare CS vs compsci", (None, None)),                    # same major twice
    ("How did students do?", (None, None)),
])
def test_parse_major_pair(question, expected):
    assert _parse_major_pair(question) == expected


def test_template_summary_for_improvers():
    results = {"improvers": [{"Student Name": "Student 031", "Major": "Biology", "Change": 17.4}]}
    assert _template_summary(results, "top_improvers").startswith(
        "Student 031 from Biology improved the most, gaining +17.4 points."
    )


def test_template_summary_explains_missing_second_file():
    assert "requires two uploaded files" in _template_summary({"no_second_file": True})


def test_template_summary_for_grade_bands():
    bands = {"total": 4, "percentages": {"A (90+)": 50, "B (80–89)": 25, "C (70–79)": 25, "D/F (<70)": 0}}
    text = _template_summary({"grade_bands": bands}, "grade_bands")
    assert text.startswith("Of 4 students: 50% earned an A")
    assert "majority of students performed at a B or higher" in text
