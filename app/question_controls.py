"""Live controls for one Annexure A question: the widgets that let the examiner change its parameters.

Every question in core/questions.py has default parameters (category, years, institutions, the two
parameters to compare ...). question_controls() draws one widget per editable parameter of THAT
question, right above its chart, starting from the registered default, and returns the parameter set
to run. So Q1.1 gets an institution picker and a year range, Q7.1 two year pickers, Q5.2 two parameter
pickers, and so on. This is how a new Level 2 question ("same chart, but for 2019 / Engineering /
Kerala") is answered live without writing code.

Parameters that fix WHAT the chart is (the direction of Q1.2/Q1.3, the chart view, the quartile mode)
are not offered, so the chart always stays the one the "Why this chart?" note explains.
"""

from __future__ import annotations

import streamlit as st

from app.filters import (MAX_INSTITUTIONS, category_years_map, institution_options, parameters_for,
                         prune_institutions, state_options)
from core.data import YEARS, NirfInputError, SHORT, find_institutions
from core.questions import Question

# Extra parameters worth changing live that the registry leaves at the engine default.
EXTRA_PARAMS = {
    "Q5.4": {"n": 12},
    "Q6.1": {"top": 10},
    "Q7.3": {"by_band": False},
    "Q8.1": {"z_threshold": 2.0},
    "Q8.3": {"z_threshold": 2.0},
}
FIXED = {"direction", "view", "mode"}           # define the chart itself, so not editable here
PAIRS = {"start_year": "end_year", "year_a": "year_b"}
# Left-to-right order of the controls: what is ranked (category), who, when, then the details.
ORDER = ["category", "categories", "institutions", "states", "years", "year", "start_year", "end_year", "year_a",
         "year_b", "x", "y", "param", "param_high", "param_low"]
TOP_CUTS = [10, 25, 50, 100, 150, 200]
TOP_SMALL = [3, 5, 10, 15, 20, 25]
Z_LEVELS = [1.5, 2.0, 2.5, 3.0]
PER_ROW = 4


def _key(q: Question, name: str, *scope) -> str:
    """Widget key: question + parameter, plus anything whose change must reset the widget (e.g. category)."""
    return "-".join(["qb", q.id, name, *map(str, scope)])


def reset_question(qid: str) -> None:
    """Forget every control of one question, so it shows its registered defaults again."""
    for k in [k for k in st.session_state if str(k).startswith(f"qb-{qid}-")]:
        del st.session_state[k]


def default_params(q: Question) -> dict:
    """The parameters the controls start from: the registry defaults plus the extra live ones (engine
    defaults), with institution names turned into the keys the picker uses. The page compares the
    current controls with this to tell whether the question was changed."""
    params = {**q.default_params, **EXTRA_PARAMS.get(q.id, {})}
    if params.get("institutions"):
        params["institutions"] = _default_keys(params["institutions"]) or None
    return params


def _index(options: list, value, fallback: int = 0) -> int:
    return options.index(value) if value in options else fallback


def _param_label(p: str) -> str:
    return SHORT.get(p, p.upper())


def _default_keys(names) -> list[str]:
    """Institution names in the registry (e.g. 'IIT Madras') -> the keys the picker uses."""
    try:
        return find_institutions(names) if names else []
    except NirfInputError:
        return []


def question_controls(q: Question) -> dict:
    """Draw the controls for question `q` and return the parameters to run it with."""
    params = default_params(q)
    shown = sorted((n for n in params if n not in FIXED), key=lambda n: ORDER.index(n) if n in ORDER else len(ORDER))
    out = dict(params)
    cats = category_years_map()

    # Category first: the year and parameter choices below depend on it.
    category = st.session_state.get(_key(q, "category"), params["category"]) if "category" in params else None
    years = cats.get(category, YEARS) if category else YEARS

    for row in [shown[i:i + PER_ROW] for i in range(0, len(shown), PER_ROW)]:
        cols = st.columns(PER_ROW, gap="small")
        for col, name in zip(cols, row):
            with col:
                out.update(_widget(q, name, params, category, years, cats))
    return out


