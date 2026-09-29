"""
Batch SLO Assessment Analysis (Before vs After)
Effect sizes removed (NO Cohen's d)

NOTE: This is the original standalone script the web app's analytics engine
(backend/app/engine/) was refactored from. It is kept for reference and still
runs on its own:

    python legacy/student_assessment.py

It reads the sample CSVs from frontend/public/samples/ and writes its outputs
to legacy/output/ (gitignored).

Outputs:
- accreditation_summary.xlsx
- plot_mean_by_major_semester.png
- plot_attainment_stacked_overall.png
- plot_box_by_major_semester.png
"""

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats


# -----------------------------
# File Paths
# Resolved relative to this file, so the script works from any directory.
# -----------------------------
_here      = Path(__file__).resolve().parent
_samples   = _here.parent / "frontend" / "public" / "samples"
before_csv = _samples / "assessment_before.csv"
after_csv  = _samples / "assessment_after.csv"
out_dir    = _here / "output"
out_dir.mkdir(exist_ok=True)

# -----------------------------
# SLO Attainment Thresholds
# -----------------------------
def slo_level(score):
    if score < 70:
        return "Not Meet"
    elif score < 80:
        return "Nearly Meet"
    elif score < 90:
        return "Meet"
    else:
        return "Exceed"


# -----------------------------
# Summary Statistics Function
# -----------------------------
def summary_stats(df):
    g = df["AssignmentGrade"]
    return pd.Series({
        "N": g.count(),
        "Mean": g.mean(),
        "SD": g.std(ddof=1),
        "Median": g.median(),
        "Min": g.min(),
        "Max": g.max(),
        "% Meet+Exceed": (df["SLO_Level"].isin(["Meet", "Exceed"]).mean() * 100),
        "% Not Meet": (df["SLO_Level"].eq("Not Meet").mean() * 100),
    })


# -----------------------------
# Load Data
# -----------------------------
before = pd.read_csv(before_csv)
after  = pd.read_csv(after_csv)

before["Semester"] = "Before (Prev)"
after["Semester"]  = "After (Current)"

data = pd.concat([before, after], ignore_index=True)

# Add SLO attainment category
data["SLO_Level"] = data["AssignmentGrade"].apply(slo_level)


# -----------------------------
# Summary Tables
# -----------------------------
overall_summary = data.groupby("Semester").apply(summary_stats).reset_index()

major_summary = (
    data.groupby(["Semester", "Major"])
        .apply(summary_stats)
        .reset_index()
)

# Attainment Counts + Percentages (Overall)
attain_overall_counts = (
    data.pivot_table(index="Semester",
                     columns="SLO_Level",
                     values="StudentName",
                     aggfunc="count",
                     fill_value=0)
    .reindex(columns=["Not Meet", "Nearly Meet", "Meet", "Exceed"])
)

attain_overall_pct = attain_overall_counts.div(attain_overall_counts.sum(axis=1), axis=0) * 100

# Attainment Counts + Percentages (Major)
attain_major_counts = (
    data.pivot_table(index=["Semester", "Major"],
                     columns="SLO_Level",
                     values="StudentName",
                     aggfunc="count",
                     fill_value=0)
    .reindex(columns=["Not Meet", "Nearly Meet", "Meet", "Exceed"])
)

attain_major_pct = attain_major_counts.div(attain_major_counts.sum(axis=1), axis=0) * 100


# -----------------------------
# Statistical Tests (NO Effect Sizes)
# -----------------------------
tests = []

# Overall Before vs After (Welch t-test)
x = before["AssignmentGrade"]
y = after["AssignmentGrade"]

t, p = stats.ttest_ind(x, y, equal_var=False)

tests.append({
    "Comparison": "Overall: Before vs After",
    "Test": "Welch t-test",
    "n_before": len(x),
    "n_after": len(y),
    "mean_before": x.mean(),
    "mean_after": y.mean(),
    "t_statistic": t,
    "p_value": p
})


# Major-specific Before vs After
majors = sorted(data["Major"].unique())

