"""Chart Builder: the safety net for unusual questions. Pick filters, then X, Y, colour, facet,
aggregation and an allowed chart type, and get a chart (logic: core/builder.py).

How the page works:
  1. Filters: categories, years, states, regions, institutions and a rank cut-off. They start from the
     global filters when the page opens and are then the page's own. The institution list offers only
     institutions listed in the chosen categories.
  2. Chart: chart type, X, Y, aggregation, colour (group), facet, and bubble size. Controls the chosen
     chart type does not use are greyed out, so only sensible choices remain.
  3. Combinations that still cannot make a chart (a pie of averages, a line over states ...) show a
     friendly hint saying what to change instead of an error.
Quick starts fill in a ready combination, as a starting point to change.
"""

from __future__ import annotations

import streamlit as st

from app.components import chart_card, empty_state, page_header
from app.filters import category_years_map, current, institution_options, master, prune_institutions, state_options
from core.builder import AGGREGATIONS, CHARTS, DIMENSIONS, MEASURES, BuilderHint, build_chart, uses
from core.data import YEARS
from core.result import ChartResult

K = "cb-"   # widget key prefix
# 0 = no limit (a selectbox shows a stored None as "nothing chosen", so 0 stands for "all").
RANK_CUTS = {0: "All ranks", 10: "Top 10", 25: "Top 25", 50: "Top 50", 100: "Top 100", 150: "Top 150",
             200: "Top 200"}
NONE = "(none)"
QUICK = {
    "Institutions per state": dict(chart="bar", x="state", agg="count", color=NONE, facet=NONE),
    "State × year heatmap": dict(chart="heatmap", x="year", agg="count", color="state", facet=NONE, rank=100),
    "Scores by region": dict(chart="box", x="region", y="score", color=NONE, facet=NONE),
    "TLR vs RPC bubbles": dict(chart="bubble", x="tlr", y="rpc", size="pr", color="region", facet=NONE),
    "Average PR over time": dict(chart="line", x="year", y="pr", agg="mean", color=NONE, facet=NONE),
    "Share by region": dict(chart="pie", x="region", agg="count", color=NONE, facet=NONE, rank=100),
    "New entrants per year": dict(chart="stacked_bar", x="year", agg="count", color="new_entrant", facet=NONE),
}
LIMITS = {0: "All", 5: "Top 5", 10: "Top 10", 15: "Top 15", 20: "Top 20", 30: "Top 30"}


def _init() -> None:
    """First visit (or back from another page): start from the sidebar filters and a simple bar chart."""
    if f"{K}chart" in st.session_state:
        return
    f = current()
    st.session_state.update({
        f"{K}categories": [f.category], f"{K}from": f.start, f"{K}to": f.end, f"{K}states": list(f.states),
        f"{K}regions": [], f"{K}institutions": list(f.institutions), f"{K}rank": 0,
        f"{K}chart": "bar", f"{K}x": "state", f"{K}y": "score", f"{K}agg": "count", f"{K}color": NONE,
        f"{K}facet": NONE, f"{K}size": "pr", f"{K}limit": 0,
    })


def _quick(name: str) -> None:
    spec = QUICK[name]
    st.session_state[f"{K}rank"] = 0
    st.session_state[f"{K}limit"] = 0
    for k, v in spec.items():
        st.session_state[f"{K}{k}"] = v


def _clamp(key: str, options: list, fallback) -> None:
    """Keep a stored choice valid when its options change (e.g. fewer years after a category change)."""
    if st.session_state.get(key) not in options:
        st.session_state[key] = fallback


def _var_label(v: str) -> str:
    if v == NONE:
        return "(none)"
    return f"{DIMENSIONS[v]} · group" if v in DIMENSIONS else f"{MEASURES[v]} · number"


@st.cache_data(show_spinner=False, max_entries=256)
def _build(spec: tuple) -> tuple[ChartResult | None, str | None]:
    try:
        return build_chart(**dict(spec)), None
    except BuilderHint as e:
        return None, str(e)


_init()
page_header("Chart Builder", "For a question no page answers yet: choose the filters, then X, Y, a colour, a "
            "facet, an aggregation and a chart type from the course list, and get a chart with its answer, "
            "method and data.", eyebrow="Build & ask · Any chart")

st.caption("Quick starts (then change anything):")
with st.container(horizontal=True, gap="small", key=f"{K}quick"):
    for name in QUICK:
        st.button(name, key=f"{K}q-{name}", on_click=_quick, args=(name,), icon=":material/bolt:")

