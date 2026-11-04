"""The executor: runs a checked plan with OUR code and returns an Answer (chart, insight, assumptions, follow-ups).

The plan is data, never code: nothing the model writes is passed to exec() or eval(). An engine plan
can only call one of the public engine functions (core.runner, which refuses anything else), and a
custom plan can only call the Chart Builder (core.builder.build_chart), which filters, groups and
summarises whitelisted columns with fixed pandas operations. Before running, every value is translated
and checked by nlq/resolve.py:
  * category words -> the NIRF category; institution names -> institution keys; state codes -> states;
    parameter words -> column codes; year phrases -> years of that category;
  * years are fitted to what the function takes: a list (`years`), one year (`year`, the latest asked
    for) or two years (`start_year`/`end_year`, `year_a`/`year_b`: the first and last asked for; given
    the wrong way round, e.g. "from 2024 to 2019", they are swapped and the swap is noted);
  * `states` on a function without its own states parameter limits the analysis to those states;
  * a parameter the function does not have is dropped, and the drop is listed as an assumption.
Every translation is added to the answer's assumptions as a plain sentence, shown under the answer.
Institution names that need a guess come back with alternatives ("There's no IIT Bangalore ...": IISc,
IIM Bangalore), which the page offers as one-click buttons (with_institution() re-runs the same plan with
the other institution, without the model). An institution that took part but was never ranked gives a
'not_ranked' answer: a clear message and similar ranked institutions instead of an error.
"""

from __future__ import annotations

import copy
import inspect
import re
from dataclasses import dataclass, field

from core.builder import AGGREGATIONS, CHARTS, DIMENSIONS, MEASURES, build_chart
from core.data import NirfInputError, NotRankedError, fmt_years, institution_names, load_master, short_label
from core.questions import QUESTION_REGISTRY, get_question
from core.result import ChartResult
from core.runner import run
from nlq.catalog import data_facts, functions
from nlq.planner import ClarifyPlan, CustomPlan, EnginePlan, OutOfScopePlan
from nlq.resolve import (resolve_category, resolve_institution, resolve_parameter, resolve_state,
                         resolve_years)

YEAR_KEYS = ("years", "year", "start_year", "end_year", "year_a", "year_b")
YEAR_PAIRS = (("start_year", "end_year"), ("year_a", "year_b"))
PARAMETER_KEYS = ("x", "y", "param", "param_high", "param_low")
COUNT_ALIASES = {"n": ("top_n", "top"), "top_n": ("n", "top"), "top": ("top_n", "n")}
GROUP_WORDS = {"years": "year", "categories": "category", "states": "state", "regions": "region", "zone": "region",
               "zones": "region", "band": "rank_band", "bands": "rank_band", "rank band": "rank_band",
               "institutions": "institution", "institute": "institution", "college": "institution",
               "new entrants": "new_entrant", "new entrant": "new_entrant"}
CHART_WORDS = {"bar chart": "bar", "column": "bar", "column chart": "bar", "grouped bar": "grouped_bar",
               "stacked bar": "stacked_bar", "line chart": "line", "trend": "line", "scatterplot": "scatter",
               "scatter plot": "scatter", "box plot": "box", "boxplot": "box", "violin plot": "violin",
               "heat map": "heatmap", "pie chart": "pie", "donut": "pie", "strip chart": "strip"}


@dataclass
class Answer:
    kind: str                                   # chart | clarify | out_of_scope | not_ranked | error
    plan: dict
    title: str = ""
    result: ChartResult | None = None
    assumptions: list[str] = field(default_factory=list)
    message: str = ""
    options: list[str] = field(default_factory=list)
    follow_ups: list[str] = field(default_factory=list)
    engine: str | None = None                   # for "open the matching page" links ("builder" = custom)
    # Other institutions the person may have meant: {"typed": name in the plan, "key": ..., "label": "IISc"}.
    alternatives: list[dict] = field(default_factory=list)


def _as_list(value) -> list:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple, set)) else [value]


def _group(name: str) -> str:
    key = str(name).strip().lower()
    return GROUP_WORDS.get(key, key.replace(" ", "_"))


def _chart(name: str) -> str:
    key = str(name).strip().lower()
    return CHART_WORDS.get(key, key.replace(" ", "_"))


