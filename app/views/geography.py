"""Geography: where the ranked institutions are and how the map changes (engine: core/engines/geography.py).

Four tabs (only the open tab is drawn, so the page stays fast):
  * India map       choropleth of institutions per state in the top N, with a year slider and a play button
                    that animates the map from the category's first year to its last;
  * State vs State  two states head to head (default Karnataka vs Tamil Nadu): a card per state, then counts
                    and median rank per year (two aligned panels) and a box plot of all their ranks;
  * New entrants    states that produced the most institutions entering the ranking for the first time;
  * More views      the other geography analyses (counts, shares over time, gains and losses, rank boxes).
Every view has controls for all of its engine parameters (app/explorer.py); VIEWS lists them all.
"""

import pandas as pd
import streamlit as st

from app.components import chart_card, empty_state, kpi_cards, page_header, run_engine, show
from app.explorer import (CATEGORY, PERIOD, SCOPE, STATE_PAIR, TOP_CUT, YEAR, YEARS_RANGE, C, View, controls,
                          explore, explore_view)
from core.data import short_name
from core.theme import color_map

PAGE = "geography"
DEFAULT_STATES = ("Karnataka", "Tamil Nadu")
VS_TOP = C("choice", "top_n", "Count only the top …", {None: "All ranked", 10: "10", 25: "25", 50: "50", 100: "100",
                                                       150: "150", 200: "200"}, None,
           help="All ranked = every institution in the list, NIRF bands included; 100 = only those certainly in "
                "the top 100.")

MAP_VIEW = View("Institutions per state on the map of India", "geography", "state_map", (CATEGORY, YEAR, TOP_CUT),
                why="A choropleth map shows at a glance where the top institutions are concentrated; the fixed "
                    "colour scale lets the play button show the map changing year by year.",
                hint="Press ▶ Play under the map to animate every year, or drag the slider to pick one. "
                     "Hover a state for its best institution and median rank.")
VS_VIEW = View("State vs State: institutions and median rank per year", "geography", "state_vs_state",
               (STATE_PAIR, CATEGORY, YEARS_RANGE, VS_TOP),
               why="Two time series on one shared year axis: how many institutions each state has (top) and how "
                   "well they rank (bottom), so both sides of the comparison are read year by year.")
VS_BOX_VIEW = View("State vs State: all their ranks side by side", "geography", "state_rank_boxes",
                   (STATE_PAIR, CATEGORY, YEARS_RANGE, VS_TOP),
                   why="A box plot compares whole rank distributions: median, middle 50% and outliers, with every "
                       "institution-year as a dot.")
NEW_VIEW = View("States with the most new entrants", "geography", "new_entrants_by_state",
                (CATEGORY, YEARS_RANGE, C("choice", "by_year", "Split by year", default=False,
                                          widget="toggle"), SCOPE),
                why="A ranked bar chart compares the states' totals directly; switch on the split to see in which "
                    "years the new entrants arrived.")
MORE_VIEWS = [
    View("States with the most institutions in the top list", "geography", "state_counts",
         (CATEGORY, YEAR, TOP_CUT, SCOPE)),
    View("Each state's share of the top list over time", "geography", "state_share_over_time",
         (CATEGORY, TOP_CUT, SCOPE)),
    View("States that gained or lost places in the top list", "geography", "state_representation_change",
         (CATEGORY, PERIOD, TOP_CUT, SCOPE)),
    View("Compare the ranks of up to 8 states, year by year", "geography", "compare_states",
         (CATEGORY, C("states", default=DEFAULT_STATES), YEARS_RANGE),
         hint="No states chosen = Karnataka and Tamil Nadu. Pick up to 8 states."),
]
VIEWS = [MAP_VIEW, VS_VIEW, VS_BOX_VIEW, NEW_VIEW, *MORE_VIEWS]
TABS = {"map": "India map", "vs": "State vs State", "new": "New entrants", "more": "More views"}


def state_cards(vs: pd.DataFrame, boxes: pd.DataFrame, top_n: int | None) -> None:
    """One card per state, in its chart colour: institutions per year, pooled median rank, best institution."""
    per_year = vs.groupby("state", sort=False)["institutions"].mean()
    b = boxes.set_index("state")
    what = f"top-{top_n}" if top_n else "ranked"
    kpi_cards([(s, f"{per_year[s]:.1f}",
                f"{what} institutions a year · median rank {b.at[s, 'median_rank']:g} · best: "
                f"{short_name(b.at[s, 'best_institution'], 30)} (#{int(b.at[s, 'best_rank'])})")
               for s in per_year.index], accents=list(color_map(per_year.index).values()))


def state_vs_state() -> None:
    with st.container(border=True, key=f"x-{PAGE}-controls-vs"):
        params, _ = controls(PAGE, VS_VIEW, per_row=5)
        st.caption("Counts include NIRF band-only positions; median ranks use exact ranks only.")
    vs, error = run_engine("geography", "state_vs_state", params)
    boxes, box_error = run_engine("geography", "state_rank_boxes", params)
    if error or box_error:
        with st.container(border=True, key=f"card-{PAGE}-vs"):
            empty_state(error or box_error, title="This selection has no answer",
                        hint="Choose two different states, another category or a wider year range.")
        return
    state_cards(vs.table, boxes.table, params.get("top_n"))
    chart_card(vs, f"{PAGE}-vs", VS_VIEW.why)
    chart_card(boxes, f"{PAGE}-vs-box", VS_BOX_VIEW.why)


SECTIONS = {
    "map": lambda: explore_view(PAGE, MAP_VIEW),
    "vs": state_vs_state,
    "new": lambda: explore_view(PAGE, NEW_VIEW),
    "more": lambda: explore(PAGE, MORE_VIEWS),
}

page_header("Geography", "Where the top institutions are on the map of India, how two states compare head to "
            "head, which states bring in new institutions, and how their share changes over the years.",
            eyebrow="Explore · Regions")
tabs = st.tabs(list(TABS.values()), key=f"{PAGE}-tab", on_change="rerun")
for name, tab in zip(TABS, tabs):
    if tab.open:
        with tab:
            SECTIONS[name]()