cats = category_years_map()
df = master()
with st.container(border=True, key=f"{K}filters"):
    st.html("<div class='nirf-eyebrow'>1 · Filters</div>")
    c = st.columns(4, gap="small")
    with c[0]:
        chosen = st.multiselect("Categories", list(cats), key=f"{K}categories", placeholder="All categories",
                                help="Empty = every category. Scores of different categories are on different "
                                     "scales of meaning.")
    years = sorted({y for k in (chosen or cats) for y in cats[k]}) or YEARS
    _clamp(f"{K}from", years, years[0])
    _clamp(f"{K}to", years, years[-1])
    with c[1]:
        y_from = st.selectbox("From year", years, key=f"{K}from")
    with c[2]:
        y_to = st.selectbox("To year", years, key=f"{K}to")
    with c[3]:
        rank_max = st.selectbox("Rank cut-off", list(RANK_CUTS), format_func=RANK_CUTS.get, key=f"{K}rank",
                                help="Top 100 = rows certainly ranked 1-100 (a 101-150 band is left out).")
    c = st.columns(4, gap="small")
    with c[0]:
        states = st.multiselect("States", state_options(), key=f"{K}states", placeholder="All states")
    with c[1]:
        regions = st.multiselect("Regions", sorted(df["region"].dropna().unique()), key=f"{K}regions",
                                 placeholder="All regions")
    with c[2]:   # only institutions listed in the chosen categories (all, when none is chosen)
        opts = institution_options(chosen or None)
        listed_in = " or ".join(chosen) if chosen else "any category"
        note = prune_institutions(f"{K}institutions", opts, listed_in)
        insts = st.multiselect("Institutions", list(opts), key=f"{K}institutions", format_func=lambda k: opts[k],
                               placeholder="All institutions",
                               help=f"Institutions listed in {listed_in}. 'band only' = never given an exact rank "
                                    "there." if chosen else None)
        if note:
            st.caption(note)

chart_keys = list(CHARTS)
dims, nums = list(DIMENSIONS), list(MEASURES)
with st.container(border=True, key=f"{K}spec"):
    st.html("<div class='nirf-eyebrow'>2 · Chart</div>")
    c = st.columns(4, gap="small")
    with c[0]:
        chart = st.selectbox("Chart type", chart_keys, format_func=lambda k: CHARTS[k][0], key=f"{K}chart",
                             help="Only chart types from the course list.")
    u = uses(chart)
    x_options = dims + nums if u["x_kind"] == "dimension" else nums + dims
    _clamp(f"{K}x", x_options, x_options[0])
    with c[1]:
        x = st.selectbox("X axis", x_options, format_func=_var_label, key=f"{K}x",
                         help="Groups (year, state ...) for bar, line, box, violin, strip, heatmap and pie; a "
                              "number for scatter, bubble and histogram.")
    agg_used = u["agg"]
    with c[3]:
        agg = st.selectbox("Aggregation", list(AGGREGATIONS), format_func=AGGREGATIONS.get, key=f"{K}agg",
                           disabled=not agg_used,
                           help="Count = number of distinct institutions; mean, median, min, max of the Y number."
                           if agg_used else f"Not used: a {CHARTS[chart][0].lower()} draws every institution.")
    y_used = u["y"] and not (agg_used and agg == "count")
    with c[2]:
        y = st.selectbox("Y axis", nums, format_func=_var_label, key=f"{K}y", disabled=not y_used,
                         help="The number to summarise or plot." if y_used else
                         ("Not used with Count." if agg_used else f"Not used by a {CHARTS[chart][0].lower()}."))
    c = st.columns(4, gap="small")
    with c[0]:
        color_label = "Rows (second group)" if chart == "heatmap" else "Colour / group"
        color = st.selectbox(color_label, [NONE] + dims, format_func=_var_label, key=f"{K}color",
                             disabled=not u["colour"],
                             help="Required." if u["colour_required"] else
                             ("Not used by a pie chart." if not u["colour"] else "Optional second grouping."))
    with c[1]:
        facet = st.selectbox("Facet (small multiples)", [NONE] + dims, format_func=_var_label, key=f"{K}facet",
                             disabled=not u["facet"],
                             help="One small chart per group." if u["facet"] else "Not available for this chart.")
    with c[2]:
        size = st.selectbox("Bubble size", nums, format_func=_var_label, key=f"{K}size", disabled=not u["size"],
                            help="Bubble area shows this number." if u["size"] else "Only for a bubble chart.")
    with c[3]:
        limit = st.selectbox("Show groups", list(LIMITS), format_func=LIMITS.get, key=f"{K}limit",
                             disabled=not u["limit"],
                             help="Only the X groups with the largest values (the best, for rank)." if u["limit"]
                             else "Only for bar charts.")

if y_from > y_to:
    with st.container(border=True, key="card-builder-hint"):
        empty_state(f"'From year' ({y_from}) is after 'To year' ({y_to}).", title="Swap the years",
                    hint="Choose a From year that is the same as or before the To year.")
else:
    spec = dict(chart=chart, x=x, y=y if y_used else None, agg=agg, color=None if color == NONE else color,
                facet=None if facet == NONE else facet, size=size if u["size"] else None,
                categories=tuple(chosen) or None, years=tuple(y for y in years if y_from <= y <= y_to),
                states=tuple(states) or None, regions=tuple(regions) or None, institutions=tuple(insts) or None,
                rank_max=rank_max or None, limit=(limit or None) if u["limit"] else None)
    with st.spinner("Building the chart…"):
        result, hint = _build(tuple(spec.items()))
    if hint:
        with st.container(border=True, key="card-builder-hint"):
            empty_state(hint, title="Try a different combination",
                        hint="Controls the chart type does not use are greyed out; a quick start above always works.")
    else:
        chart_card(result, key="builder", why=f"Built from your choices: a {CHARTS[chart][0].lower()} "
                                               f"({result.chart_type}, from the course list).")
