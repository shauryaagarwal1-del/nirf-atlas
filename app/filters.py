"""Global filters: the sidebar controls shared by every page, kept in st.session_state.

The sidebar is drawn once per run by the entry point (app/Home.py), so the same five choices follow
the user from page to page: category, year range, states, institutions and top-N. A page reads them
with current() and turns them into engine parameters; a page may offer its own control that starts
from the global value (e.g. a single year that defaults to the end of the year range).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from core.data import load_master, parameters_of, short_name

DEFAULT_CATEGORY = "Overall"
TOP_N_OPTIONS = [3, 5, 10, 15, 20, 25, 50, 100]
DEFAULT_TOP_N = 10
MAX_INSTITUTIONS = 8   # the categorical palette has 8 colours


@st.cache_resource(show_spinner=False)
def master() -> pd.DataFrame:
    """The cleaned master table, loaded once per server process (read-only: never modify it)."""
    return load_master()


@st.cache_data(show_spinner=False)
def category_years_map() -> dict[str, list[int]]:
    """Category -> the years NIRF published it, categories ordered by how many years they cover."""
    df = master()
    years = df.groupby("category_std")["year"].agg(lambda s: sorted(s.unique().tolist()))
    order = sorted(years.index, key=lambda c: (c != DEFAULT_CATEGORY, -len(years[c]), c))
    return {c: years[c] for c in order}


@st.cache_data(show_spinner=False)
def institution_options() -> dict[str, str]:
    """institution_key -> 'Short name · City, State', sorted by name (for the search box)."""
    df = master().sort_values("year").drop_duplicates("institution_key", keep="last")
    labels = {r.institution_key: f"{short_name(r.canonical_name, 60)} · {r.city}, {r.state}" if r.city
              else f"{short_name(r.canonical_name, 60)} · {r.state}" for r in df.itertuples()}
    return dict(sorted(labels.items(), key=lambda kv: kv[1].lower()))


@st.cache_data(show_spinner=False)
def state_options() -> list[str]:
    return sorted(master()["state"].dropna().unique().tolist())


@dataclass(frozen=True)
class Filters:
    category: str
    start: int
    end: int
    states: tuple[str, ...]
    institutions: tuple[str, ...]   # institution keys
    top_n: int

    @property
    def years(self) -> list[int]:
        """The category's published years inside the chosen range."""
        return [y for y in category_years_map()[self.category] if self.start <= y <= self.end]

    @property
    def span(self) -> str:
        return str(self.start) if self.start == self.end else f"{self.start}–{self.end}"

    def institution_labels(self) -> list[str]:
        opts = institution_options()
        return [opts[k].split(" · ")[0] for k in self.institutions if k in opts]

    def rows(self) -> pd.DataFrame:
        """Master-table rows matching every global filter (used for the selection summary and the data page)."""
        df = master()
        mask = df["category_std"].eq(self.category) & df["year"].between(self.start, self.end)
        if self.states:
            mask &= df["state"].isin(self.states)
        if self.institutions:
            mask &= df["institution_key"].isin(self.institutions)
        return df[mask]


def _reset_years() -> None:
    years = category_years_map()[st.session_state["f_category"]]
    st.session_state["f_years"] = (years[0], years[-1])


def _reset_all() -> None:
    st.session_state["f_category"] = DEFAULT_CATEGORY
    _reset_years()
    st.session_state["f_states"] = []
    st.session_state["f_institutions"] = []
    st.session_state["f_top_n"] = DEFAULT_TOP_N


def _init() -> None:
    if "f_category" not in st.session_state:
        _reset_all()


def render_sidebar() -> Filters:
    """Draw the global filters in the sidebar and return the current choice."""
    _init()
    cats = category_years_map()
    with st.sidebar:
        st.html('<div class="nirf-side-title">Global filters</div>')
        category = st.selectbox("Category", list(cats), key="f_category", on_change=_reset_years,
                                help="Each NIRF category is a separate ranking list with its own weights.")
        years = cats[category]
        lo, hi = st.session_state.get("f_years", (years[0], years[-1]))
        if lo < years[0] or hi > years[-1]:
            st.session_state["f_years"] = (years[0], years[-1])
        if len(years) > 1:
            st.slider("Years", min_value=years[0], max_value=years[-1], key="f_years", step=1,
                      help=f"{category} was published in {years[0]}–{years[-1]}.")
        else:
            st.session_state["f_years"] = (years[0], years[0])
            st.caption(f"Years: {category} exists only in {years[0]}.")
        st.multiselect("States", state_options(), key="f_states", placeholder="All states",
                       help="Leave empty for all states and union territories.")
        st.multiselect("Institutions", list(institution_options()), key="f_institutions",
                       format_func=lambda k: institution_options()[k], max_selections=MAX_INSTITUTIONS,
                       placeholder="Search by name, e.g. IIT Madras",
                       help="Used by charts that follow chosen institutions (trajectories, profiles).")
        st.select_slider("Top N", TOP_N_OPTIONS, key="f_top_n",
                         help="How many institutions a 'top N' chart shows.")
        f = current()
        rows = f.rows()
        st.html(f'<div class="nirf-side-summary">Your selection matches <b>{len(rows):,}</b> rows · '
                f'<b>{rows["institution_key"].nunique():,}</b> institutions.</div>')
        st.button("Reset filters", on_click=_reset_all, icon=":material/restart_alt:", width="stretch")
    return f


def current() -> Filters:
    """The global filters as they are now (defaults if the sidebar has not been drawn yet)."""
    _init()
    s = st.session_state
    lo, hi = s["f_years"]
    return Filters(s["f_category"], int(lo), int(hi), tuple(s["f_states"]), tuple(s["f_institutions"]),
                   int(s["f_top_n"]))


@st.cache_data(show_spinner=False)
def parameters_for(category: str) -> list[str]:
    """The parameter columns NIRF published for a category (TLR..PR, or QnR/QlR/SFC/OI/PR for Research)."""
    df = master()
    return parameters_of(df[df["category_std"].eq(category)])