for major in majors:
    xb = before.loc[before["Major"] == major, "AssignmentGrade"]
    ya = after.loc[after["Major"] == major, "AssignmentGrade"]

    if len(xb) >= 2 and len(ya) >= 2:
        t, p = stats.ttest_ind(xb, ya, equal_var=False)
    else:
        t, p = np.nan, np.nan

    tests.append({
        "Comparison": f"{major}: Before vs After",
        "Test": "Welch t-test",
        "n_before": len(xb),
        "n_after": len(ya),
        "mean_before": xb.mean(),
        "mean_after": ya.mean(),
        "t_statistic": t,
        "p_value": p
    })


# ANOVA Across Majors Within Each Semester
for sem_label, df_sem in [("Before", before), ("After", after)]:
    groups = [
        df_sem.loc[df_sem["Major"] == m, "AssignmentGrade"]
        for m in df_sem["Major"].unique()
    ]

    f, p = stats.f_oneway(*groups)

    tests.append({
        "Comparison": f"{sem_label}: Major Differences",
        "Test": "One-way ANOVA",
        "F_statistic": f,
        "p_value": p
    })


# CS vs Biology Within Each Semester
def cs_vs_bio(df, semester):
    cs = df.loc[df["Major"] == "Computer Science", "AssignmentGrade"]
    bio = df.loc[df["Major"] == "Biology", "AssignmentGrade"]

    if len(cs) >= 2 and len(bio) >= 2:
        t, p = stats.ttest_ind(cs, bio, equal_var=False)
    else:
        t, p = np.nan, np.nan

    tests.append({
        "Comparison": f"{semester}: CS vs Biology",
        "Test": "Welch t-test",
        "mean_CS": cs.mean(),
        "mean_Biology": bio.mean(),
        "t_statistic": t,
        "p_value": p
    })

cs_vs_bio(before, "Before")
cs_vs_bio(after, "After")


tests_df = pd.DataFrame(tests)


# -----------------------------
# Accreditation Plots
# -----------------------------
plot1 = out_dir / "plot_mean_by_major_semester.png"
plot2 = out_dir / "plot_attainment_stacked_overall.png"
plot3 = out_dir / "plot_box_by_major_semester.png"

# Plot 1: Mean Grade by Major & Semester
means = data.groupby(["Semester", "Major"])["AssignmentGrade"].mean().unstack()

means.plot(kind="bar", figsize=(10, 5))
plt.ylabel("Mean Assignment Grade")
plt.title("Mean Assignment Grade by Major (Before vs After)")
plt.tight_layout()
plt.savefig(plot1, dpi=200)
plt.close()

# Plot 2: Overall Attainment Distribution
attain_overall_pct.plot(kind="bar", stacked=True, figsize=(8, 5))
plt.ylabel("Percent of Students")
plt.title("SLO Attainment Distribution (Overall)")
plt.tight_layout()
plt.savefig(plot2, dpi=200)
plt.close()

# Plot 3: Boxplot by Major and Semester
data.boxplot(column="AssignmentGrade", by=["Semester", "Major"], figsize=(12, 6))
plt.xticks(rotation=45)
plt.ylabel("Assignment Grade")
plt.title("Grade Distribution by Major and Semester")
plt.suptitle("")
plt.tight_layout()
plt.savefig(plot3, dpi=200)
plt.close()


# -----------------------------
# Export Excel Workbook
# -----------------------------
xlsx_path = out_dir / "accreditation_summary.xlsx"

with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
    overall_summary.to_excel(writer, index=False, sheet_name="Overall Summary")
    major_summary.to_excel(writer, index=False, sheet_name="Major Summary")

    attain_overall_counts.to_excel(writer, sheet_name="Attainment Counts Overall")
    attain_overall_pct.to_excel(writer, sheet_name="Attainment % Overall")

    attain_major_counts.to_excel(writer, sheet_name="Attainment Counts Major")
    attain_major_pct.to_excel(writer, sheet_name="Attainment % Major")

    tests_df.to_excel(writer, index=False, sheet_name="Statistical Tests")

print("✅ Analysis complete!")
print("Workbook saved:", xlsx_path)
print("Plots saved:", plot1, plot2, plot3)