def check_plan(plan) -> list[str]:
    """Names in the plan that do not exist (empty list = fine). Used by the planner to ask for a retry."""
    problems = []
    if isinstance(plan, EnginePlan):
        if (plan.engine, plan.function) not in functions():
            same = [f for e, f in functions() if e == plan.engine]
            problems.append(f"{plan.engine}.{plan.function} is not an analysis"
                            + (f" (the {plan.engine} engine has: {', '.join(same)})" if same else ""))
    elif isinstance(plan, CustomPlan):
        for g in plan.group_by:
            if _group(g) not in DIMENSIONS:
                problems.append(f"group_by '{g}' is not one of {', '.join(DIMENSIONS)}")
        if _chart(plan.chart) not in CHARTS:
            problems.append(f"chart '{plan.chart}' is not one of {', '.join(CHARTS)}")
        if plan.agg not in AGGREGATIONS:
            problems.append(f"agg '{plan.agg}' is not one of {', '.join(AGGREGATIONS)}")
    return problems


# ---------- engine plans ----------

def _fit_category(raw: dict, sig, function: str, notes: list[str]) -> tuple[dict, str | None]:
    """Resolve category / categories to what the function takes; returns (params, category for years)."""
    out: dict = {}
    given = [c for c in _as_list(raw.pop("category", None)) + _as_list(raw.pop("categories", None))]
    names = []
    for c in dict.fromkeys(given):
        name, note = resolve_category(c)
        names.append(name)
        notes += [note] if note else []
    if "categories" in sig:
        if names:
            out["categories"] = names if len(names) > 1 else names[0]
        return out, names[0] if len(names) == 1 else (None if names else sig["categories"].default)
    if "category" in sig:
        if len(names) > 1 and function == "scatter_relation":        # the one function that pools categories
            out["category"] = names
            return out, None
        if len(names) > 1:
            notes.append(f"This chart shows one category, so {names[0]} is used.")
        if names:
            out["category"] = names[0]
        return out, out.get("category", sig["category"].default)
    if [n for n in names if n != "Overall"]:
        notes.append(f"This analysis compares every category, so '{', '.join(given)}' was not needed.")
    return out, None


def _fit_years(raw: dict, sig, category: str | None, notes: list[str]) -> dict:
    out: dict = {}
    asked: dict[str, list[int]] = {}
    for k in YEAR_KEYS:
        if k in raw:
            years, note = resolve_years(raw.pop(k), category)
            if not years:
                raise NirfInputError(f"No {category or 'NIRF'} ranking falls in the years you asked for.")
            asked[k] = years
            notes += [note] if note else []
    if not asked:
        return out
    every = sorted(set().union(*asked.values()))
    used = False
    if "years" in sig:
        out["years"], used = every, True
    if "year" in sig:
        chosen = asked.get("year") or every
        out["year"], used = chosen[-1], True
        if len(chosen) > 1:
            notes.append(f"This chart shows one year, so the latest of {fmt_years(chosen)} ({chosen[-1]}) is used.")
    for a, b in YEAR_PAIRS:
        if a in sig:
            lo, hi = asked.get(a), asked.get(b)
            if lo is None and hi is None:
                lo = hi = every
            if lo and hi is None and len(lo) > 1:     # "since 2020" -> from 2020 to the latest
                hi = lo
            if lo:
                out[a] = lo[0]
            if hi:
                out[b] = hi[-1]
            if a in out and b in out and out[a] > out[b]:    # "from 2024 back to 2019"
                notes.append(f"You gave the later year first ({out[a]} → {out[b]}); a change is always measured "
                             f"from the earlier year to the later one, so {out[b]} → {out[a]} is shown.")
                out[a], out[b] = out[b], out[a]
            used = True
    if not used:
        notes.append(f"This analysis always uses every year it can, so the years you asked for "
                     f"({fmt_years(every)}) were not applied.")
    return out


def _coerce(value, default):
    """Give a value the type of the parameter's default (e.g. '10' -> 10 for n)."""
    if isinstance(default, bool):
        return value if isinstance(value, bool) else str(value).strip().lower() in ("true", "yes", "1")
    if isinstance(default, int) and not isinstance(value, bool):
        return int(float(value))
    if isinstance(default, float):
        return float(value)
    return value


