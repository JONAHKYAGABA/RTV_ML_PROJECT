"""
RTV Household Predictions -- Comprehensive Data Analysis
========================================================

Exploratory data analysis of 27,525 household records from
Raising the Village (RTV) program evaluation dataset.

Produces:
  - Console report with all key statistics
  - 8 publication-quality PNG figures saved to outputs/figures/

Usage:
    python -m src.analysis.data_analysis
    # or
    python src/analysis/data_analysis.py
"""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path
from typing import Final

import matplotlib
matplotlib.use("Agg")  # non-interactive backend for CI/headless environments

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats

warnings.filterwarnings("ignore", category=FutureWarning)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
DATA_PATH: Final[Path] = PROJECT_ROOT / "Test Data 2026-03-17-12-43.xlsx"
FIGURES_DIR: Final[Path] = PROJECT_ROOT / "outputs" / "figures"

CROP_COLUMNS: Final[list[str]] = [
    "cassava",
    "maize",
    "ground_nuts",
    "irish_potatoes",
    "sweet_potatoes",
    "perennial_crops_grown_food_banana",
]

NUMERIC_COLUMNS: Final[list[str]] = [
    "tot_hhmembers",
    "Land_size_for_Crop_Agriculture_Acres",
    "farm_implements_owned",
    "Average_Water_Consumed_Per_Day",
    "predicted_income",
]

BOOLEAN_COLUMNS: Final[list[str]] = [
    *CROP_COLUMNS,
    "business_participation",
    "vsla_participation",
    "prediction",
]

PALETTE: Final[str] = "viridis"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _section(title: str) -> None:
    """Print a formatted section header."""
    width = 72
    print(f"\n{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}\n")


def _subsection(title: str) -> None:
    """Print a formatted subsection header."""
    print(f"\n--- {title} ---\n")


def _save_figure(fig: plt.Figure, name: str) -> None:
    """Save a matplotlib figure to the outputs directory."""
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURES_DIR / f"{name}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  [saved] {path.relative_to(PROJECT_ROOT)}")


# ---------------------------------------------------------------------------
# 1. Data Loading & Schema Inspection
# ---------------------------------------------------------------------------

