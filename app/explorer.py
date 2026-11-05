"""Explorer pages (Level 2): "What do you want to see?", then every knob of that analysis, then its chart.

Each topic page (Trends, Geography, Distributions, Relationships, Multi-Parameter, Mobility, Outliers)
is a list of View objects: a plain-English label, the engine function that draws it, and the controls
for ALL of that function's parameters, and only those. explore() draws the picker, the controls in a
card right above the chart, and the chart card. So a new examiner question ("the same, but Pharmacy,
2019-2023, top 50, Kerala only, |z| above 2.5") is answered by turning the knobs of one view.

Controls come in two kinds:
  * shared with the sidebar (category, year range, states, institutions): the control on the page and
    the sidebar filter are the same value, so a change in either place shows in both and follows the
    user to the next page;
  * local to the view (a single year, two parameters, top N, thresholds, a chart variant): they start
    from the sidebar where that makes sense (the year starts at the end of the year range, top N at the
    sidebar's top N) and otherwise from the engine's default.
"States" on a view that has no state parameter of its own limits the whole analysis to institutions in
those states (core/runner.py); the chart subtitle, answer and method then name the states.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import streamlit as st

from app.components import show
from app.filters import (MAX_INSTITUTIONS, TOP_N_OPTIONS, category_years_map, clear_dropped_note, current,
                         dropped_note, institution_options, master, on_category_change, parameters_for,
                         removed_note, short_labels, state_options, synced as _synced)
from core.data import SHORT, YEARS
from core.questions import QUESTION_REGISTRY

PER_ROW = 4
STATES_HELP = ("Only institutions in these states are analysed (ranks stay national). Empty = all of India. "
               "Same as the sidebar's States filter.")


@dataclass(frozen=True)
class C:
    """One control. `kind` says which widget; `name` is the engine parameter it sets.

    kinds: category, categories, years, period, year, institutions, institution (exactly one), states,
    state_pair (two single-state pickers, "State A" and "State B", that together set `states`), scope (state
    filter for the whole analysis), param (a parameter picker), choice (any other value: top N, threshold,
    variant ...).
    """
    kind: str
    name: str | None = None
    label: str | None = None
    options: list | dict | str | None = None   # choice: values, {value: label}, or "years" = 1..number of
                                               # years of the category ("years2" = 2..)
    default: object = None
    widget: str = "select_slider"        # choice: select_slider, segmented, selectbox, slider, toggle
    help: str | None = None
    seed_top_n: bool = False             # choice: start from the sidebar's top N (nearest option)
    params: tuple[str, str] = ("start_year", "end_year")   # period: the two parameter names
    with_score: bool = False             # param: also offer the overall score


@dataclass(frozen=True)
class View:
    label: str
    engine: str
    function: str
    controls: tuple[C, ...]
    fixed: dict = field(default_factory=dict)   # parameters that define the chart itself (not a knob)
    why: str | None = None                      # "why this chart" (default: from the question registry)
    hint: str | None = None                     # optional one-line hint shown under the controls

    @property
    def id(self) -> str:
        return "-".join([self.function, *map(str, self.fixed.values())])


def _registry_why(function: str) -> str | None:
    for q in QUESTION_REGISTRY.values():
        if q.function == function:
            return q.why_this_chart
    return None


# ---------- the widgets ----------

def keep_valid(key: str, options) -> None:
    """Forget a local choice only when it is no longer offered (e.g. a year the new category does not have).

    Local controls keep a stable key, so changing the category keeps the chosen year, parameters and X/Y
    whenever the new category has them too; otherwise the control starts again from its default.
    """
    if key in st.session_state and st.session_state[key] not in options:
        del st.session_state[key]


def _choice(c: C, key: str):
    opts = c.options
    values = list(opts) if isinstance(opts, dict) else list(opts or [])
    fmt = (lambda v: opts[v]) if isinstance(opts, dict) else str
    default = c.default
    if c.seed_top_n:
        top = current().top_n
        default = min(values, key=lambda v: (abs(v - top), v))
        key += f"-{top}"
    if c.widget == "toggle":
        return st.toggle(c.label, value=bool(default), key=key, help=c.help)
    if c.widget == "slider":
        lo, hi = values[0], values[-1]
        return st.slider(c.label, lo, hi, min(max(default, lo), hi), key=key, help=c.help)
    if c.widget == "segmented":
        v = st.segmented_control(c.label, values, default=default, format_func=fmt, key=key, help=c.help)
        return default if v is None else v
    if c.widget == "selectbox":
        return st.selectbox(c.label, values, index=values.index(default), format_func=fmt, key=key, help=c.help)
    return st.select_slider(c.label, values, value=default, format_func=fmt, key=key, help=c.help)


class Ctx:
    """What the controls of one view need to know while they are drawn."""

    def __init__(self, page: str, view: View):
        self.page, self.view, self.f = page, view, current()
        self.category = self.f.category if any(c.kind == "category" for c in view.controls) else None
        self.categories = [self.f.category]

    @property
    def years(self) -> list[int]:
        cats = category_years_map()
        if self.category:
            return cats[self.category]
        if any(c.kind == "categories" for c in self.view.controls):
            return sorted({y for c in self.categories for y in cats[c]})
        return YEARS

    def key(self, name: str, *scope) -> str:
        return "-".join(["x", self.page, self.view.id, name, *map(str, scope)])


def draw(c: C, ctx: Ctx) -> dict:
    """Draw one control; returns the engine parameters it sets ({"__states": ...} for the state filter)."""
    f, cats = ctx.f, category_years_map()

    if c.kind == "category":
        ctx.category = _synced(st.selectbox, f"x-{ctx.page}-category", "f_category", f.category,
                               after=on_category_change,
                               label="Category", options=list(cats), index=list(cats).index(f.category),
                               help="Each NIRF category is a separate ranking list with its own weights.")
        return {c.name or "category": ctx.category}

    if c.kind == "categories":
        value = st.multiselect(c.label or "Categories", list(cats), default=[f.category], max_selections=8,
                               key=ctx.key("categories", f.category),
                               help="Add categories to compare them. Scores of different categories are on "
                                    "different scales of meaning.")
        ctx.categories = value or [f.category]
        return {c.name or "categories": ctx.categories}

    years = ctx.years
    if c.kind in ("years", "period"):
        if len(years) == 1:
            st.caption(f"{ctx.category} exists only in {years[0]}.")
            ys = (years[0], years[0])
        else:
            lo, hi = max(f.start, years[0]), min(f.end, years[-1])
            if lo >= hi:
                lo, hi = years[0], years[-1]
            ys = _synced(st.select_slider, ctx.key(c.kind, ctx.category), "f_years", (lo, hi),
                         to_global=lambda v: tuple(sorted(v)), value=(lo, hi),
                         label=c.label or ("Years" if c.kind == "years" else "From year → to year"), options=years,
                         help=None if c.kind == "years" else "The first and the last year to compare.")
        ys = tuple(sorted(ys))                   # always earlier year first, however the range was set
        if c.kind == "years":
            return {"years": [y for y in years if ys[0] <= y <= ys[1]]}
        return dict(zip(c.params, ys))

    if c.kind == "year":
        default = min(f.end, years[-1]) if f.end >= years[0] else years[-1]
        key = ctx.key("year")
        keep_valid(key, years)
        value = st.selectbox(c.label or "Year", years, index=years.index(default) if default in years else len(years) - 1,
                             key=key)
        return {c.name or "year": value}

    if c.kind == "institutions":                  # only institutions listed in the chosen category
        category = ctx.category or f.category
        opts = institution_options(ctx.categories if ctx.category is None else category)
        value = _synced(st.multiselect, f"x-{ctx.page}-institutions", "f_institutions",
                        list(f.institutions), after=clear_dropped_note,
                        default=[k for k in f.institutions if k in opts],
                        label="Institutions", options=list(opts),
                        format_func=lambda k: opts[k], max_selections=MAX_INSTITUTIONS,
                        placeholder=c.help or "Top 5 (default)",
                        help=f"Institutions listed in {category}. 'band only' = never given an exact rank there.")
        if note := dropped_note():
            st.caption(note)
        return {"institutions": value or None}

    if c.kind == "institution":
        category = ctx.category or f.category
        opts = institution_options(category)
        key = ctx.key("institution")
        default = next((k for k in f.institutions if k in opts), None) or _leader(category)
        note = _keep_institution(key, opts, category)
        index = 0 if key in st.session_state else list(opts).index(default)   # a kept choice wins
        value = st.selectbox("Institution", list(opts), index=index, format_func=opts.get, key=key,
                             on_change=lambda: st.session_state.update({f"{key}-chosen": True}),
                             help="Starts from the first institution in the sidebar, else this category's rank 1. "
                                  f"Only institutions listed in {category}.")
        if note:
            st.caption(note)
        return {"institution": value}

    if c.kind == "states":
        value = _synced(st.multiselect, f"x-{ctx.page}-states", "f_states", list(f.states), default=list(f.states),
                        label="States",
                        options=state_options(), max_selections=8, placeholder="Karnataka, Tamil Nadu")
        return {"states": value or list(c.default)}

    if c.kind == "state":                                 # one half of a state_pair
        opts = state_options()
        key = ctx.key(c.name)
        keep_valid(key, opts)
        value = st.selectbox(c.label, opts, index=opts.index(c.default) if c.default in opts else 0, key=key,
                             help=c.help)
        return {"__pair": value}

    if c.kind == "scope":
        value = _synced(st.multiselect, f"x-{ctx.page}-states", "f_states", list(f.states), default=list(f.states),
                        label="Only states",
                        options=state_options(), placeholder="All of India", help=STATES_HELP)
        return {"__states": value or None}

    if c.kind == "param":
        options = parameters_for(ctx.category)
        options = (["score"] + options) if c.with_score else options
        if not parameters_for(ctx.category):
            st.selectbox(c.label, ["n/a"], disabled=True, key=ctx.key(c.name, ctx.category, "none"),
                         help=f"NIRF published no parameter scores for {ctx.category}.")
            return {c.name: c.default}
        index = options.index(c.default) if c.default in options else 0
        key = ctx.key(c.name)
        keep_valid(key, options)
        value = st.selectbox(c.label, options, index=index, format_func=lambda p: SHORT.get(p, p.upper()), key=key)
        return {c.name: value}

    if c.kind == "choice":
        if isinstance(c.options, str):                    # "at least N years": bounded by the category's years
            lo = 2 if c.options == "years2" else 1
            n = C(c.kind, c.name, c.label, list(range(lo, max(len(years), lo + 1) + 1)),
                  min(max(c.default, lo), max(len(years), lo + 1)), widget="slider", help=c.help)
            keep_valid(ctx.key(c.name), n.options)
            return {c.name: _choice(n, ctx.key(c.name))}
        return {c.name: _choice(c, ctx.key(c.name))}

    raise ValueError(f"unknown control kind {c.kind!r}")


def _keep_institution(key: str, opts: dict, category: str) -> str | None:
    """A single-institution picker after a category change: keep the choice when the new category lists it
    (written back, because new options make a new widget), else forget it. Returns a caption when a choice
    the user made was removed."""
    if key not in st.session_state:
        return None
    value = st.session_state[key]
    if value in opts:
        st.session_state[key] = value
        return None
    del st.session_state[key]
    if st.session_state.pop(f"{key}-chosen", False):
        return removed_note(short_labels([value]), category)
    return None


def _leader(category: str) -> str:
    """The institution with the best exact rank in the category's latest year."""
    df = master()
    rows = df[df["category_std"].eq(category) & df["rank"].notna()]
    return rows[rows["year"].eq(rows["year"].max())].sort_values("rank")["institution_key"].iloc[0]


