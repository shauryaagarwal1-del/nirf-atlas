"""Run any engine function by name, optionally for the institutions of chosen states only.

One entry point used by the dashboard pages (app/components.py) and later by the Ask NIRF chat, so
both run analyses the same way:
  * only the 8 engines and their public functions can be called (no other code);
  * states=["Kerala"] runs the analysis on Kerala's institutions only (core.data.only_states), and the
    answer says so: the chart subtitle, the one-line answer and the method all name the states, so a
    "Kerala only" chart can never be mistaken for an all-India one.

Ranks stay the national NIRF ranks; averages, quartiles, z-scores and correlations are then
calculated within the chosen states.
"""

from __future__ import annotations

import importlib
import inspect

from core.data import NirfInputError, check_category, load_master, only_states
from core.result import ChartResult

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


def run(engine: str, function: str, params: dict | None = None, states=None) -> ChartResult:
    """Call the engine function with `params`; with `states`, only for institutions in those states."""
    fn = engine_function(engine, function)
    params = dict(params or {})
    if not states or takes_states(engine, function):
        return fn(**params)

    with only_states(states) as scope:
        where = _state_text(scope)
        if "category" in params:
            category = check_category(params["category"])
            if not load_master()["category_std"].eq(category).any():
                raise NirfInputError(f"No institution in {where} is ranked in {category}. "
                                     f"Choose another category or clear the state filter.")
        try:
            result = fn(**params)
        except NirfInputError as e:
            raise NirfInputError(f"{e} (Only institutions in {where} are included; clear the state filter "
                                 f"to use all of India.)") from None

    subtitle = result.fig.layout.title.subtitle.text or ""
    result.fig.update_layout(title_subtitle_text=f"Only institutions in {where}" + (f" · {subtitle}" if subtitle else ""))
    result.insight = f"Among institutions in {where}: {result.insight}"
    result.method += (f" State filter: only institutions located in {where} are included. Their ranks are their "
                      f"national NIRF ranks; counts, averages, quartiles, z-scores and correlations are calculated "
                      f"within this group.")
    return result
