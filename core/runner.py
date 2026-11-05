"""Run any engine function by name, optionally for the institutions of chosen states or institute types only.

One entry point used by the dashboard pages (app/components.py) and by the Ask NIRF chat, so both run
analyses the same way:
  * only the 8 engines and their public functions can be called (no other code);
  * states=["Kerala"] runs the analysis on Kerala's institutions only (core.data.only_states), and the
    answer says so: the chart subtitle, the one-line answer and the method all name the states, so a
    "Kerala only" chart can never be mistaken for an all-India one;
  * types=["IIT"] runs it on IITs only (core.data.only_types); the chart title and the answer then start
    with "Among IITs only".

Ranks stay the national NIRF ranks; averages, quartiles, z-scores and correlations are then
calculated within the chosen group.
"""

from __future__ import annotations

import importlib
import inspect

from core.data import (INSTITUTE_TYPES, NirfInputError, check_category, load_master, only_states, only_types,
                       scope_phrase)
from core.result import ChartResult
from core.theme import TITLE_LINE, TITLE_WRAP, wrap_text

ENGINES = ("trends", "geography", "univariate", "bivariate", "multivariate", "distribution", "mobility", "outliers")


def engine_function(engine: str, function: str):
    """The engine function `core.engines.<engine>.<function>`, or a NirfInputError if there is none."""
    if engine not in ENGINES:
        raise NirfInputError(f"There is no '{engine}' analysis. Choose one of: {', '.join(ENGINES)}.")
    module = importlib.import_module(f"core.engines.{engine}")
    fn = getattr(module, function, None)
    if function.startswith("_") or not inspect.isfunction(fn) or fn.__module__ != module.__name__:
        raise NirfInputError(f"The {engine} analysis has no '{function}' chart.")
    return fn


def takes_states(engine: str, function: str) -> bool:
    """True when the function has its own `states` parameter (then the state scope is not used)."""
    return "states" in inspect.signature(engine_function(engine, function)).parameters


def _state_text(states: tuple[str, ...]) -> str:
    return states[0] if len(states) == 1 else ", ".join(states[:-1]) + " and " + states[-1]


def _retitle(fig, prefix: str) -> None:
    """Put `prefix` in front of the chart title and wrap it again (keeping the room for the title right)."""
    old = fig.layout.title.text or ""
    text, extra = wrap_text(f"{prefix}: {old.replace('<br>', ' ')}", TITLE_WRAP)
    grow = TITLE_LINE * (extra - old.count("<br>"))
    fig.update_layout(title_text=text)
    if grow:
        fig.update_layout(height=(fig.layout.height or 520) + grow, margin_t=(fig.layout.margin.t or 0) + grow)


def run(engine: str, function: str, params: dict | None = None, states=None, types=None) -> ChartResult:
    """Call the engine function with `params`; with `states` / `types`, only for those institutions.

    states: institutions located in these states (not used when the function has its own `states`).
    types: institute types such as ["IIT"] or ["IIM", "IISER"] (core.data.INSTITUTE_TYPES).
    """
    fn = engine_function(engine, function)
    params = dict(params or {})
    states = states if states and not takes_states(engine, function) else None
    if not states and not types:
        return fn(**params)

    with only_states(states) as scope, only_types(types) as kinds:
        who = scope_phrase(scope, kinds)
        clear = " and ".join(x for x, on in (("the state filter", scope), ("the institute type filter", kinds)) if on)
        if "category" in params:
            category = check_category(params["category"])
            if not load_master()["category_std"].eq(category).any():
                raise NirfInputError(f"No {scope_phrase(scope, kinds, singular=True)} is ranked in {category}. "
                                     f"Choose another category or clear {clear}.")
        try:
            result = fn(**params)
        except NirfInputError as e:
            everyone = "all of India" if not kinds else "every institution"
            raise NirfInputError(f"{e} (Only {who} are included; clear {clear} to use {everyone}.)") from None

    subtitle = result.fig.layout.title.subtitle.text or ""
    if kinds:
        among = f"Among {who} only"
        _retitle(result.fig, among)
        result.fig.update_layout(title_subtitle_text=among + (f" · {subtitle}" if subtitle else ""))
        result.insight = f"{among}: {result.insight}"
        result.method += (f" Institute type filter: only {who} are included ("
                          + "; ".join(f"{k}: {INSTITUTE_TYPES[k]}" for k in kinds)
                          + "), recognised from the cleaned institution names. Their ranks are their national NIRF "
                            "ranks; counts, averages, quartiles, z-scores and correlations are calculated within "
                            "this group.")
        if scope:
            result.method += f" State filter: only institutes located in {_state_text(scope)}."
        return result
    where = _state_text(scope)
    result.fig.update_layout(title_subtitle_text=f"Only institutions in {where}" + (f" · {subtitle}" if subtitle else ""))
    result.insight = f"Among institutions in {where}: {result.insight}"
    result.method += (f" State filter: only institutions located in {where} are included. Their ranks are their "
                      f"national NIRF ranks; counts, averages, quartiles, z-scores and correlations are calculated "
                      f"within this group.")
    return result