def _expand(controls_: tuple[C, ...]) -> list[C]:
    """A state_pair becomes its two single-state pickers (each takes one column)."""
    out = []
    for c in controls_:
        if c.kind == "state_pair":
            a, b = c.default or ("Karnataka", "Tamil Nadu")
            out += [C("state", "state_a", "State A", default=a, help=c.help),
                    C("state", "state_b", "State B", default=b, help=c.help)]
        else:
            out.append(c)
    return out


def controls(page: str, view: View, per_row: int = PER_ROW) -> tuple[dict, list[str] | None]:
    """Draw a view's controls in rows of `per_row`; returns (engine parameters, state filter or None)."""
    ctx = Ctx(page, view)
    params: dict = dict(view.fixed)
    pair: list[str] = []
    items = _expand(view.controls)
    for row in [items[i:i + per_row] for i in range(0, len(items), per_row)]:
        cols = st.columns(per_row, gap="small")
        for col, c in zip(cols, row):
            with col:
                out = draw(c, ctx)
                if "__pair" in out:
                    pair.append(out.pop("__pair"))
                params.update(out)
    if pair:
        params["states"] = pair
    states = params.pop("__states", None)
    return params, states


def explore(page: str, views: list[View]) -> None:
    """The picker, the chosen view's controls in a card, then its chart card."""
    labels = [v.label for v in views]
    label = st.selectbox("What do you want to see?", labels, key=f"x-{page}-view")
    explore_view(page, views[labels.index(label)])