def _keep_ranked(keys: list[str], category, years, notes: list[str]) -> list[str]:
    """Leave out named institutions that NIRF did not rank in this category (and years), if others remain.

    E.g. "IIT Madras and IISc in Engineering": IISc is not in the Engineering list, so the chart shows IIT
    Madras alone and says why, instead of no chart at all. If none is ranked, the analysis explains it.
    """
    if len(keys) < 2 or not isinstance(category, str):
        return keys
    rows = load_master()
    rows = rows[rows["category_std"].eq(category)]
    if years:
        rows = rows[rows["year"].isin(_as_list(years))]
    ranked = set(rows["institution_key"])
    kept = [k for k in keys if k in ranked]
    if not kept or len(kept) == len(keys):
        return keys
    names = institution_names([k for k in keys if k not in ranked])
    when = f" in {fmt_years(sorted(set(_as_list(years))))}" if years else ""
    notes.append(f"{'; '.join(names.values())}: not ranked in {category}{when}, so left out of this chart.")
    return kept


def _institutions(names, notes: list[str], alternatives: list[dict] | None,
                  swaps: dict[str, str] | None) -> list[str]:
    """Institution keys for the names in a plan; assumptions go to `notes`, other options to `alternatives`,
    and each family swap to `swaps` as {name typed: short name used} ('IIT Bangalore': 'IIIT Bangalore').

    A NotRankedError is passed on with the name as typed, so the page can offer similar ranked institutions.
    """
    keys = []
    for n in dict.fromkeys(names):
        try:
            key, note, others = resolve_institution(n)
        except NotRankedError as e:
            e.typed = str(n)
            raise
        keys.append(key)
        notes += [note] if note else []
        if alternatives is not None:
            alternatives += [{"typed": str(n), "key": k, "label": short_label(k)} for k in others]
        if swaps is not None and note and note.startswith("There's no "):
            swaps[str(n)] = short_label(key)
    return keys


def _apply_swaps(answer: Answer, swaps: dict[str, str], model_notes: list[str]) -> None:
    """After 'IIT Bangalore' became IIIT Bangalore: the title and follow-ups name the institution actually shown,
    and the model's own notes about the name it was given ("Institution: IIT Bangalore, as named") are dropped,
    because our sentence ("There's no IIT Bangalore ...") replaces them."""
    for typed, label in swaps.items():
        pattern = re.compile(re.escape(typed), re.IGNORECASE)
        answer.title = pattern.sub(label, answer.title)
        answer.follow_ups = [pattern.sub(label, q) for q in answer.follow_ups]
        answer.assumptions = [a for a in answer.assumptions if not (a in model_notes and pattern.search(a))]


def engine_call(plan: EnginePlan, alternatives: list[dict] | None = None,
                swaps: dict[str, str] | None = None) -> tuple[dict, list[str] | None, list[str]]:
    """The engine parameters, the state scope and the assumptions for an engine plan."""
    fn = functions()[(plan.engine, plan.function)]
    sig = inspect.signature(fn).parameters
    raw = {k: v for k, v in plan.params.items() if v is not None and v != ""}
    notes: list[str] = []

    params, category = _fit_category(raw, sig, plan.function, notes)
    params.update(_fit_years(raw, sig, category if isinstance(category, str) else None, notes))

    names = _as_list(raw.pop("institutions", None)) + _as_list(raw.pop("institution", None))
    keys = _institutions(names, notes, alternatives, swaps)
    if keys and "institutions" in sig:
        params["institutions"] = _keep_ranked(keys, category, params.get("years"), notes)
    elif keys and "institution" in sig:
        params["institution"] = keys[0]
        if len(keys) > 1:
            notes.append("This chart follows one institution, so only the first one named is shown.")
    elif keys:
        notes.append("This analysis covers all institutions, so the institutions named were not singled out.")

    states = []
    for s in _as_list(raw.pop("states", None)) + _as_list(raw.pop("state", None)):
        name, note = resolve_state(s)
        states.append(name)
        notes += [note] if note else []
    scope = None
    if states and "states" in sig:
        params["states"] = states
    elif states:
        scope = states
        notes.append(f"Only institutions located in {', '.join(states)} are included (ranks stay national).")

    for k in PARAMETER_KEYS:
        if k in raw:
            value = raw.pop(k)
            if k in sig:
                params[k], note = resolve_parameter(value)
                notes += [note] if note else []
            else:
                notes.append(f"The option {k} = '{value}' does not apply to this chart and was ignored.")

    for k, v in raw.items():
        target = k if k in sig else next((a for a in COUNT_ALIASES.get(k, ()) if a in sig and a not in raw), None)
        if target is None:
            notes.append(f"The option {k} = {v!r} does not apply to this chart and was ignored.")
            continue
        default = sig[target].default
        try:
            params[target] = _coerce(v, default) if default is not inspect.Parameter.empty and default is not None \
                else v
        except (TypeError, ValueError):
            raise NirfInputError(f"'{v}' is not a valid value for {target}.") from None
    return params, scope, notes


