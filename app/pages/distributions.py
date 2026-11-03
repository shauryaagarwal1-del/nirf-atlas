"""Distributions: the shape and spread of scores (engines: core/engines/univariate.py, distribution.py).

Every univariate and distribution function is one entry of "What do you want to see?", with controls
for all of its parameters (app/explorer.py).
"""

from app.components import page_header
from app.explorer import CATEGORY, SCOPE, TOP_ONLY, YEAR, C, View, explore, top_n, variant

VIEWS = [
    View("Score distribution in one year", "univariate", "score_distribution", (CATEGORY, YEAR, SCOPE)),
    View("How many institutions sit in each rank band", "univariate", "rank_distribution", (CATEGORY, YEAR, SCOPE)),
    View("Average, median, minimum and maximum score", "univariate", "summary_stats", (CATEGORY, YEAR, SCOPE)),
    View("Share of institutions in each score quartile", "univariate", "quartile_shares",
         (CATEGORY, YEAR, variant("mode", "Quartiles", {"score_range": "Fixed ranges 0–25–50–75–100",
                                                        "statistical": "Statistical Q1/Q2/Q3"}, "score_range"),
          SCOPE)),
    View("Top N versus the rest", "distribution", "top10_vs_rest",
         (CATEGORY, YEAR, top_n("top", "Top N group", (3, 5, 10, 15, 20, 25, 50)),
          variant("view", "Chart", {"violin": "Violin", "histogram": "Overlapping histogram"}, "violin"), SCOPE)),
    View("Spread of scores in each year", "distribution", "dispersion_by_year",
         (CATEGORY, TOP_ONLY, variant("view", "Chart", {"box": "Box per year", "sd": "SD line"}, "box"), SCOPE)),
    View("Median and IQR over time", "distribution", "median_iqr_over_time", (CATEGORY, TOP_ONLY, SCOPE)),
    View("Which parameter varies the most", "distribution", "parameter_variability",
         (CATEGORY, YEAR, variant("view", "Chart", {"bar": "CV bars", "box": "Box per parameter"}, "bar"), SCOPE)),
    View("Scores by state", "distribution", "score_by_state",
         (CATEGORY, YEAR, C("choice", "min_institutions", "States with at least … institutions",
                            list(range(1, 11)), 3, widget="slider"), SCOPE)),
    View("Spread of scores across categories (all categories)", "univariate", "spread_by_category",
         (C("year", label="Year"), SCOPE),
         hint="Every category ranked in that year is shown; scores of different categories are on different scales."),
]

page_header("Distributions", "The shape and spread of NIRF scores: histograms, quartiles, box and violin plots, "
            "and how the spread changes between years, groups and states.", eyebrow="Explore · Distributions")
explore("distributions", VIEWS)
