"""Relationships: how two NIRF numbers move together (engine: core/engines/bivariate.py)."""

import streamlit as st

from app.components import page_header, show, year_select
from app.filters import current, parameters_for
from core.data import LABELS

COLOR_BY = {None: "Nothing", "region": "Region", "state": "State", "rank_band": "Rank band"}

f = current()
page_header("Relationships", "How two NIRF numbers move together: a scatterplot with its trend line, the "
            "correlation of every parameter with the overall score, and how a correlation changed over time.",
            eyebrow="Explore · Correlation", filters=f, show=("category", "years"))

view = st.selectbox("What do you want to see?", [
    "Any two numbers against each other",
    "Which parameter is most linked to the overall score",
    "How one parameter's link to the overall score changed",
], key="rel-view")
params = parameters_for(f.category)
numbers = ["score"] + params + ["rank"]

if not params:
    st.caption(f"NIRF published no parameter scores for {f.category}, so only rank and score can be compared.")

if view.startswith("Any two"):
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        x = st.selectbox("X axis", numbers, index=numbers.index("rpc") if "rpc" in numbers else 0,
                         format_func=LABELS.get, key=f"rel-x-{f.category}")
    with c2:
        y = st.selectbox("Y axis", numbers, index=0, format_func=LABELS.get, key=f"rel-y-{f.category}")
    with c3:
        year = year_select(f, key="rel-year")
    with c4:
        color = st.selectbox("Colour by", list(COLOR_BY), format_func=COLOR_BY.get, key="rel-color")
    show("bivariate", "scatter_relation", key="rel-scatter", x=x, y=y, year=year, category=f.category,
         color_by=color)
elif view.startswith("Which parameter"):
    c1, c2, _ = st.columns([1, 1, 2])
    with c1:
        year = year_select(f, key="rel-year2")
    with c2:
        v = st.segmented_control("View", ["correlogram", "bar"], default="correlogram", key="rel-corr-view")
    show("bivariate", "correlation_with_overall", key="rel-corr", year=year, category=f.category,
         view=v or "correlogram")
else:
    c1, _ = st.columns([1, 3])
    with c1:
        p = st.selectbox("Parameter", params or ["rpc"], index=params.index("rpc") if "rpc" in params else 0,
                         format_func=LABELS.get, key=f"rel-param-{f.category}")
    show("bivariate", "correlation_over_time", key="rel-time", param=p, category=f.category)