# ---------- custom plans ----------

def custom_call(plan: CustomPlan, alternatives: list[dict] | None = None,
                swaps: dict[str, str] | None = None) -> tuple[dict, list[str]]:
    """The build_chart() arguments and the assumptions for a custom plan."""
    notes: list[str] = []
    f = plan.filters
    cats = []
    for c in f.categories:
        name, note = resolve_category(c)
        cats.append(name)
        notes += [note] if note else []
    years = None
    if f.years is not None:
        years, note = resolve_years(f.years, cats[0] if len(cats) == 1 else None)
        notes += [note] if note else []
    states = []
    for s in f.states:
        name, note = resolve_state(s)
        states.append(name)
        notes += [note] if note else []
    known_regions = {r.lower(): r for r in data_facts()["regions"]}
    regions = []
    for r in f.regions:
        key = str(r).strip().lower().replace("northeast", "north-east").replace("north east", "north-east")
        if key not in known_regions:
            raise NirfInputError(f"'{r}' is not a region. Regions: {', '.join(known_regions.values())}.")
        regions.append(known_regions[key])
    keys = _institutions(f.institutions, notes, alternatives, swaps)

    chart = _chart(plan.chart)
    groups = [_group(g) for g in plan.group_by]
    metric = str(plan.metric).strip().lower()
    agg = "count" if metric in ("count", "number", "institutions") else plan.agg
    y = None
    if agg != "count":
        y, note = resolve_parameter(metric)
        notes += [note] if note else []
        if y not in MEASURES:
            raise NirfInputError(f"'{plan.metric}' cannot be summarised in a chart.")
    if chart in ("scatter", "bubble", "histogram"):
        x, note = resolve_parameter(plan.x or (groups[0] if groups else "score"))
        notes += [note] if note else []
        rest = [g for g in groups if g in DIMENSIONS]
        color = rest[0] if rest else None
        facet = rest[1] if len(rest) > 1 else None
        y = y if chart != "histogram" else None
    else:
        if not groups:
            raise NirfInputError("A custom chart needs something to group by (year, state, category ...).")
        x = groups[0]
        color = groups[1] if len(groups) > 1 else None
        facet = groups[2] if len(groups) > 2 else None
    if not cats:
        notes.append("No category was named, so every category is included (scores of different categories "
                     "are on different scales).")
    args = dict(chart=chart, x=x, y=y, agg=agg, color=color, facet=facet,
                categories=cats or None, years=years, states=states or None, regions=regions or None,
                institutions=keys or None, rank_max=f.rank_max, limit=plan.limit)
    return args, notes


# ---------- running ----------

def _local_follow_ups(engine: str | None, function: str | None, asked: str) -> list[str]:
    """Sample questions from the same section (a fallback when the model gave fewer than three)."""
    same = [q for q in QUESTION_REGISTRY.values() if q.engine == engine and q.function != function]
    others = [q for q in QUESTION_REGISTRY.values() if q.engine != engine]
    return [q.text for q in same + others[::7] if q.text.lower() != asked.lower()]


def _follow_ups(given: list[str], engine, function, asked: str) -> list[str]:
    out = [q.strip() for q in given if q and q.strip() and q.strip().lower() != asked.lower()]
    for q in _local_follow_ups(engine, function, asked):
        if len(out) >= 3:
            break
        if q not in out:
            out.append(q)
    return list(dict.fromkeys(out))[:3]


