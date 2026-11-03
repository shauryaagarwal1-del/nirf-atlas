"""Outliers: institutions that break the pattern (engine: core/engines/outliers.py)."""

import streamlit as st

from app.components import page_header, show, year_select
from app.filters import current, parameters_for
from core.data import LABELS

f = current()
page_header("Outliers", "Institutions that break the pattern: a parameter far above what the overall score "
            "predicts, unusual year-to-year jumps, strong parameters with weak ranks, and unstable ranks.",
            eyebrow="Explore · Outliers & gaps", filters=f, show=("category", "years", "top_n"))

view = st.selectbox("What do you want to see?", [
    "A parameter unusually high for the overall score",
    "Research much stronger than teaching",
    "Unusually large year-to-year score changes",
    "Strong parameter, relatively poor rank",
    "Unusually volatile ranks compared with peers",
], key="out-view")
params = parameters_for(f.category) or ["rpc"]


def pick(label, default, key):
    return st.selectbox(label, params, index=params.index(default) if default in params else 0,
                        format_func=LABELS.get, key=f"{key}-{f.category}")


if view.startswith("A parameter"):
    c1, c2, _ = st.columns([1, 1, 2])
    with c1:
        p = pick("Parameter", "rpc", "out-p1")
    with c2:
        year = year_select(f, key="out-year1")
    show("outliers", "research_vs_overall_outliers", key="out-resid", year=year, category=f.category, param=p)
elif view.startswith("Research much"):
    c1, _ = st.columns([1, 3])
    with c1:
        year = year_select(f, key="out-year2")
    show("outliers", "research_over_teaching", key="out-rvt", year=year, category=f.category, n=max(f.top_n, 5))
elif view.startswith("Unusually large"):
    show("outliers", "unusual_score_jumps", key="out-jumps", category=f.category)
elif view.startswith("Strong parameter"):
    c1, c2, _ = st.columns([1, 1, 2])
    with c1:
        p = pick("Parameter", "go", "out-p2")
    with c2:
        year = year_select(f, key="out-year3")
    show("outliers", "strong_param_poor_rank", key="out-strong", param=p, year=year, category=f.category)
else:
    show("outliers", "volatility_vs_peers", key="out-vol", category=f.category)
