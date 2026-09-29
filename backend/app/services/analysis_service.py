"""
services/analysis_service.py
-----------------------------
Orchestrates a full analysis cycle.

The AI layer (Gemini or OpenAI, selected via AI_PROVIDER in .env) handles:
  - Intent parsing  — convert natural language → structured intent JSON
  - NL summary      — turn pre-computed results → plain-English paragraph

If no AI provider is configured (or any AI call fails), both steps fall back to
local Python rule-based logic so the app always keeps working.
"""

import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from ..core.config import settings
from ..engine.analysis import (
    compare_two_datasets,
    compare_two_majors,
    grade_bands,
    grade_changes,
    overall_summary_one_file,
    rank_majors,
    rank_students,
    slo_distribution,
    summary_stats,
)
from ..engine.export import export_to_excel
from ..engine.io import load_csv, normalize_dataframe
from ..models.file_record import FileRecord
from ..schemas.analysis import AnalysisResult, ChartData, TableData
from ..utils.chart_utils import (
    chart_boxplot_by_group,
    chart_comparison_bars,
    chart_grade_bands,
    chart_grade_change,
    chart_major_comparison,
    chart_mean_by_group,
    chart_slo_stacked,
    chart_student_bars,
)


def _openai_available() -> bool:
    """True when OpenAI key is configured and looks valid."""
    return bool(settings.openai_api_key and settings.openai_api_key.startswith("sk-"))


def _gemini_available() -> bool:
    """True when Gemini is selected as provider and a key is present."""
    return bool(
        settings.ai_provider.lower() == "gemini"
        and settings.gemini_api_key
    )


