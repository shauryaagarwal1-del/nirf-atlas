"""Trends: how ranks and scores changed over the years (engine: core/engines/trends.py)."""

import streamlit as st

from app.components import page_header, show
from app.filters import category_years_map, current

f = current()
page_header("Trends", "How ranks and scores moved over time: one institution's path, the biggest climbers and "
            "fallers, the average score each year, and who stayed at the top.", eyebrow="Explore · Time series",
            filters=f)

view = st.selectbox("What do you want to see?", [
    "Rank of chosen institutions, year by year",
    "Biggest climbers between the first and last year",
    "Biggest fallers between the first and last year",
    "Average score per year",
    "Who stayed in the top N",
    "Today's top N, followed back in time",
], key="trends-view")

if view.startswith("Rank of"):
    if not f.institutions:
        st.caption("No institutions chosen in the sidebar, so the chart shows the top 5 of the last year.")
    show("trends", "rank_trajectory", key="trends-traj", category=f.category, years=f.years,
         institutions=list(f.institutions) or None)
elif view.startswith("Biggest climbers"):
    show("trends", "biggest_movers", key="trends-up", category=f.category, start_year=f.start, end_year=f.end,
         direction="up", n=f.top_n)
elif view.startswith("Biggest fallers"):
    show("trends", "biggest_movers", key="trends-down", category=f.category, start_year=f.start, end_year=f.end,
         direction="down", n=f.top_n)
elif view.startswith("Average"):
    stat = st.segmented_control("Statistic", ["mean", "median"], default="mean", key="trends-stat") or "mean"
    show("trends", "average_score_over_time", key="trends-avg", categories=f.category, stat=stat)
elif view.startswith("Who stayed"):
    years = len(category_years_map()[f.category])  # this chart always uses every published year
    min_years = st.slider("At least this many years in the top N", 1, years, min(5, years), key=f"trends-min-{years}")
    show("trends", "consistent_top_n", key="trends-consistent", category=f.category, n=f.top_n, min_years=min_years)
else:
    show("trends", "top_n_race", key="trends-race", category=f.category, years=f.years, n=max(2, min(f.top_n, 20)))
