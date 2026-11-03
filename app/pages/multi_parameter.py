"""Multi-Parameter: all five NIRF parameters at once (engine: core/engines/multivariate.py)."""

import streamlit as st

from app.components import page_header, show, year_select
from app.filters import current, parameters_for
from core.data import LABELS

f = current()
page_header("Multi-Parameter", "All five parameters at once: institution profiles, high-on-one-but-low-on-another "
            "gaps, overall gains despite weaker parameters, and the spread between strongest and weakest.",
            eyebrow="Explore · Multivariate", filters=f)

view = st.selectbox("What do you want to see?", [
    "Parameter profile of chosen institutions",
    "High on one parameter, low on another",
    "Overall score rose although a parameter fell",
    "Biggest gap between strongest and weakest parameter",
    "Map of institutions by all parameters (PCA)",
], key="mp-view")
params = parameters_for(f.category) or ["tlr", "rpc"]


def pick(params, label, default, key):
    return st.selectbox(label, params, index=params.index(default) if default in params else 0,
                        format_func=LABELS.get, key=f"{key}-{f.category}")


if view.startswith("Parameter profile"):
    c1, c2, _ = st.columns([1, 1, 2])
    with c1:
        year = year_select(f, key="mp-year")
    with c2:
        v = st.segmented_control("View", ["bar", "heatmap"], default="bar", key="mp-profile-view") or "bar"
    if not f.institutions:
        st.caption("No institutions chosen in the sidebar, so the chart shows the top 5 of that year.")
    show("multivariate", "parameter_profile", key="mp-profile", institutions=list(f.institutions) or None,
         year=year, category=f.category, view=v)
elif view.startswith("High on one"):
    c1, c2, c3, _ = st.columns([1, 1, 1, 1])
    with c1:
        hi = pick(params, "High on", "rpc", "mp-hi")
    with c2:
        lo = pick([p for p in params if p != hi], "Low on", "tlr", f"mp-lo-{hi}")
    with c3:
        year = year_select(f, key="mp-year2")
    show("multivariate", "gap_finder", key="mp-gap", param_high=hi, param_low=lo, year=year, category=f.category)
elif view.startswith("Overall score rose"):
    show("multivariate", "improved_despite_decline", key="mp-despite", category=f.category, start_year=f.start,
         end_year=f.end)
elif view.startswith("Biggest gap"):
    c1, _ = st.columns([1, 3])
    with c1:
        year = year_select(f, key="mp-year3")
    show("multivariate", "strongest_weakest_gap", key="mp-sw", year=year, category=f.category, n=max(f.top_n, 5))
else:
    c1, _ = st.columns([1, 3])
    with c1:
        year = year_select(f, key="mp-year4")
    show("multivariate", "parameter_pca", key="mp-pca", year=year, category=f.category)