def execute(plan, run_fn=None, question: str = "") -> Answer:
    """Run a plan and return the Answer. Never raises: data problems come back as kind='error'.

    run_fn(engine, function, params, states) runs an engine call (default core.runner.run; the page
    passes a cached version).
    """
    run_fn = run_fn or (lambda e, f, p, s: run(e, f, p, states=s))
    dump = plan.model_dump()
    if isinstance(plan, OutOfScopePlan):
        return Answer("out_of_scope", dump, message=plan.message,
                      follow_ups=_follow_ups([], None, None, question))
    if isinstance(plan, ClarifyPlan):
        return Answer("clarify", dump, message=plan.question, options=plan.options[:4])

    engine = plan.engine if isinstance(plan, EnginePlan) else "builder"
    function = plan.function if isinstance(plan, EnginePlan) else None
    answer = Answer("chart", dump, title=plan.title, assumptions=list(plan.assumptions), engine=engine,
                    follow_ups=_follow_ups(plan.follow_ups, engine, function, question))
    swaps: dict[str, str] = {}
    try:
        if isinstance(plan, EnginePlan):
            params, scope, notes = engine_call(plan, answer.alternatives, swaps)
            answer.assumptions += notes
            answer.plan["resolved_call"] = {"engine": plan.engine, "function": plan.function, "params": params,
                                            "states": scope}
            answer.result = run_fn(plan.engine, plan.function, params, scope)
        else:
            args, notes = custom_call(plan, answer.alternatives, swaps)
            answer.assumptions += notes
            answer.plan["resolved_call"] = {"builder": "build_chart", **args}
            answer.result = build_chart(**args)
    except NotRankedError as e:
        answer.kind, answer.message = "not_ranked", str(e)
        answer.alternatives = [{"typed": getattr(e, "typed", ""), "key": k, "label": short_label(k)}
                               for k in e.similar]
    except NirfInputError as e:
        answer.kind, answer.message = "error", str(e)
    except Exception as e:  # a plan our checks let through but the analysis cannot draw
        answer.kind = "error"
        answer.message = (f"The analysis could not be drawn with these settings ({type(e).__name__}: "
                          f"{str(e)[:160]}). Try asking in other words, or use the matching page below.")
    _apply_swaps(answer, swaps, list(plan.assumptions))
    answer.assumptions = list(dict.fromkeys(a for a in answer.assumptions if a))
    return answer


def with_institution(plan: dict, question: str, typed: str, key: str, label: str) -> tuple[dict, str]:
    """The same plan and question with the institution `typed` replaced by `key` (shown as `label`).

    Used by the "Use IISc instead" buttons: the plan is re-run as it is, without asking the model again.
    Returns (new plan, new question text).
    """
    new = copy.deepcopy({k: v for k, v in plan.items() if k != "resolved_call"})
    holder = new["filters"] if new.get("type") == "custom" else new.get("params", {})
    for k in ("institutions", "institution"):
        value = holder.get(k)
        if isinstance(value, list):
            holder[k] = [key if str(v).strip() == typed else v for v in value]
        elif value is not None and str(value).strip() == typed:
            holder[k] = key
    pattern = re.compile(re.escape(typed), re.IGNORECASE)
    if new.get("title"):
        new["title"] = pattern.sub(label, new["title"])
    if "assumptions" in new:      # the model's notes about the old name no longer apply
        new["assumptions"] = [a for a in new["assumptions"] if not pattern.search(a)]
        new["assumptions"].append(f"You chose {label} instead of {typed}.")
    if new.get("follow_ups"):
        new["follow_ups"] = [pattern.sub(label, q) for q in new["follow_ups"]]
    asked = pattern.sub(label, question) if pattern.search(question) else f"{question} (using {label})"
    return new, asked


def registry_plan(qid: str) -> EnginePlan:
    """The engine plan of an Annexure A question with its default parameters (no model needed)."""
    q = get_question(qid)
    return EnginePlan(type="engine", engine=q.engine, function=q.function,
                      params={k: v for k, v in q.default_params.items() if v is not None},
                      title=f"{q.id}: {q.text}", assumptions=[f"Ran the sample question {q.id} with its default "
                                                              f"settings."])
