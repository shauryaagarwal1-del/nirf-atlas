"""Distributions: the shape and spread of scores (engines: core/engines/univariate.py, distribution.py)."""

import streamlit as st

from app.components import page_header, show, year_select
from app.filters import current, master

f = current()
page_header("Distributions", "The shape and spread of NIRF scores: histograms, quartiles, box and violin plots, "
            "and how the spread changes between years, groups and states.", eyebrow="Explore · Distributions",
            filters=f, show=("category", "years", "top_n"))

# label -> (engine, function, needs one year)
VIEWS = {
    "Score distribution in one year": ("univariate", "score_distribution", True),
    "How many institutions sit in each rank band": ("univariate", "rank_distribution", True),
    "Average, median, minimum and maximum score": ("univariate", "summary_stats", True),
    "Share of institutions in each score quartile": ("univariate", "quartile_shares", True),
    "Top N versus the rest": ("distribution", "top10_vs_rest", True),
    "Spread of scores in each year": ("distribution", "dispersion_by_year", False),
    "Median and IQR over time": ("distribution", "median_iqr_over_time", False),
    "Which parameter varies the most": ("distribution", "parameter_variability", True),
    "Scores by state": ("distribution", "score_by_state", True),
    "Spread of scores across categories (all categories)": ("univariate", "spread_by_category", True),
}
view = st.selectbox("What do you want to see?", list(VIEWS), key="dist-view")
engine, function, one_year = VIEWS[view]

params = {}
c1, _ = st.columns([1, 3])
if function == "spread_by_category":
    with c1:
        params["year"] = year_select(f, key="dist-year-all", years=sorted(master()["year"].unique().tolist()))
else:
    params["category"] = f.category
    if one_year:
        with c1:
            params["year"] = year_select(f, key="dist-year")
if function == "top10_vs_rest":
    params["top"] = f.top_n
show(engine, function, key=f"dist-{function}", **params)