def _ai_available() -> bool:
    """True when any configured AI provider is ready to use."""
    return _gemini_available() or (
        settings.ai_provider.lower() == "openai" and _openai_available()
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_analysis(
    question: str,
    file_ids: List[int],
    mapping: Dict[str, Optional[str]],
    records: List[FileRecord],
    do_export: bool = True,
) -> AnalysisResult:
    # 1. Load and normalise DataFrames
    df_a = _load_and_normalise(records[0], mapping)
    df_b = _load_and_normalise(records[1], mapping) if len(records) > 1 else None

    label_a = records[0].term_label or records[0].original_filename
    label_b = (records[1].term_label or records[1].original_filename) if df_b is not None else None

    # 2. Parse intent — use AI provider if configured, otherwise keyword fallback
    intent: Dict[str, Any]
    if _ai_available():
        from ..engine.query_parser import parse_intent_with_ai
        schema_ctx = _build_schema_context(df_a, df_b, label_a, label_b)
        ai_intent  = await parse_intent_with_ai(question, schema_ctx)
        # ai_intent is None on any failure → fall through to rule-based
        intent = ai_intent if ai_intent else _rule_based_intent(question, df_b is not None)
    else:
        intent = _rule_based_intent(question, df_b is not None)

    # 3. Dispatch to engine
    results, chart_objects = _dispatch(intent, df_a, df_b, label_a, label_b)

    # 4. NL summary (generated before export so it can be included in the workbook)
    summary: str
    if _ai_available():
        from ..engine.query_parser import generate_summary_with_ai
        ai_summary = await generate_summary_with_ai(question, results)
        # ai_summary is None on any failure → use template
        summary = ai_summary if ai_summary else _template_summary(results, intent.get("intent_type", ""))
    else:
        summary = _template_summary(results, intent.get("intent_type", ""))

    # 5. Data quality notes
    from ..engine.data_quality import check_data_quality
    data_quality_notes = check_data_quality(df_a, df_b, mapping)

    # 6. Excel export — includes metadata so the Report Summary sheet is populated
    session_id: Optional[str] = None
    if do_export:
        session_id = uuid.uuid4().hex[:10]
        export_metadata = {
            "question":           question,
            "summary":            summary,
            "data_quality_notes": data_quality_notes,
            "label_a":            label_a,
            "label_b":            label_b,
            "generated_at":       datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        export_to_excel(
            results,
            settings.outputs_dir / f"{session_id}.xlsx",
            metadata=export_metadata,
            charts=chart_objects,
        )

    return AnalysisResult(
        summary=summary,
        data_quality_notes=data_quality_notes,
        tables=_extract_tables(results),
        charts=chart_objects,
        stat_tests=_extract_stat_tests(results),
        export_session_id=session_id,
        raw_intent=intent,
        comparison_cards=_extract_comparison_cards(results),
    )


# ---------------------------------------------------------------------------
# OpenAI-free fallbacks
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Major name aliases for rule-based parsing (abbreviation → canonical name)
# ---------------------------------------------------------------------------

_MAJOR_ALIASES: Dict[str, str] = {
    "cs":                   "Computer Science",
    "computer science":     "Computer Science",
    "compsci":              "Computer Science",
    "comp sci":             "Computer Science",
    "bio":                  "Biology",
    "biology":              "Biology",
    "psych":                "Psychology",
    "psychology":           "Psychology",
    "business":             "Business",
    "biz":                  "Business",
    "bus":                  "Business",
    "math":                 "Mathematics",
    "mathematics":          "Mathematics",
    "chem":                 "Chemistry",
    "chemistry":            "Chemistry",
    "eng":                  "Engineering",
    "engineering":          "Engineering",
    "econ":                 "Economics",
    "economics":            "Economics",
    "polsci":               "Political Science",
    "poli sci":             "Political Science",
    "political science":    "Political Science",
    "hist":                 "History",
    "history":              "History",
    "nursing":              "Nursing",
    "physics":              "Physics",
    "sociology":            "Sociology",
    "soc":                  "Sociology",
}


def _normalize_major(raw: str) -> Optional[str]:
    """Map a raw user-typed major name or abbreviation to a canonical name."""
    key = raw.strip().lower()
    return _MAJOR_ALIASES.get(key)


def _parse_major_pair(question: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Try to extract two major names from a comparison question.
    Handles patterns like:
      - "Compare CS vs Biology"
      - "CS vs Biology students"
      - "Computer Science versus Business"
      - "Compare Computer Science and Biology"
    Returns (None, None) if two distinct majors cannot be resolved.
    """
    q = question.strip()
    # Patterns ordered from most specific to least specific
    patterns = [
        # "compare X vs Y" or "compare X versus Y"
        r'compare\s+(.+?)\s+(?:vs\.?|versus)\s+(.+?)(?:\s+students?|\s+majors?|$)',
        # "compare X and Y students/majors" 
        r'compare\s+(.+?)\s+and\s+(.+?)(?:\s+students?|\s+majors?|$)',
        # plain "X vs Y"
        r'(.+?)\s+(?:vs\.?|versus)\s+(.+?)(?:\s+students?|\s+majors?|$)',
    ]
    for pat in patterns:
        m = re.search(pat, q, re.IGNORECASE)
        if m:
            a = _normalize_major(m.group(1).strip())
            b = _normalize_major(m.group(2).strip())
            if a and b and a != b:
                return a, b
    return None, None


def _rule_based_intent(question: str, has_two_files: bool) -> Dict[str, Any]:
    """
    Keyword matching used when no OpenAI key is configured.
    Covers the most common faculty questions.
    Checked in priority order: student → major → SLO → comparison → summary.
    """
    q = question.lower()
    base: Dict[str, Any] = {
        "filters": {"major": None, "term": None, "gender": None, "year": None},
        "compare_major_a": None,
        "compare_major_b": None,
        "top_n": 5,
        "file_scope": "both",
    }

    # ── Grade change questions (two-file; must be before student questions) ────
    # "improve", "gain", "progress" → top improvers
    # "declin", "dropped", "fell", "regress" → biggest declines
    if any(w in q for w in ["improv", " gain", "progress"]):
        return {**base, "intent_type": "top_improvers"}
    if any(w in q for w in ["declin", "dropped", "fell ", "worsened", "regress"]):
        return {**base, "intent_type": "biggest_declines"}

    # ── Grade band distribution (before SLO check) ───────────────────────────
    _grade_band_kw = [
        "grade band", "letter grade", "grade distribut",
        "a grade", "b grade", "c grade", "got a ", "got b ", "got c ",
    ]
    if any(w in q for w in _grade_band_kw) and "slo" not in q:
        return {**base, "intent_type": "grade_bands"}

    # ── Student-level questions (must be checked before major questions) ──────
    # Signals: "student", "who", "person", "individual", or known phrase patterns
    _student_signals = [
        "student", "who ", "person", "individual", "learner",
        "performed the best", "performed the worst",
        "had the highest grade", "had the lowest grade",
        "highest grade", "lowest grade",
        "best student", "worst student",
        "top student", "bottom student",
    ]
    is_student_q = any(sig in q for sig in _student_signals)

    if is_student_q:
        if any(w in q for w in ["best", "top", "highest"]):
            return {**base, "intent_type": "best_student"}
        if any(w in q for w in ["worst", "lowest", "bottom"]):
            return {**base, "intent_type": "worst_student"}

    # ── Major-level ranking ───────────────────────────────────────────────────
    if any(w in q for w in ["best", "top", "highest", "leading"]) and "major" in q:
        return {**base, "intent_type": "best_major"}

    if any(w in q for w in ["worst", "lowest", "bottom", "weakest"]) and "major" in q:
        return {**base, "intent_type": "worst_major"}

    # ── SLO distribution ─────────────────────────────────────────────────────
    if "slo" in q or "attainment" in q:
        return {**base, "intent_type": "slo_distribution"}

    # ── Major-vs-major comparison ─────────────────────────────────────────────
    major_a, major_b = _parse_major_pair(question)
    if major_a and major_b:
        return {
            **base,
            "intent_type":      "compare_majors",
            "compare_major_a":  major_a,
            "compare_major_b":  major_b,
        }

    # ── Two-file term comparison ──────────────────────────────────────────────
    if any(w in q for w in ["compare", "difference", "before", "after", "vs", "versus", "between"]):
        if has_two_files:
            return {**base, "intent_type": "compare_terms"}

    return {**base, "intent_type": "summary_one_file", "file_scope": "file_a"}


def _template_summary(results: Dict[str, Any], intent_type: str = "") -> str:
    """
    Generate a concise, plain-English summary suitable for non-technical faculty.
    Rules:
      - 1–3 short sentences maximum.
      - No SD, no median, no p-values, no ANOVA mentions.
      - Statistical detail stays in the tables and Statistical Tests section.
      - Use early return per case so blocks don't accidentally stack.
    """

    # ── Requires two files ────────────────────────────────────────────────────
    if results.get("no_second_file"):
        return (
            "This question requires two uploaded files to compare student progress. "
            "Upload a second CSV file and try again."
        )

    # ── No matched students between files ─────────────────────────────────────
    if results.get("no_match"):
        return (
            "No matching student names were found between the two files. "
            "Make sure both files use the same student name format."
        )

    # ── No student name column ────────────────────────────────────────────────
    if results.get("no_student_name"):
        return (
            "Student-level ranking requires a student name or ID column. "
            "Please ensure your CSV includes a student name column and that it is "
            "mapped correctly in the column mapping step."
        )

    # ── Top improvers ─────────────────────────────────────────────────────────
    if results.get("improvers"):
        rows  = results["improvers"]
        top   = rows[0]
        name  = top.get("Student Name", "Unknown")
        chg   = top.get("Change")
        major_str = f" from {top['Major']}" if top.get("Major") else ""
        chg_str   = f"+{chg:.1f}" if isinstance(chg, (int, float)) and chg >= 0 else (
            f"{chg:.1f}" if isinstance(chg, (int, float)) else "?"
        )
        lines = [
            f"{name}{major_str} improved the most, gaining {chg_str} points.",
            f"See the Top Improvers table for the full list.",
        ]
        return " ".join(lines)

    # ── Biggest declines ──────────────────────────────────────────────────────
    if results.get("declines"):
        rows  = results["declines"]
        bot   = rows[0]
        name  = bot.get("Student Name", "Unknown")
        chg   = bot.get("Change")
        major_str = f" from {bot['Major']}" if bot.get("Major") else ""
        chg_str   = f"{chg:.1f}" if isinstance(chg, (int, float)) else "?"
        lines = [
            f"{name}{major_str} had the biggest decline, dropping {chg_str} points.",
            f"See the Biggest Declines table for the full list.",
        ]
        return " ".join(lines)

    # ── Grade bands ───────────────────────────────────────────────────────────
    if results.get("grade_bands"):
        bands = results["grade_bands"]
        total = bands.get("total", 0)
        pct   = bands.get("percentages", {})
        a_pct  = pct.get("A (90+)",   0)
        b_pct  = pct.get("B (80–89)", 0)
        c_pct  = pct.get("C (70–79)", 0)
        df_pct = pct.get("D/F (<70)", 0)
        lines  = [
            f"Of {total} students: {a_pct:.0f}% earned an A, "
            f"{b_pct:.0f}% a B, {c_pct:.0f}% a C, and {df_pct:.0f}% below a C."
        ]
        if a_pct + b_pct >= 60:
            lines.append("The majority of students performed at a B or higher.")
        return " ".join(lines)

    # ── Top students ──────────────────────────────────────────────────────────
    if results.get("top_students"):
        top   = results["top_students"][0]
        name  = top.get("Student Name", "Unknown")
        grade = top.get("Grade", "?")
        major_str = f" from {top['Major']}" if top.get("Major") else ""
        term_str  = (
            f" ({top['Term']})"
            if top.get("Term") and top.get("Term") not in ("Unknown", "")
            else ""
        )
        grade_str = f"{grade:.1f}" if isinstance(grade, (int, float)) else str(grade)
        lines = [
            f"The top-performing student is {name}{major_str}{term_str} "
            f"with a grade of {grade_str}."
        ]
        if len(results["top_students"]) > 1:
            lines.append(
                f"See the Top Students table below for the full ranking."
            )
        return " ".join(lines)

    # ── Bottom students ───────────────────────────────────────────────────────
    if results.get("bottom_students"):
        bot   = results["bottom_students"][0]
        name  = bot.get("Student Name", "Unknown")
        grade = bot.get("Grade", "?")
        major_str = f" from {bot['Major']}" if bot.get("Major") else ""
        term_str  = (
            f" ({bot['Term']})"
            if bot.get("Term") and bot.get("Term") not in ("Unknown", "")
            else ""
        )
        grade_str = f"{grade:.1f}" if isinstance(grade, (int, float)) else str(grade)
        lines = [
            f"The lowest-performing student is {name}{major_str}{term_str} "
            f"with a grade of {grade_str}."
        ]
        if len(results["bottom_students"]) > 1:
            lines.append("See the Bottom Students table below for the full ranking.")
        return " ".join(lines)

    # ── Two-file comparison ───────────────────────────────────────────────────
    if "overall_stats" in results:
        stats  = results["overall_stats"]
        labels = list(stats.keys())
        if len(labels) == 2:
            la, lb = labels
            ma  = stats[la].get("Mean")
            mb  = stats[lb].get("Mean")
            na  = stats[la].get("N", "?")
            nb  = stats[lb].get("N", "?")
            if ma is not None and mb is not None:
                diff    = abs(ma - mb)
                better  = la if ma > mb else lb
                worse   = lb if ma > mb else la
                lines = [
                    f"This comparison includes {na} records from {la} and {nb} from {lb}.",
                    f"Students in {better} averaged {max(ma, mb):.1f} compared to "
                    f"{min(ma, mb):.1f} in {worse}, a difference of {diff:.1f} points.",
                ]
                t = results.get("ttest_overall", {})
                if t and "error" not in t:
                    note = (
                        "This difference is statistically significant."
                        if t.get("significant")
                        else "This difference is not statistically significant."
                    )
                    lines.append(note)
                return " ".join(lines)
        return "Comparison complete. See the charts and tables below for details."

    # ── Major-vs-major comparison ─────────────────────────────────────────────
    if "stats_a" in results and "stats_b" in results:
        sa     = results["stats_a"]
        sb     = results["stats_b"]
        ttest  = results.get("ttest", {})
        cmp    = ttest.get("comparison", "")
        parts  = cmp.split(" vs ")
        name_a = parts[0].strip() if len(parts) == 2 else "Group A"
        name_b = parts[1].strip() if len(parts) == 2 else "Group B"
        mean_a = sa.get("Mean")
        mean_b = sb.get("Mean")
        if mean_a is not None and mean_b is not None:
            diff   = abs(mean_a - mean_b)
            better = name_a if mean_a > mean_b else name_b
            lines  = [
                f"{name_a} students averaged {mean_a:.1f} compared to {mean_b:.1f} "
                f"for {name_b}, a difference of {diff:.1f} points.",
                f"{better} had the higher average grade.",
            ]
            if ttest and "error" not in ttest:
                note = (
                    "This difference is statistically significant. "
                    "See the Statistical Tests section for details."
                    if ttest.get("significant")
                    else "This difference is not statistically significant."
                )
                lines.append(note)
            return " ".join(lines)
        return "Major comparison complete. See the charts and tables below for details."

    # ── Best major ────────────────────────────────────────────────────────────
    if intent_type == "best_major" and results.get("rankings"):
        top      = results["rankings"][0]
        top_mean = top.get("Mean")
        lines    = []
        if top_mean is not None:
            lines.append(
                f"{top['major']} has the highest average grade among all majors, "
                f"with a mean of {top_mean:.1f}."
            )
        overall = results.get("overall", {})
        n    = overall.get("N")
        mean = overall.get("Mean")
        if n and mean is not None:
            lines.append(
                f"The overall average across all {n} students is {mean:.1f}."
            )
        return " ".join(lines) if lines else "See the Rankings table for full details."

    # ── Worst major ───────────────────────────────────────────────────────────
    if intent_type == "worst_major" and results.get("rankings"):
        bot      = results["rankings"][0]
        bot_mean = bot.get("Mean")
        lines    = []
        if bot_mean is not None:
            lines.append(
                f"{bot['major']} has the lowest average grade among all majors, "
                f"with a mean of {bot_mean:.1f}."
            )
        overall = results.get("overall", {})
        n    = overall.get("N")
        mean = overall.get("Mean")
        if n and mean is not None:
            lines.append(
                f"The overall average across all {n} students is {mean:.1f}."
            )
        return " ".join(lines) if lines else "See the Rankings table for full details."

    # ── SLO distribution ──────────────────────────────────────────────────────
    if intent_type == "slo_distribution" and "slo_distribution" in results:
        pct = results["slo_distribution"].get("percentages", {})
        if isinstance(pct, dict):
            meet     = float(pct.get("Meet", 0))
            exceed   = float(pct.get("Exceed", 0))
            not_meet = float(pct.get("Not Meet", 0))
            total_met = meet + exceed
            lines = [f"About {total_met:.0f}% of students met or exceeded the SLO threshold."]
            if not_meet > 0:
                lines.append(f"{not_meet:.0f}% did not meet the minimum requirement.")
            lines.append("See the charts and SLO table for a breakdown by major.")
            return " ".join(lines)

    # ── General one-file summary ──────────────────────────────────────────────
    if "overall" in results:
        s    = results["overall"]
        n    = s.get("N", "?")
        mean = s.get("Mean")
        lines = []

        intro = f"This analysis includes {n} student records"
        intro += f" with an overall average grade of {mean:.1f}." if mean is not None else "."
        lines.append(intro)

        rankings = results.get("rankings", [])
        if len(rankings) >= 2:
            best      = rankings[0]
            worst     = rankings[-1]
            best_mean = best.get("Mean")
            worst_mean = worst.get("Mean")
            if best_mean is not None and worst_mean is not None:
                lines.append(
                    f"{best['major']} had the highest average ({best_mean:.1f}), "
                    f"while {worst['major']} had the lowest ({worst_mean:.1f})."
                )

        meet = s.get("% Meet+Exceed")
        if meet is not None:
            lines.append(f"About {meet:.0f}% of students met or exceeded the SLO threshold.")

        return " ".join(lines)

    return "Analysis complete. See the charts and tables below for details."


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_and_normalise(record: FileRecord, mapping: Dict[str, Optional[str]]) -> pd.DataFrame:
    path = settings.uploads_dir / record.stored_filename
    df   = load_csv(path)
    return normalize_dataframe(df, mapping, record.term_label)


def _build_schema_context(df_a, df_b, label_a, label_b) -> str:
    ctx = f"Columns: {list(df_a.columns)}."
    if "major" in df_a.columns:
        ctx += f" Majors in {label_a}: {sorted(df_a['major'].dropna().unique().tolist())}."
    if df_b is not None:
        if "major" in df_b.columns:
            ctx += f" Majors in {label_b}: {sorted(df_b['major'].dropna().unique().tolist())}."
        ctx += f" Two files uploaded: '{label_a}' and '{label_b}'."
    else:
        ctx += " One file uploaded."
    return ctx


def _match_major(name: str, available: List[str]) -> Optional[str]:
    """Case-insensitive major name match against the actual values in the data."""
    name_lower = name.lower()
    for candidate in available:
        if candidate.lower() == name_lower:
            return candidate
    return None


def _extract_comparison_cards(results: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """
    Extract two-group metric data for the comparison cards UI.
    Only populated for major-vs-major results that have stats_a / stats_b.
    """
    if "stats_a" not in results or "stats_b" not in results:
        return None

    ttest = results.get("ttest", {})
    cmp_label = ttest.get("comparison", "")
    parts = cmp_label.split(" vs ")
    name_a = parts[0].strip() if len(parts) == 2 else "Group A"
    name_b = parts[1].strip() if len(parts) == 2 else "Group B"

    def _card(name: str, s: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "label":           name,
            "mean":            s.get("Mean"),
            "median":          s.get("Median"),
            "n":               s.get("N"),
            "meet_exceed_pct": s.get("% Meet+Exceed"),
        }

    return [_card(name_a, results["stats_a"]), _card(name_b, results["stats_b"])]


def _dispatch(
    intent: Dict[str, Any],
    df_a: pd.DataFrame,
    df_b: Optional[pd.DataFrame],
    label_a: str,
    label_b: Optional[str],
) -> Tuple[Dict[str, Any], List[ChartData]]:
    intent_type = intent.get("intent_type", "summary_one_file")
    charts: List[ChartData] = []

    def _apply_filters(df: pd.DataFrame) -> pd.DataFrame:
        filters = intent.get("filters") or {}
        if filters.get("major") and "major" in df.columns:
            df = df[df["major"].str.lower() == filters["major"].lower()]
        if filters.get("gender") and "gender" in df.columns:
            df = df[df["gender"].str.lower() == filters["gender"].lower()]
        if filters.get("year") and "year" in df.columns:
            df = df[df["year"].str.lower() == filters["year"].lower()]
        return df

    df_a = _apply_filters(df_a)
    if df_b is not None:
        df_b = _apply_filters(df_b)

    if intent_type in ("summary_one_file",) or (
        df_b is None and intent_type not in (
            "compare_majors", "best_major", "worst_major",
            "slo_distribution", "best_student", "worst_student",
        )
    ):
        results = overall_summary_one_file(df_a)
        if "major" in df_a.columns and not df_a.empty:
            charts.append(ChartData(title="Mean Grade by Major",
                                    image_b64=chart_mean_by_group(df_a)))
            charts.append(ChartData(title="Grade Distribution",
                                    image_b64=chart_boxplot_by_group(df_a)))
        slo = results.get("slo_distribution", {})
        if isinstance(slo.get("percentages"), dict):
            charts.append(ChartData(title="SLO Attainment",
                                    image_b64=chart_slo_stacked(slo["percentages"])))

    elif intent_type in ("compare_terms", "summary_two_files") and df_b is not None:
        results = compare_two_datasets(df_a, df_b, label_a, label_b or "File B")
        charts.append(ChartData(
            title=f"{label_a} vs {label_b}",
            image_b64=chart_comparison_bars(
                results["overall_stats"][label_a],
                results["overall_stats"][label_b or "File B"],
                label_a, label_b or "File B",
                title=f"Overall: {label_a} vs {label_b}",
            )
        ))
        if "major" in df_a.columns:
            combined = pd.concat([
                df_a.assign(term=label_a),
                df_b.assign(term=label_b or "File B"),
            ], ignore_index=True)
            charts.append(ChartData(title="Mean Grade by Major (Combined)",
                                    image_b64=chart_mean_by_group(combined)))
            charts.append(ChartData(title="Grade Distribution (Combined)",
                                    image_b64=chart_boxplot_by_group(combined)))

    elif intent_type == "compare_majors":
        major_a = intent.get("compare_major_a")
        major_b = intent.get("compare_major_b")
        combined = pd.concat([df_a] + ([df_b] if df_b is not None else []), ignore_index=True)
        if major_a and major_b and "major" in combined.columns:
            # Resolve case-insensitive match against actual data values
            available = combined["major"].dropna().unique().tolist()
            major_a = _match_major(major_a, available) or major_a
            major_b = _match_major(major_b, available) or major_b

            results = compare_two_majors(combined, major_a, major_b)
            sa = results.get("stats_a", {})
            sb = results.get("stats_b", {})
            sub = combined[combined["major"].isin([major_a, major_b])]

            if not sub.empty and sa and sb:
                # Primary: clean side-by-side bar chart
                charts.append(ChartData(
                    title=f"{major_a} vs {major_b}",
                    image_b64=chart_major_comparison(
                        sa, sb, major_a, major_b,
                        title=f"{major_a} vs {major_b}: Mean & Median",
                    ),
                ))
                # Secondary: distribution overview
                charts.append(ChartData(
                    title=f"Grade Distribution: {major_a} vs {major_b}",
                    image_b64=chart_boxplot_by_group(
                        sub, title=f"Grade Distribution by Major",
                    ),
                ))
        else:
            results = overall_summary_one_file(df_a)

    elif intent_type in ("best_major", "worst_major"):
        combined = pd.concat([df_a] + ([df_b] if df_b is not None else []), ignore_index=True)
        ascending = intent_type == "worst_major"
        results = {
            "rankings": rank_majors(combined, ascending=ascending),
            "overall":  summary_stats(combined),
        }
        if "major" in combined.columns and not combined.empty:
            charts.append(ChartData(title="Mean Grade by Major",
                                    image_b64=chart_mean_by_group(combined)))

    elif intent_type == "slo_distribution":
        combined = pd.concat([df_a] + ([df_b] if df_b is not None else []), ignore_index=True)
        slo = slo_distribution(combined, group_col="major" if "major" in combined.columns else None)
        results = {"slo_distribution": slo}
        pct = slo.get("percentages")
        if pct:
            charts.append(ChartData(title="SLO Attainment Distribution",
                                    image_b64=chart_slo_stacked(pct)))

    elif intent_type in ("best_student", "worst_student"):
        combined = pd.concat([df_a] + ([df_b] if df_b is not None else []), ignore_index=True)
        ascending = intent_type == "worst_student"
        top_n     = int(intent.get("top_n") or 5)
        label     = "Bottom" if ascending else "Top"
        result_key = "bottom_students" if ascending else "top_students"

        if "student_name" not in combined.columns:
            # Friendly message — no crash
            results = {
                "no_student_name": True,
                "overall": summary_stats(combined),
            }
        else:
            rows = rank_students(combined, ascending=ascending, top_n=top_n)
            results = {
                result_key: rows,
                "overall":  summary_stats(combined),
            }
            if rows:
                charts.append(ChartData(
                    title=f"{label} {top_n} Students by Grade",
                    image_b64=chart_student_bars(
                        rows, ascending=ascending,
                        title=f"{label} {top_n} Students by Grade",
                    ),
                ))

    elif intent_type == "top_improvers":
        if df_b is None:
            results = {"no_second_file": True, "overall": summary_stats(df_a)}
        elif "student_name" not in df_a.columns or "student_name" not in df_b.columns:
            results = {"no_student_name": True, "overall": summary_stats(df_a)}
        else:
            rows = grade_changes(df_a, df_b, ascending=False, top_n=5)
            if not rows:
                results = {"no_match": True, "overall": summary_stats(df_a)}
            else:
                results = {
                    "improvers": rows,
                    "overall":   summary_stats(pd.concat([df_a, df_b], ignore_index=True)),
                }
                charts.append(ChartData(
                    title="Top 5 Improvers",
                    image_b64=chart_grade_change(rows, ascending=False, title="Top 5 Improvers"),
                ))

    elif intent_type == "biggest_declines":
        if df_b is None:
            results = {"no_second_file": True, "overall": summary_stats(df_a)}
        elif "student_name" not in df_a.columns or "student_name" not in df_b.columns:
            results = {"no_student_name": True, "overall": summary_stats(df_a)}
        else:
            rows = grade_changes(df_a, df_b, ascending=True, top_n=5)
            if not rows:
                results = {"no_match": True, "overall": summary_stats(df_a)}
            else:
                results = {
                    "declines": rows,
                    "overall":  summary_stats(pd.concat([df_a, df_b], ignore_index=True)),
                }
                charts.append(ChartData(
                    title="Biggest Grade Declines",
                    image_b64=chart_grade_change(rows, ascending=True, title="Biggest Grade Declines"),
                ))

    elif intent_type == "grade_bands":
        combined = pd.concat([df_a] + ([df_b] if df_b is not None else []), ignore_index=True)
        bands = grade_bands(combined)
        results = {"grade_bands": bands}
        if bands:
            charts.append(ChartData(
                title="Grade Distribution by Band",
                image_b64=chart_grade_bands(bands, title="Grade Distribution by Band"),
            ))

    else:
        results = overall_summary_one_file(df_a)
        if "major" in df_a.columns and not df_a.empty:
            charts.append(ChartData(title="Mean Grade by Major",
                                    image_b64=chart_mean_by_group(df_a)))

    return results, charts


def _extract_tables(results: Dict[str, Any]) -> List[TableData]:
    tables = []

    # Grade bands — convert the nested dict to a flat table
    if results.get("grade_bands"):
        bands  = results["grade_bands"]
        counts = bands.get("counts", {})
        pct    = bands.get("percentages", {})
        band_rows = [
            {"Grade Band": k, "Count": v, "Percentage": f"{pct.get(k, 0.0):.0f}%"}
            for k, v in counts.items()
        ]
        if band_rows:
            tables.append(TableData(title="Grade Bands", rows=band_rows))

    for key, title in [
        ("top_students",    "Top Students"),
        ("bottom_students", "Bottom Students"),
        ("improvers",       "Top Improvers"),
        ("declines",        "Biggest Declines"),
        ("by_major",        "Summary by Major"),
        ("by_major_a",      "By Major (File A)"),
        ("by_major_b",      "By Major (File B)"),
        ("rankings",        "Rankings"),
    ]:
        if key in results and results[key]:
            tables.append(TableData(title=title, rows=results[key]))
    if "overall_stats" in results:
        rows = [{"Group": k, **v} for k, v in results["overall_stats"].items()]
        tables.append(TableData(title="Group Comparison", rows=rows))
    return tables


def _extract_stat_tests(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    tests = []
    for key in ("ttest_overall", "ttest", "anova", "anova_a", "anova_b"):
        if key in results:
            tests.append(results[key])
    if "per_major_tests" in results:
        tests.extend(results["per_major_tests"])
    return tests