def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load the main dataset and column-description sheet."""
    if not DATA_PATH.exists():
        sys.exit(f"ERROR: Data file not found at {DATA_PATH}")

    df = pd.read_excel(DATA_PATH, sheet_name="Test Data")
    desc = pd.read_excel(DATA_PATH, sheet_name="Descriptions")
    return df, desc


def inspect_schema(df: pd.DataFrame, desc: pd.DataFrame) -> None:
    """Print dataset shape, types, null counts, and column descriptions."""
    _section("1. DATASET OVERVIEW")

    print(f"Records : {df.shape[0]:,}")
    print(f"Features: {df.shape[1]}")
    print(f"Memory  : {df.memory_usage(deep=True).sum() / 1e6:.1f} MB")

    _subsection("Column Types")
    dtype_map: dict[str, list[str]] = {}
    for col in df.columns:
        dtype_str = str(df[col].dtype)
        dtype_map.setdefault(dtype_str, []).append(col)
    for dtype_str, cols in sorted(dtype_map.items()):
        print(f"  {dtype_str:>15s}  ({len(cols)}): {', '.join(cols)}")

    _subsection("Null / Missing Values")
    nulls = df.isnull().sum()
    if nulls.sum() == 0:
        print("  No missing values detected -- dataset is fully populated.")
    else:
        print(nulls[nulls > 0].to_string())

    _subsection("Column Descriptions (from 'Descriptions' sheet)")
    for _, row in desc.iterrows():
        col_name = row.iloc[0]
        col_desc = row.iloc[1]
        if pd.notna(col_name):
            print(f"  {col_name:45s}  {col_desc}")


# ---------------------------------------------------------------------------
# 2. Univariate Numeric Analysis
# ---------------------------------------------------------------------------

def analyze_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """Compute extended descriptive statistics for numeric columns."""
    _section("2. NUMERIC FEATURE ANALYSIS")

    records: list[dict] = []
    for col in NUMERIC_COLUMNS:
        s = df[col]
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        iqr = q3 - q1
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        n_outliers = int(((s < lower) | (s > upper)).sum())

        rec = {
            "feature": col,
            "count": int(s.count()),
            "mean": round(s.mean(), 3),
            "std": round(s.std(), 3),
            "min": s.min(),
            "p1": round(s.quantile(0.01), 3),
            "p5": round(s.quantile(0.05), 3),
            "Q1": q1,
            "median": s.median(),
            "Q3": q3,
            "p95": round(s.quantile(0.95), 3),
            "p99": round(s.quantile(0.99), 3),
            "max": s.max(),
            "IQR": iqr,
            "skewness": round(s.skew(), 3),
            "kurtosis": round(s.kurtosis(), 3),
            "outliers": n_outliers,
            "outlier_pct": round(n_outliers / len(s) * 100, 1),
        }
        records.append(rec)

        print(f"  {col}")
        print(f"    Range        : [{rec['min']} .. {rec['max']}]")
        print(f"    Central      : mean={rec['mean']}, median={rec['median']}")
        print(f"    Spread       : std={rec['std']}, IQR={rec['IQR']}")
        print(f"    Shape        : skew={rec['skewness']}, kurtosis={rec['kurtosis']}")
        print(f"    Outliers     : {n_outliers:,} ({rec['outlier_pct']}%)")
        print(f"    Percentiles  : p1={rec['p1']}, p5={rec['p5']}, "
              f"p95={rec['p95']}, p99={rec['p99']}")
        print()

    _subsection("CRITICAL DATA QUALITY NOTES")
    print("  1. farm_implements_owned has EXTREME outliers:")
    print("     max=30,000 vs IQR=[3, 5]. Likely data-entry errors.")
    print("     Recommendation: use PERCENTILE_CONT or clip at p99=12")
    print("     for any aggregate queries.")
    print()
    print("  2. Land_size_for_Crop_Agriculture_Acres: max=99 with")
    print("     skew=9.29 -- probable encoding of 'unknown' as 99.")
    print()
    print("  3. Average_Water_Consumed_Per_Day units are JERRYCANS,")
    print("     not liters (~20L per jerrycan in Uganda).")

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# 3. Categorical / Boolean Analysis
# ---------------------------------------------------------------------------

def analyze_categorical(df: pd.DataFrame) -> None:
    """Distribution analysis for categorical and boolean features."""
    _section("3. CATEGORICAL & BOOLEAN FEATURE ANALYSIS")

    _subsection("Region Distribution")
    region_counts = df["region"].value_counts()
    for region, count in region_counts.items():
        pct = count / len(df) * 100
        print(f"  {region:15s}  {count:>6,}  ({pct:5.1f}%)")

    _subsection("District Distribution (top 10)")
    for dist, count in df["district"].value_counts().head(10).items():
        pct = count / len(df) * 100
        print(f"  {dist:15s}  {count:>6,}  ({pct:5.1f}%)")
    print(f"  ... and {df['district'].nunique() - 10} more districts")

    _subsection("Cohort Distribution")
    for cohort, count in df["cohort"].value_counts().sort_index().items():
        pct = count / len(df) * 100
        print(f"  {cohort}  {count:>6,}  ({pct:5.1f}%)")

    _subsection("Cycle Distribution")
    for cycle, count in df["cycle"].value_counts().items():
        pct = count / len(df) * 100
        print(f"  {cycle}     {count:>6,}  ({pct:5.1f}%)")

    _subsection("Evaluation Month Distribution")
    for month, count in df["evaluation_month"].value_counts().sort_index().items():
        pct = count / len(df) * 100
        print(f"  Month {month:>2d}  {count:>6,}  ({pct:5.1f}%)")

    _subsection("Crop Adoption Rates")
    for col in CROP_COLUMNS:
        n = int(df[col].sum())
        pct = n / len(df) * 100
        bar = "#" * int(pct / 2)
        print(f"  {col:45s}  {n:>6,}  ({pct:5.1f}%)  {bar}")

    _subsection("Program Participation")
    for col in ["business_participation", "vsla_participation"]:
        n = int(df[col].sum())
        pct = n / len(df) * 100
        print(f"  {col:30s}  {n:>6,}  ({pct:5.1f}%)")

    _subsection("Prediction Target Distribution")
    for val, count in df["prediction"].value_counts().items():
        pct = count / len(df) * 100
        label = "Will hit target" if val else "Will NOT hit target"
        print(f"  {label:25s}  {count:>6,}  ({pct:5.1f}%)")

    _subsection("Household ID Structure")
    parts = df["household_id"].str.split("-")
    part_counts = parts.str.len().value_counts().sort_index()
    print("  Format: DIST-VILLAGE-NAME-GENDER-NUM-MEMBERS")
    print(f"  Sample : {df['household_id'].iloc[0]}")
    for n_parts, count in part_counts.items():
        print(f"  {n_parts} parts: {count:,} records ({count/len(df)*100:.1f}%)")

    _subsection("Date Range")
    print(f"  Collection dates : {df['date'].min()} to {df['date'].max()}")
    print(f"  Distinct dates   : {df['date'].nunique()}")
    print(f"  Database created : {df['created_at'].iloc[0][:10]}")


# ---------------------------------------------------------------------------
# 4. Correlation & Cross-Tab Analysis
# ---------------------------------------------------------------------------

def analyze_correlations(df: pd.DataFrame) -> pd.DataFrame:
    """Correlation matrix and cross-tabulations."""
    _section("4. CORRELATION & CROSS-TABULATION ANALYSIS")

    _subsection("Pearson Correlation Matrix (Numeric Features)")
    corr = df[NUMERIC_COLUMNS].corr().round(3)
    print(corr.to_string())

    _subsection("Key Correlation Insights")
    print("  - tot_hhmembers <-> Average_Water_Consumed_Per_Day: r=0.523 (strong)")
    print("    Larger households consume more water -- expected.")
    print("  - Land_size <-> tot_hhmembers: r=0.232 (moderate)")
    print("    More members -> more land cultivated.")
    print("  - Land_size <-> predicted_income: r=0.214 (moderate)")
    print("    Land area is a meaningful income predictor.")
    print("  - farm_implements_owned is UNCORRELATED with everything")
    print("    (r ~ 0.00) -- outliers dominate the variance.")

    _subsection("Prediction Rate by Region")
    ct = pd.crosstab(df["region"], df["prediction"], normalize="index").round(3)
    ct.columns = ["Will NOT hit target", "Will hit target"]
    print(ct.to_string())

    _subsection("Predicted Income by Region")
    inc_by_region = (
        df.groupby("region")["predicted_income"]
        .agg(["mean", "median", "std", "count"])
        .sort_values("mean", ascending=False)
        .round(3)
    )
    print(inc_by_region.to_string())

    _subsection("Predicted Income by District (top 10 & bottom 5)")
    inc_by_dist = (
        df.groupby("district")["predicted_income"]
        .agg(["mean", "median", "std", "count"])
        .sort_values("mean", ascending=False)
        .round(3)
    )
    print("Top 10:")
    print(inc_by_dist.head(10).to_string())
    print("\nBottom 5:")
    print(inc_by_dist.tail(5).to_string())

    _subsection("Crop Adoption by Region (% of households)")
    crop_by_region = df.groupby("region")[CROP_COLUMNS].mean().round(3) * 100
    print(crop_by_region.to_string())

    return corr


# ---------------------------------------------------------------------------
# 5. Statistical Tests
# ---------------------------------------------------------------------------

def run_statistical_tests(df: pd.DataFrame) -> None:
    """Hypothesis tests relevant to the dataset."""
    _section("5. STATISTICAL TESTS")

    _subsection("5a. Income Difference: Prediction=True vs False (Welch t-test)")
    income_true = df.loc[df["prediction"], "predicted_income"]
    income_false = df.loc[~df["prediction"], "predicted_income"]
    t_stat, p_val = stats.ttest_ind(income_true, income_false, equal_var=False)
    print(f"  Mean (True) : {income_true.mean():.3f}")
    print(f"  Mean (False): {income_false.mean():.3f}")
    print(f"  t-statistic : {t_stat:.3f}")
    print(f"  p-value     : {p_val:.2e}")
    print(f"  Effect size (Cohen's d): "
          f"{(income_true.mean() - income_false.mean()) / df['predicted_income'].std():.3f}")
    print(f"  Conclusion  : {'Significant' if p_val < 0.05 else 'Not significant'} "
          f"at alpha=0.05")

    _subsection("5b. Income Across Regions (Kruskal-Wallis)")
    groups = [g["predicted_income"].values for _, g in df.groupby("region")]
    h_stat, p_val = stats.kruskal(*groups)
    print(f"  H-statistic : {h_stat:.3f}")
    print(f"  p-value     : {p_val:.2e}")
    print(f"  Conclusion  : {'Significant' if p_val < 0.05 else 'Not significant'} "
          f"regional differences at alpha=0.05")

    _subsection("5c. Business Participation & Income (Welch t-test)")
    biz_yes = df.loc[df["business_participation"], "predicted_income"]
    biz_no = df.loc[~df["business_participation"], "predicted_income"]
    t_stat, p_val = stats.ttest_ind(biz_yes, biz_no, equal_var=False)
    print(f"  Mean (Business=Yes): {biz_yes.mean():.3f}")
    print(f"  Mean (Business=No) : {biz_no.mean():.3f}")
    print(f"  t-statistic        : {t_stat:.3f}")
    print(f"  p-value            : {p_val:.2e}")

    _subsection("5d. Normality Test -- Predicted Income (D'Agostino-Pearson)")
    k2, p_val = stats.normaltest(df["predicted_income"])
    print(f"  k2 statistic: {k2:.3f}")
    print(f"  p-value     : {p_val:.2e}")
    print(f"  Conclusion  : {'Normal' if p_val > 0.05 else 'Non-normal'} distribution")


# ---------------------------------------------------------------------------
# 6. Geographic Analysis
# ---------------------------------------------------------------------------

def analyze_geography(df: pd.DataFrame) -> None:
    """Geographic hierarchy and coverage analysis."""
    _section("6. GEOGRAPHIC COVERAGE")

    _subsection("Hierarchy: Region -> District -> Cluster -> Village")
    print(f"  Regions   : {df['region'].nunique()}")
    print(f"  Districts : {df['district'].nunique()}")
    print(f"  Clusters  : {df['cluster'].nunique()}")
    print(f"  Villages  : {df['village'].nunique()}")
    print(f"  Households: {df['household_id'].nunique()} unique IDs "
          f"({len(df)} total records)")

    _subsection("Districts per Region")
    for region in df["region"].unique():
        districts = df.loc[df["region"] == region, "district"].unique()
        print(f"  {region} ({len(districts)}): {', '.join(sorted(districts))}")

    _subsection("Villages per District (top 10)")
    vpd = df.groupby("district")["village"].nunique().sort_values(ascending=False)
    for dist, n in vpd.head(10).items():
        print(f"  {dist:15s}  {n:>3d} villages")

    _subsection("Clusters per District (top 10)")
    cpd = df.groupby("district")["cluster"].nunique().sort_values(ascending=False)
    for dist, n in cpd.head(10).items():
        print(f"  {dist:15s}  {n:>3d} clusters")

    _subsection("Duplicate Household IDs (multi-cycle records)")
    dup_ids = df["household_id"].value_counts()
    multi = dup_ids[dup_ids > 1]
    print(f"  Unique household_ids  : {df['household_id'].nunique():,}")
    print(f"  IDs appearing >1 time : {len(multi):,}")
    print(f"  Max appearances       : {multi.max()}")
    if len(multi) > 0:
        print(f"  These represent households evaluated across multiple cycles.")


# ---------------------------------------------------------------------------
# 7. Visualizations
# ---------------------------------------------------------------------------

def create_visualizations(df: pd.DataFrame) -> None:
    """Generate all analysis figures."""
    _section("7. GENERATING VISUALIZATIONS")

    sns.set_theme(style="whitegrid", palette=PALETTE, font_scale=1.1)

    # ---- Figure 1: Income Distribution ----
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    axes[0].hist(df["predicted_income"], bins=60, color="#2196F3", edgecolor="white",
                 alpha=0.85)
    axes[0].axvline(df["predicted_income"].mean(), color="red", ls="--", lw=1.5,
                    label=f"Mean = {df['predicted_income'].mean():.2f}")
    axes[0].axvline(df["predicted_income"].median(), color="orange", ls="--", lw=1.5,
                    label=f"Median = {df['predicted_income'].median():.2f}")
    axes[0].set_xlabel("Predicted Income + Production Value")
    axes[0].set_ylabel("Frequency")
    axes[0].set_title("Distribution of Predicted Income")
    axes[0].legend(fontsize=9)

    df.boxplot(column="predicted_income", by="prediction", ax=axes[1],
               patch_artist=True,
               boxprops=dict(facecolor="#2196F3", alpha=0.6),
               medianprops=dict(color="red", lw=2))
    axes[1].set_title("Predicted Income by Target Prediction")
    axes[1].set_xlabel("Prediction (False=0, True=1)")
    axes[1].set_ylabel("Predicted Income")
    plt.suptitle("")
    fig.tight_layout()
    _save_figure(fig, "01_income_distribution")

    # ---- Figure 2: Income by Region ----
    fig, ax = plt.subplots(figsize=(12, 6))
    order = (df.groupby("region")["predicted_income"].median()
             .sort_values(ascending=False).index)
    sns.boxplot(data=df, x="region", y="predicted_income", order=order, ax=ax,
                palette="viridis", showfliers=False)
    ax.set_title("Predicted Income Distribution by Region")
    ax.set_xlabel("Region")
    ax.set_ylabel("Predicted Income")
    fig.tight_layout()
    _save_figure(fig, "02_income_by_region")

    # ---- Figure 3: Income by District (top 15) ----
    fig, ax = plt.subplots(figsize=(14, 7))
    top_districts = df.groupby("district")["predicted_income"].median().nlargest(15).index
    sns.boxplot(data=df[df["district"].isin(top_districts)],
                x="district", y="predicted_income",
                order=top_districts, ax=ax, palette="viridis", showfliers=False)
    ax.set_title("Predicted Income by District (Top 15 by Median)")
    ax.set_xlabel("District")
    ax.set_ylabel("Predicted Income")
    plt.xticks(rotation=45, ha="right")
    fig.tight_layout()
    _save_figure(fig, "03_income_by_district")

    # ---- Figure 4: Crop Adoption Heatmap by Region ----
    fig, ax = plt.subplots(figsize=(10, 5))
    crop_pct = df.groupby("region")[CROP_COLUMNS].mean() * 100
    crop_pct.columns = [c.replace("_", " ").replace("perennial crops grown food banana",
                         "banana (perennial)").title() for c in crop_pct.columns]
    sns.heatmap(crop_pct, annot=True, fmt=".1f", cmap="YlGn", ax=ax,
                linewidths=0.5, cbar_kws={"label": "% of Households"})
    ax.set_title("Crop Adoption Rates by Region (%)")
    ax.set_ylabel("")
    fig.tight_layout()
    _save_figure(fig, "04_crop_adoption_heatmap")

    # ---- Figure 5: Correlation Heatmap ----
    fig, ax = plt.subplots(figsize=(8, 6))
    corr = df[NUMERIC_COLUMNS].corr()
    mask = np.triu(np.ones_like(corr, dtype=bool))
    short_labels = ["HH Members", "Land (Acres)", "Farm Implements",
                    "Water (Jerrycans)", "Predicted Income"]
    sns.heatmap(corr, mask=mask, annot=True, fmt=".2f", cmap="coolwarm",
                center=0, ax=ax, xticklabels=short_labels,
                yticklabels=short_labels, linewidths=0.5)
    ax.set_title("Feature Correlation Matrix")
    fig.tight_layout()
    _save_figure(fig, "05_correlation_heatmap")

    # ---- Figure 6: Household Size & Water Consumption ----
    fig, ax = plt.subplots(figsize=(10, 6))
    # Jitter plot with alpha for density
    jitter_x = df["tot_hhmembers"] + np.random.normal(0, 0.15, len(df))
    jitter_y = df["Average_Water_Consumed_Per_Day"] + np.random.normal(0, 0.15, len(df))
    ax.scatter(jitter_x, jitter_y, alpha=0.05, s=5, c="#2196F3")
    # Trend line
    z = np.polyfit(df["tot_hhmembers"], df["Average_Water_Consumed_Per_Day"], 1)
    x_line = np.linspace(0, 20, 100)
    ax.plot(x_line, np.polyval(z, x_line), "r--", lw=2,
            label=f"Trend: y = {z[0]:.2f}x + {z[1]:.2f}")
    ax.set_xlabel("Total Household Members")
    ax.set_ylabel("Average Water Consumed (Jerrycans/Day)")
    ax.set_title("Household Size vs Water Consumption (r=0.52)")
    ax.legend()
    fig.tight_layout()
    _save_figure(fig, "06_hh_size_vs_water")

    # ---- Figure 7: Prediction Rate by Region ----
    fig, ax = plt.subplots(figsize=(10, 5))
    pred_rate = df.groupby("region")["prediction"].mean().sort_values(ascending=False)
    bars = ax.barh(pred_rate.index, pred_rate.values * 100, color="#4CAF50",
                   edgecolor="white")
    ax.axvline(50, color="red", ls="--", lw=1, alpha=0.7, label="50% threshold")
    ax.set_xlabel("% Predicted to Hit Target")
    ax.set_title("Prediction Success Rate by Region")
    ax.xaxis.set_major_formatter(mtick.PercentFormatter())
    for bar, val in zip(bars, pred_rate.values):
        ax.text(val * 100 + 0.5, bar.get_y() + bar.get_height() / 2,
                f"{val*100:.1f}%", va="center", fontsize=10)
    ax.legend()
    fig.tight_layout()
    _save_figure(fig, "07_prediction_rate_by_region")

    # ---- Figure 8: Feature Distributions Grid ----
    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    axes = axes.ravel()

    for i, col in enumerate(NUMERIC_COLUMNS):
        ax = axes[i]
        # Clip extreme outliers for visualization
        data = df[col].clip(upper=df[col].quantile(0.99))
        ax.hist(data, bins=40, color="#2196F3", edgecolor="white", alpha=0.85)
        ax.axvline(data.mean(), color="red", ls="--", lw=1.2)
        ax.set_title(col.replace("_", " ").title(), fontsize=10)
        ax.set_ylabel("Frequency")

    # Participation rates in last subplot
    ax = axes[5]
    participation = {
        "VSLA": df["vsla_participation"].mean() * 100,
        "Business": df["business_participation"].mean() * 100,
    }
    bars = ax.bar(participation.keys(), participation.values(),
                  color=["#4CAF50", "#FF9800"], edgecolor="white")
    for bar, val in zip(bars, participation.values()):
        ax.text(bar.get_x() + bar.get_width() / 2, val + 1,
                f"{val:.1f}%", ha="center", fontsize=11, fontweight="bold")
    ax.set_ylim(0, 100)
    ax.set_title("Program Participation Rates")
    ax.set_ylabel("% of Households")

    fig.suptitle("Feature Distributions (clipped at p99 for visibility)",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    _save_figure(fig, "08_feature_distributions")

    print(f"\n  All {8} figures saved to {FIGURES_DIR.relative_to(PROJECT_ROOT)}/")


# ---------------------------------------------------------------------------
# 8. Summary & SQL-Readiness Assessment
# ---------------------------------------------------------------------------

def print_summary(df: pd.DataFrame) -> None:
    """Final summary with SQL-readiness notes."""
    _section("8. SUMMARY & SQL-READINESS ASSESSMENT")

    print("  Dataset Summary:")
    print(f"    - 27,525 household evaluation records from 22 districts")
    print(f"    - 5 regions across Uganda (South West dominant: 51.5%)")
    print(f"    - 3 cohorts (2023, 2024, 2025); 2 cycles (A, B)")
    print(f"    - No missing values -- clean dataset")
    print(f"    - 26,068 unique household IDs (some appear in multiple cycles)")
    print()
    print("  Key Findings:")
    print("    1. Predicted income ranges from 0.52 to 5.39 (median=1.83)")
    print("    2. South West has highest income (mean=2.08) and prediction rate (59.7%)")
    print("    3. East has lowest income (mean=1.52) and prediction rate (29.2%)")
    print("    4. VSLA participation is near-universal (93.1%)")
    print("    5. Business participation is moderate (41.9%)")
    print("    6. Maize is most common crop (51.9%), ground nuts least (14.9%)")
    print("    7. Household size strongly correlates with water consumption (r=0.52)")
    print("    8. farm_implements_owned has extreme outliers -- use percentiles")
    print()
    print("  SQL Agent Considerations:")
    print("    - Use DuckDB for OLAP-style analytical queries")
    print("    - household_id is STRING type (structured: DIST-VILLAGE-NAME-GENDER-NUM)")
    print("    - Boolean columns stored as true/false (DuckDB BOOLEAN)")
    print("    - predicted_income is FLOAT -- use ROUND() for display")
    print("    - farm_implements_owned: always use PERCENTILE_CONT or WHERE < 100")
    print("    - Average_Water_Consumed_Per_Day: units are JERRYCANS (not liters)")
    print("    - date column: only 3 distinct dates (2024-11, 2025-01, 2025-06)")
    print()
    print("  RAG Pipeline Considerations:")
    print("    - Crop columns map directly to Agriculture Handbook topics")
    print("    - Regional crop patterns inform context for hybrid queries")
    print("    - Prediction target (54.3% True) suggests balanced classification")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the complete data analysis pipeline."""
    print("=" * 72)
    print("  RAISING THE VILLAGE -- HOUSEHOLD PREDICTIONS DATA ANALYSIS")
    print("  Dataset: Test Data 2026-03-17-12-43.xlsx")
    print("  Records: 27,525 | Features: 25")
    print("=" * 72)

    df, desc = load_data()
    inspect_schema(df, desc)
    stats_df = analyze_numeric(df)
    analyze_categorical(df)
    corr = analyze_correlations(df)
    run_statistical_tests(df)
    analyze_geography(df)
    create_visualizations(df)
    print_summary(df)

    # Export stats summary to CSV
    output_dir = PROJECT_ROOT / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    stats_df.to_csv(output_dir / "numeric_statistics.csv", index=False)
    corr.to_csv(output_dir / "correlation_matrix.csv")
    print(f"\n  Exported: outputs/numeric_statistics.csv, outputs/correlation_matrix.csv")
    print("\n  Analysis complete.")


if __name__ == "__main__":
    main()
