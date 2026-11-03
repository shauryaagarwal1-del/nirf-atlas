"""Geography: where the ranked institutions are and how the map changes (engine: core/engines/geography.py)."""

import streamlit as st

from app.components import page_header, show, year_select
from app.filters import current

DEFAULT_STATES = ["Karnataka", "Tamil Nadu"]
TOP_LISTS = [10, 25, 50, 100, 150, 200]

f = current()
page_header("Geography", "Which states hold the top places, how their share changes over the years, and how "
            "two or more states compare.", eyebrow="Explore · Regions", filters=f)

view = st.selectbox("What do you want to see?", [
    "States with the most institutions in the top list",
    "Each state's share of the top list over time",
    "States that gained or lost places in the top list",
    "Compare the ranks of chosen states",
    "States with the most new entrants",
], key="geo-view")

top = 100
c1, c2, _ = st.columns([1, 1, 2])
if view.startswith(("States with the most inst", "Each state", "States that")):
    with c1:
        top = st.select_slider("Top list", TOP_LISTS, value=100, key="geo-top",
                               help="Count institutions certainly ranked within this many places.")

if view.startswith("States with the most inst"):
    with c2:
        year = year_select(f, key="geo-year")
    show("geography", "state_counts", key="geo-counts", year=year, category=f.category, top_n=top)
elif view.startswith("Each state"):
    show("geography", "state_share_over_time", key="geo-share", category=f.category, top_n=top)
elif view.startswith("States that"):
    show("geography", "state_representation_change", key="geo-change", category=f.category, start_year=f.start,
         end_year=f.end, top_n=top)
elif view.startswith("Compare"):
    if not f.states:
        st.caption("No states chosen in the sidebar, so the chart compares Karnataka and Tamil Nadu.")
    show("geography", "compare_states", key="geo-compare", states=list(f.states[:8]) or DEFAULT_STATES,
         category=f.category, years=f.years)
else:
    show("geography", "new_entrants_by_state", key="geo-new", category=f.category, years=f.years)