def _widget(q: Question, name: str, params: dict, category: str | None, years: list[int], cats: dict) -> dict:
    """One parameter's widget; returns {parameter: value}."""
    default = params[name]

    if name == "category":
        options = list(cats)
        value = st.selectbox("Category", options, index=_index(options, default), key=_key(q, name),
                             help="Each NIRF category is a separate ranking list with its own weights.")
        return {name: value}

    if name == "categories":
        options = list(cats)
        start = [default] if isinstance(default, str) else list(default)
        value = st.multiselect("Categories", options, default=start, key=_key(q, name), max_selections=8,
                               help="Add categories to compare their averages. Scores of different categories "
                                    "are on different scales of meaning.")
        return {name: default if value in ([], start) else value}

    if name == "years":
        lo, hi = (default[0], default[-1]) if default else (years[0], years[-1])
        lo, hi = max(lo, years[0]), min(hi, years[-1])
        if len(years) == 1:
            st.caption(f"Years: {category} exists only in {years[0]}.")
            return {name: years}
        a, b = st.slider("Years", years[0], years[-1], (lo, hi), step=1, key=_key(q, name, category))
        return {name: [y for y in years if a <= y <= b]}

    if name == "year":
        options = years if category else YEARS
        value = st.selectbox("Year", options, index=_index(options, default, len(options) - 1),
                             key=_key(q, name, category))
        return {name: value}

    if name in PAIRS or name in PAIRS.values():
        first = name in PAIRS
        value = st.selectbox("From year" if first else "To year", years, key=_key(q, name, category),
                             index=_index(years, default, 0 if first else len(years) - 1))
        return {name: value}

    if name == "institutions":                    # only institutions listed in the question's category
        opts = institution_options(category or params.get("categories"))
        key = _key(q, name)
        note = prune_institutions(key, opts, category)   # after a category change: drop the unlisted ones
        start = None if key in st.session_state else [k for k in default or [] if k in opts]
        value = st.multiselect("Institutions", list(opts), default=start, key=key, format_func=opts.__getitem__,
                               max_selections=MAX_INSTITUTIONS,
                               placeholder="Top 5 (default)" if not default else "Search by name",
                               help=f"Institutions listed in {category}. 'band only' = never given an exact rank "
                                    "there." if category else None)
        if note:
            st.caption(note)
        return {name: value or None}

    if name == "states":
        value = st.multiselect("States", state_options(), default=list(default), key=_key(q, name),
                               max_selections=MAX_INSTITUTIONS)
        return {name: value or list(default)}

    if name in ("x", "y", "param", "param_high", "param_low"):
        options = parameters_for(category)
        if name in ("x", "y"):
            options = ["score"] + options
        label = {"x": "X axis", "y": "Y axis", "param": "Parameter", "param_high": "High parameter",
                 "param_low": "Low parameter"}[name]
        if not parameters_for(category):          # Innovation, SDG ... publish ranks without parameter scores
            st.selectbox(label, ["n/a"], disabled=True, key=_key(q, name, category),
                         help=f"NIRF published no parameter scores for {category}.")
            return {name: default}
        # A default missing in this category (RPC in Research) falls back to its first parameter.
        fallback = 1 if name in ("x", "param_low") and len(options) > 1 else 0
        value = st.selectbox(label, options, index=_index(options, default, fallback), format_func=_param_label,
                             key=_key(q, name, category))
        return {name: value}

    if name == "n":
        value = st.slider("How many institutions", 3, 30, int(default), key=_key(q, name))
        return {name: value}

    if name == "top_n":
        value = st.select_slider("Top N (rank cut-off)", TOP_CUTS, value=default, key=_key(q, name))
        return {name: value}

    if name == "top":
        value = st.select_slider("Top N", TOP_SMALL, value=default, key=_key(q, name))
        return {name: value}

    if name == "stat":
        value = st.segmented_control("Statistic", ["mean", "median"], default=default, key=_key(q, name))
        return {name: value or default}

    if name == "min_years":
        lo = 2 if q.function == "volatility_vs_peers" else 1
        hi = max(len(cats.get(category, YEARS)), lo + 1)
        label = "Ranked in at least N years" if lo == 2 else "In the top N for at least … years"
        value = st.slider(label, lo, hi, min(max(int(default), lo), hi), key=_key(q, name, category))
        return {name: value}

    if name == "min_institutions":
        value = st.slider("Minimum institutions per state", 1, 10, int(default), key=_key(q, name))
        return {name: value}

    if name == "z_threshold":
        value = st.select_slider("Unusual if |z| is above", Z_LEVELS, value=default, key=_key(q, name),
                                 help="z = how many standard deviations a value is from the average.")
        return {name: value}

    if name == "by_band":
        value = st.toggle("Split by band", value=default, key=_key(q, name))
        return {name: value}

    return {name: default}                       # anything else keeps its registered value
