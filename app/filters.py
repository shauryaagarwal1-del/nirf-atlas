"""Global filters: the sidebar controls shared by the Explore pages, kept in st.session_state.

The entry point (app/Home.py) draws them on Home, the seven Explore pages and Data & Method, so the same
five choices follow the user from page to page: category, year range, states, institutions and top-N.
A page reads them with current() and turns them into engine parameters; a page may offer its own control
that starts from the global value (e.g. a single year that defaults to the end of the year range). On the
Explore pages, the category, year range, states and institutions controls above each chart edit these
same values (app/explorer.py), and the States filter limits every Explore analysis to those states.
The five values live in session state (f_category, f_years, f_states, f_institutions, f_top_n), not in
widget keys: every control that edits one is drawn with synced(). Question Bank, Chart Builder and Ask NIRF
have their own controls, so their sidebar only says so, and the values wait there for the next Explore page.

Institution pickers offer only the institutions listed in the chosen category (institution_options());
when the category changes, chosen institutions that are not listed in the new one are removed and a
short caption names them.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass

import pandas as pd
import streamlit as st

from core.data import load_master, parameters_of, short_name

DEFAULT_CATEGORY = "Overall"
TOP_N_OPTIONS = [3, 5, 10, 15, 20, 25, 50, 100]
DEFAULT_TOP_N = 10
MAX_INSTITUTIONS = 8   # the categorical palette has 8 colours
DROPPED = "f_dropped"  # (category, caption) after a category change removed chosen institutions


@st.cache_resource(show_spinner=False)
def master() -> pd.DataFrame:
    """The cleaned master table, loaded once per server process (read-only: never modify it)."""
    return load_master()


# The lookup tables below are cached with cache_resource, not cache_data: cache_data hands every caller a
# fresh copy (it unpickles the stored value), which made the 1,693-entry institution list cost ~2.7 s per
# page run when a search box looked up one label per option. These tables are read-only, so one shared
# copy is safe and every lookup is instant.

@st.cache_resource(show_spinner=False)
def category_years_map() -> dict[str, list[int]]:
    """Category -> the years NIRF published it, categories ordered by how many years they cover (read-only)."""
    df = master()
    years = df.groupby("category_std")["year"].agg(lambda s: sorted(s.unique().tolist()))
    order = sorted(years.index, key=lambda c: (c != DEFAULT_CATEGORY, -len(years[c]), c))
    return {c: years[c] for c in order}


@st.cache_resource(show_spinner=False)
def _institution_labels() -> dict[str, str]:
    """institution_key -> 'Short name · City, State', from the institution's latest row (read-only)."""
    df = master().sort_values("year").drop_duplicates("institution_key", keep="last")
    return {r.institution_key: f"{short_name(r.canonical_name, 60)} · {r.city}, {r.state}" if r.city
            else f"{short_name(r.canonical_name, 60)} · {r.state}" for r in df.itertuples()}


def institution_options(categories: str | list[str] | tuple[str, ...] | None = None) -> dict[str, str]:
    """The institutions a picker offers: key -> label, sorted by name (read-only).

    One category: only the institutions listed in it at least once, with an exact rank or in a rank band.
    Several categories (Chart Builder): those listed in any of them. The label ends in " · band only" when
    the institution never had an exact rank there (NIRF placed it only in bands such as 101-150).
    None = every institution in the data.
    """
    if categories is None:
        return _institution_options(None)
    names = (categories,) if isinstance(categories, str) else tuple(sorted(set(categories)))
    return _institution_options(names)


@st.cache_resource(show_spinner=False)
def _institution_options(categories: tuple[str, ...] | None) -> dict[str, str]:
    labels = _institution_labels()
    if categories is None:
        out = labels
    else:
        df = master()
        has_rank = df[df["category_std"].isin(categories)].groupby("institution_key")["rank"].agg(
            lambda s: s.notna().any())
        out = {k: labels[k] if exact else f"{labels[k]} · band only" for k, exact in has_rank.items()}
    return dict(sorted(out.items(), key=lambda kv: kv[1].lower()))


def short_labels(keys) -> list[str]:
    """The short names of institution keys, e.g. ['IIT Dharwad'] (for captions)."""
    labels = _institution_labels()
    return [labels[k].split(" · ")[0] for k in keys if k in labels]


def removed_note(names: list[str], category: str) -> str:
    """'IIT Dharwad is not ranked in Medical, so it was removed.' (for one or several names)."""
    if len(names) == 1:
        return f"{names[0]} is not ranked in {category}, so it was removed."
    return f"{', '.join(names[:-1])} and {names[-1]} are not ranked in {category}, so they were removed."


def prune_institutions(key: str, options, category: str) -> str | None:
    """Drop the chosen institutions (session state `key`) that `options` does not offer; call it before the
    picker is drawn. Returns the caption naming what was removed, or None.

    The value is written back even when nothing was dropped: to Streamlit a picker whose options change is
    a new widget, and a value set through session state is what the new widget starts from.
    """
    if key not in st.session_state:
        return None
    chosen = list(st.session_state[key] or [])
    st.session_state[key] = [k for k in chosen if k in options]
    dropped = short_labels(k for k in chosen if k not in options)
    return removed_note(dropped, category) if dropped else None