def explore_view(page: str, view: View) -> None:
    """One view: its controls in a card, then its chart card."""
    with st.container(border=True, key=f"x-{page}-controls"):
        params, states = controls(page, view)
        if view.hint:
            st.caption(view.hint)
    show(view.engine, view.function, key=f"{page}-{view.id}", why=view.why or _registry_why(view.function),
         scope=states, **params)


# ---------- ready-made controls used by several pages ----------

CATEGORY = C("category")
YEARS_RANGE = C("years")
YEAR = C("year")
SCOPE = C("scope")
PERIOD = C("period")
PERIOD_AB = C("period", params=("year_a", "year_b"))
INSTITUTIONS = C("institutions")
STATE_PAIR = C("state_pair", "states", default=("Karnataka", "Tamil Nadu"),
               help="Choose any two states or UTs; the same state twice cannot be compared.")
TOP_CUT = C("choice", "top_n", "Top list (rank cut-off)", [10, 25, 50, 100, 150, 200], 100,
            help="Count institutions certainly ranked within this many places (a 101-150 band is not in the top 100).")
TOP_ONLY = C("choice", "top_n", "Only ranks 1 to …", {None: "All", 10: "10", 25: "25", 50: "50", 100: "100"}, None,
             help="All = every institution with a published score; a number keeps the same number of places each year.")


def how_many(name: str = "n", label: str = "How many institutions", options=(3, 5, 10, 15, 20, 25, 30)) -> C:
    return C("choice", name, label, list(options), 10, seed_top_n=True)


def top_n(name: str = "top", label: str = "Top N", options=tuple(TOP_N_OPTIONS[:-1])) -> C:
    return C("choice", name, label, list(options), 10, seed_top_n=True)


def param(name: str, label: str, default: str, with_score: bool = False) -> C:
    return C("param", name, label, default=default, with_score=with_score)


def variant(name: str, label: str, options: dict, default) -> C:
    return C("choice", name, label, options, default, widget="segmented")


Z_THRESHOLD = C("choice", "z_threshold", "Unusual if |z| is above", [1.5, 2.0, 2.5, 3.0], 2.0,
                help="z = how many standard deviations a value is from the average; |z| > 2 is the usual cut-off.")
