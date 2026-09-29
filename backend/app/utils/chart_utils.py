"""
utils/chart_utils.py
--------------------
All chart generation.  Charts are rendered server-side with matplotlib
and returned as base64-encoded PNG strings for the frontend to embed
directly in <img> tags.

Non-interactive Agg backend is used — no display or GUI is needed.
"""

import base64
import io
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use("Agg")  # must be set before importing pyplot
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd

# Colour palette (indigo / amber / rose / emerald)
PALETTE = ["#6366f1", "#f59e0b", "#ef4444", "#10b981", "#8b5cf6", "#06b6d4"]

SLO_COLORS: Dict[str, str] = {
    "Not Meet":    "#ef4444",
    "Nearly Meet": "#f97316",
    "Meet":        "#22c55e",
    "Exceed":      "#3b82f6",
}


def _fig_to_b64(fig: plt.Figure) -> str:
    """Serialise a matplotlib Figure to a base64 PNG string."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return encoded


# ---------------------------------------------------------------------------
# Individual chart functions
# ---------------------------------------------------------------------------

def chart_mean_by_group(
    df: pd.DataFrame,
    group_col: str = "major",
    grade_col: str = "grade",
    title: str = "Mean Grade by Group",
) -> str:
    """Horizontal bar chart of mean grades per group, sorted descending."""
    means = (
        df.groupby(group_col)[grade_col]
        .mean()
        .sort_values(ascending=True)  # ascending so largest is at top
    )

    fig, ax = plt.subplots(figsize=(8, max(3, len(means) * 0.55)))
    colors = [PALETTE[i % len(PALETTE)] for i in range(len(means))]
    bars = ax.barh(means.index, means.values, color=colors, edgecolor="white", linewidth=0.5)

    for bar in bars:
        ax.text(
            bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
            f"{bar.get_width():.1f}",
            va="center", ha="left", fontsize=9,
        )

    ax.set_xlabel("Mean Grade")
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_xlim(0, 110)
    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f"))
    fig.tight_layout()
    return _fig_to_b64(fig)


def chart_slo_stacked(
    slo_pct: Dict[str, Any],
    title: str = "SLO Attainment Distribution",
) -> str:
    """
    Horizontal stacked bar showing SLO attainment percentages.
    slo_pct can be a flat dict {level: pct} or a list of group dicts.
    """
    order = ["Not Meet", "Nearly Meet", "Meet", "Exceed"]

    if isinstance(slo_pct, list):
        # Multiple groups — one bar each
        fig, ax = plt.subplots(figsize=(8, max(3, len(slo_pct) * 0.6)))
        for row in slo_pct:
            group_label = str(list(row.values())[0])  # first key is the group
            left = 0.0
            for level in order:
                val = float(row.get(level, 0))
                color = SLO_COLORS.get(level, "#9ca3af")
                ax.barh(group_label, val, left=left, color=color, edgecolor="white")
                if val > 6:
                    ax.text(left + val / 2, group_label, f"{val:.0f}%",
                            ha="center", va="center", fontsize=8,
                            color="white", fontweight="bold")
                left += val
    else:
        # Single group
        values = [float(slo_pct.get(l, 0)) for l in order]
        fig, ax = plt.subplots(figsize=(7, 2.5))
        left = 0.0
        for label, val in zip(order, values):
            color = SLO_COLORS.get(label, "#9ca3af")
            ax.barh("Students", val, left=left, color=color, label=label, edgecolor="white")
            if val > 6:
                ax.text(left + val / 2, 0, f"{val:.0f}%",
                        ha="center", va="center", fontsize=9,
                        color="white", fontweight="bold")
            left += val

    ax.set_xlim(0, 100)
    ax.set_xlabel("Percent of Students")
    ax.set_title(title, fontsize=12, fontweight="bold")

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=SLO_COLORS[l], label=l) for l in order]
    ax.legend(handles=legend_elements, loc="lower right", fontsize=8, framealpha=0.7)

    fig.tight_layout()
    return _fig_to_b64(fig)


def chart_boxplot_by_group(
    df: pd.DataFrame,
    group_col: str = "major",
    grade_col: str = "grade",
    title: str = "Grade Distribution by Group",
) -> str:
    """Box-and-whisker plot per group."""
    groups_dict = {k: list(v.dropna()) for k, v in df.groupby(group_col)[grade_col]}
    labels = list(groups_dict.keys())
    data   = list(groups_dict.values())

    fig, ax = plt.subplots(figsize=(max(6, len(labels) * 1.2), 4))
    bp = ax.boxplot(
        data, tick_labels=labels, patch_artist=True,
        boxprops=dict(facecolor="#6366f1", alpha=0.55),
        medianprops=dict(color="#fbbf24", linewidth=2),
        whiskerprops=dict(color="#6b7280"),
        capprops=dict(color="#6b7280"),
        flierprops=dict(marker="o", markerfacecolor="#ef4444", markersize=4, alpha=0.6),
    )
    ax.set_ylabel("Grade")
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_ylim(0, 110)
    plt.xticks(rotation=30, ha="right")
    fig.tight_layout()
    return _fig_to_b64(fig)


def chart_comparison_bars(
    stats_a: Dict[str, Any],
    stats_b: Dict[str, Any],
    label_a: str,
    label_b: str,
    title: str = "Comparison",
) -> str:
    """Grouped bar chart comparing Mean and Median for two groups (used for file comparisons)."""
    import numpy as np

    metrics = ["Mean", "Median"]
    a_vals  = [float(stats_a.get(m, 0)) for m in metrics]
    b_vals  = [float(stats_b.get(m, 0)) for m in metrics]

    x = np.arange(len(metrics))
    width = 0.35

    fig, ax = plt.subplots(figsize=(6, 4))
    bars_a = ax.bar(x - width / 2, a_vals, width, label=label_a, color=PALETTE[0], edgecolor="white")
    bars_b = ax.bar(x + width / 2, b_vals, width, label=label_b, color=PALETTE[1], edgecolor="white")

    for bar in (*bars_a, *bars_b):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                f"{bar.get_height():.1f}", ha="center", va="bottom", fontsize=9)

    ax.set_xticks(x)
    ax.set_xticklabels(metrics)
    ax.set_ylabel("Grade")
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_ylim(0, 110)
    ax.legend()
    fig.tight_layout()
    return _fig_to_b64(fig)


def chart_student_bars(
    rows: List[Dict[str, Any]],
    ascending: bool = False,
    title: str = "",
) -> str:
    """
    Horizontal bar chart for top/bottom N student rankings.
    Rank 1 always appears at the top of the chart.
    """
    names  = [str(r.get("Student Name", f"Student {i + 1}")) for i, r in enumerate(rows)]
    grades = [float(r.get("Grade", 0)) for r in rows]

    # Reverse so rank 1 is at the top
    names  = names[::-1]
    grades = grades[::-1]

    color = PALETTE[2] if ascending else PALETTE[0]  # rose for worst, indigo for best

    fig, ax = plt.subplots(figsize=(8, max(3.5, len(names) * 0.7)))
    bars = ax.barh(names, grades, color=color, edgecolor="white", linewidth=0.5)

    for bar in bars:
        ax.text(
            bar.get_width() + 0.4,
            bar.get_y() + bar.get_height() / 2,
            f"{bar.get_width():.1f}",
            va="center", ha="left", fontsize=9,
        )

    ax.set_xlabel("Grade")
    ax.set_xlim(0, 112)
    ax.set_title(
        title or ("Bottom 5 Students by Grade" if ascending else "Top 5 Students by Grade"),
        fontsize=12, fontweight="bold",
    )
    ax.grid(axis="x", linestyle="--", alpha=0.3, zorder=0)
    ax.spines[["top", "right"]].set_visible(False)

    fig.tight_layout()
    return _fig_to_b64(fig)


def chart_grade_bands(
    bands_result: Dict[str, Any],
    title: str = "Grade Distribution",
) -> str:
    """
    Vertical bar chart for letter-grade bands (A, B, C, D/F).
    Each bar shows count + percentage as a label.
    """
    counts = bands_result.get("counts", {})
    pct    = bands_result.get("percentages", {})
    if not counts:
        return ""

    labels = list(counts.keys())
    values = [counts[k] for k in labels]
    pcts   = [pct.get(k, 0.0) for k in labels]
    colors = ["#22c55e", "#6366f1", "#f59e0b", "#ef4444"]  # A=green B=indigo C=amber D/F=red

    fig, ax = plt.subplots(figsize=(7, 4.5))
    bars = ax.bar(labels, values, color=colors[:len(labels)],
                  edgecolor="white", linewidth=0.5, width=0.55)

    for bar, p in zip(bars, pcts):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.3,
            f"{int(bar.get_height())} ({p:.0f}%)",
            ha="center", va="bottom", fontsize=10, fontweight="bold",
        )

    ax.set_ylabel("Number of Students", fontsize=10)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.grid(axis="y", linestyle="--", alpha=0.3, zorder=0)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_ylim(0, (max(values) if values else 1) * 1.25)
    fig.tight_layout()
    return _fig_to_b64(fig)


def chart_grade_change(
    rows: List[Dict[str, Any]],
    ascending: bool = False,
    title: str = "",
) -> str:
    """
    Horizontal bar chart showing grade change per student.
    Green bars = improvement; red bars = decline.
    Rank 1 appears at the top.
    """
    names   = [str(r.get("Student Name", f"Student {i + 1}")) for i, r in enumerate(rows)]
    changes = [float(r.get("Change", 0)) for r in rows]

    # Reverse so rank 1 is at the top
    names   = names[::-1]
    changes = changes[::-1]

    colors = ["#22c55e" if c >= 0 else "#ef4444" for c in changes]

    fig, ax = plt.subplots(figsize=(8, max(3.5, len(names) * 0.75)))
    bars = ax.barh(names, changes, color=colors, edgecolor="white", linewidth=0.5)

    for bar, c in zip(bars, changes):
        offset = 0.3 if c >= 0 else -0.3
        ha     = "left" if c >= 0 else "right"
        ax.text(
            bar.get_width() + offset,
            bar.get_y() + bar.get_height() / 2,
            f"{'+' if c > 0 else ''}{c:.1f}",
            va="center", ha=ha, fontsize=9,
        )

    ax.axvline(0, color="#6b7280", linewidth=0.8)
    ax.set_xlabel("Grade Change", fontsize=10)
    ax.set_title(
        title or ("Top Improvers" if not ascending else "Biggest Declines"),
        fontsize=12, fontweight="bold",
    )
    ax.grid(axis="x", linestyle="--", alpha=0.3, zorder=0)
    ax.spines[["top", "right"]].set_visible(False)

    fig.tight_layout()
    return _fig_to_b64(fig)


def chart_major_comparison(
    stats_a: Dict[str, Any],
    stats_b: Dict[str, Any],
    label_a: str,
    label_b: str,
    title: str = "",
) -> str:
    """
    Clean side-by-side vertical bar chart for major-vs-major comparison.
    Shows Mean and Median with value labels and a zoomed Y axis.
    """
    import numpy as np

    metrics   = ["Mean Grade", "Median Grade"]
    a_vals    = [float(stats_a.get("Mean", 0)), float(stats_a.get("Median", 0))]
    b_vals    = [float(stats_b.get("Mean", 0)), float(stats_b.get("Median", 0))]

    x     = np.arange(len(metrics))
    width = 0.32

    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    bars_a = ax.bar(x - width / 2, a_vals, width, label=label_a,
                    color=PALETTE[0], edgecolor="white", linewidth=0.5)
    bars_b = ax.bar(x + width / 2, b_vals, width, label=label_b,
                    color=PALETTE[1], edgecolor="white", linewidth=0.5)

    # Bold value labels on top of each bar
    for bar in (*bars_a, *bars_b):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.6,
            f"{bar.get_height():.1f}",
            ha="center", va="bottom", fontsize=11, fontweight="bold",
        )

    # Zoom Y axis to data range for easier comparison
    all_vals = a_vals + b_vals
    y_min = max(0, min(all_vals) - 12)
    y_max = min(100, max(all_vals) + 14)
    ax.set_ylim(y_min, y_max)

    ax.set_xticks(x)
    ax.set_xticklabels(metrics, fontsize=10)
    ax.set_ylabel("Grade", fontsize=10)
    ax.set_title(title or f"{label_a} vs {label_b}", fontsize=12, fontweight="bold", pad=12)
    ax.legend(fontsize=9, framealpha=0.7)
    ax.grid(axis="y", linestyle="--", alpha=0.3, zorder=0)
    ax.spines[["top", "right"]].set_visible(False)

    fig.tight_layout()
    return _fig_to_b64(fig)