@st.cache_resource(show_spinner=False)
def state_options() -> list[str]:
    """All states / UTs with a ranked institution, A to Z (read-only)."""
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
        return short_labels(self.institutions)

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


def _prune_global_institutions() -> None:
    """Keep only the chosen institutions listed in the global category; remember the caption if any went."""
    category = st.session_state["f_category"]
    note = prune_institutions("f_institutions", institution_options(category), category)
    if note:
        st.session_state[DROPPED] = (category, note)


def on_category_change() -> None:
    """The global category changed (in the sidebar or on an Explore page): show its full year range and keep
    only the chosen institutions that are listed in it."""
    _reset_years()
    clear_dropped_note()
    _prune_global_institutions()


def dropped_note() -> str | None:
    """The 'X is not ranked in Y, so it was removed.' caption, while that category is still the chosen one."""
    category, note = st.session_state.get(DROPPED) or (None, None)
    return note if category == st.session_state.get("f_category") else None


def clear_dropped_note() -> None:
    st.session_state.pop(DROPPED, None)


def _reset_all() -> None:
    st.session_state["f_category"] = DEFAULT_CATEGORY
    _reset_years()
    st.session_state["f_states"] = []
    st.session_state["f_institutions"] = []
    st.session_state["f_top_n"] = DEFAULT_TOP_N
    clear_dropped_note()


def _init() -> None:
    if "f_category" not in st.session_state:
        _reset_all()


def synced(widget, key: str, global_key: str, state, to_global=lambda v: v, after=None, **kwargs):
    """A widget that edits a global filter: it starts from the filter's value and writes changes back.

    The filter values (f_category, f_years ...) are plain session-state values, not widget keys, so they
    survive pages that do not draw the filters. The widget key carries the value it was drawn from (`state`):
    when the filter changes (in the sidebar or on a page) the widget is drawn afresh from the new value, so
    sidebar and page always agree, and a late message from the browser about the old widget cannot undo
    the change. `kwargs` must give the widget its starting value (index= / value= / default=).
    """
    key = f"{key}-{zlib.crc32(repr(state).encode())}"

    def write_back():
        st.session_state[global_key] = to_global(st.session_state[key])
        if after:
            after()
    return widget(key=key, on_change=write_back, **kwargs)


def render_own_controls_note() -> None:
    """The sidebar of Question Bank, Chart Builder and Ask NIRF: a short note instead of the global filters.
    The filter values stay in session state for the next Explore page."""
    _init()
    with st.sidebar:
        st.html('<div class="nirf-side-title">Filters</div>'
                '<div class="nirf-side-summary">This page uses its own controls. The sidebar filters apply to '
                'the Explore pages.</div>')


def render_sidebar() -> Filters:
    """Draw the global filters in the sidebar and return the current choice."""
    _init()
    s = st.session_state
    cats = category_years_map()
    # A category set without the change callback (e.g. straight into session state) still keeps only the
    # institutions listed in it.
    _prune_global_institutions()
    category = s["f_category"]
    years = cats[category]
    lo, hi = s["f_years"]
    if lo < years[0] or hi > years[-1] or len(years) == 1:
        s["f_years"] = (years[0], years[-1])
    with st.sidebar:
        st.html('<div class="nirf-side-title">Global filters</div>')
        synced(st.selectbox, "side-category", "f_category", category, after=on_category_change,
               label="Category", options=list(cats), index=list(cats).index(category),
               help="Each NIRF category is a separate ranking list with its own weights.")
        if len(years) > 1:
            synced(st.slider, "side-years", "f_years", (category, s["f_years"]), to_global=lambda v: tuple(sorted(v)),
                   label="Years", min_value=years[0], max_value=years[-1], value=tuple(s["f_years"]), step=1,
                   help=f"{category} was published in {years[0]}–{years[-1]}.")
        else:
            st.caption(f"Years: {category} exists only in {years[0]}.")
        synced(st.multiselect, "side-states", "f_states", list(s["f_states"]), label="States",
               options=state_options(), default=list(s["f_states"]), placeholder="All states",
               help="Explore pages analyse only institutions in these states (ranks stay national). "
                    "Leave empty for all of India.")
        inst = institution_options(category)
        synced(st.multiselect, "side-institutions", "f_institutions", (category, list(s["f_institutions"])),
               after=clear_dropped_note, label="Institutions", options=list(inst),
               default=[k for k in s["f_institutions"] if k in inst], format_func=inst.__getitem__,
               max_selections=MAX_INSTITUTIONS, placeholder="Search, e.g. IIT Madras",
               help=f"Institutions listed in {category}, for charts that follow chosen institutions "
                    "(trajectories, profiles). 'band only' = never given an exact rank in this category.")
        if note := dropped_note():
            st.caption(note)
        synced(st.select_slider, "side-top_n", "f_top_n", s["f_top_n"], label="Top N", options=TOP_N_OPTIONS,
               value=s["f_top_n"], help="How many institutions a 'top N' chart shows.")
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
