"""Mobility: movement between rank bands and in and out of the top (engine: core/engines/mobility.py)."""

import streamlit as st

from app.components import page_header, show
from app.filters import current

f = current()
page_header("Mobility", "How institutions move: between rank bands from one year to another, in and out of the "
            "top N, and how many moved up, down or stayed each year.", eyebrow="Explore · Rank transitions",
            filters=f, show=("category", "years", "top_n"))

view = st.selectbox("What do you want to see?", [
    f"Moves between rank bands ({f.start} → {f.end})",
    "Entries and exits of the top N",
    "Share that stayed in the same band each year",
    f"Largest climbs and falls ({f.start} → {f.end})",
    "Moved up, down or stayed, each year",
], key=f"mob-view-{f.start}-{f.end}")

if view.startswith("Moves between"):
    show("mobility", "band_transitions", key="mob-bands", category=f.category, year_a=f.start, year_b=f.end)
elif view.startswith("Entries"):
    show("mobility", "top10_entries_exits", key="mob-top", category=f.category, top=f.top_n)
elif view.startswith("Share"):
    by_band = st.toggle("Split by band", key="mob-byband")
    show("mobility", "band_retention", key="mob-retention", category=f.category, by_band=by_band)
elif view.startswith("Largest"):
    show("mobility", "biggest_rank_moves", key="mob-moves", category=f.category, year_a=f.start, year_b=f.end,
         n=f.top_n)
else:
    show("mobility", "up_down_same_counts", key="mob-uds", category=f.category)
