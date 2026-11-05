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
'not_ranked' answer: a clear message and similar ranked institutions instead of an error. A name that fits
several institutions ("NIT", "Christian Medical College") gives a 'clarify' answer with up to 4 real
institutions as buttons.
"Institute_types" (or a name such as "IITs" / "all IIMs" in the institutions list, or "IITs" in the question
of an analysis that covers every institution) limits the analysis to those institute types (core.runner);
the answer then starts with "Among IITs only".
After the names are resolved, nlq/adapt.py fits the plan to what the data has: it picks the category the
named institutions are actually ranked in when none was named, cuts the years to those the institutions
are listed in, moves a year a category does not have to the nearest one, draws rank bands for institutions
NIRF placed only in bands, and answers a score question about such an institution with a 'no_scores'
message and a button for its band chart. A plan's "notice" (a prediction answered with past data) is
shown above the chart.
"""

from __future__ import annotations

import copy
import inspect
import re
from dataclasses import dataclass, field

from core.builder import AGGREGATIONS, CHARTS, DIMENSIONS, MEASURES, build_chart
from core.data import (INSTITUTE_TYPES, AmbiguousInstitutionError, NirfInputError, NotRankedError, category_years,
                       check_types, fmt_years, institute_type_code, institution_names, load_master, short_label,
                       type_plural)
from core.questions import QUESTION_REGISTRY, get_question
from core.result import ChartResult
from core.runner import run
from nlq.adapt import (INSTITUTION_FUNCTIONS, SCORE_FUNCTIONS, NoScores, category_year_note, institution_years,
                       missing_scores, only_bands, pick_category)
from nlq.catalog import data_facts, functions
from nlq.planner import ClarifyPlan, CustomPlan, EnginePlan, OutOfScopePlan
from nlq.resolve import (resolve_category, resolve_institution, resolve_parameter, resolve_region, resolve_state,
                         resolve_years)

YEAR_KEYS = ("years", "year", "start_year", "end_year", "year_a", "year_b")
TYPE_KEYS = ("institute_types", "institute_type", "types", "type")
# Plural institute-type words in a question ("Which IITs ...", "all IIMs"): the analysis is about that type.
_TYPE_WORDS = re.compile(r"\b(?:all\s+(?:the\s+)?)?(IITs|NITs|IIMs|IIITs|IISERs|NLUs|NIPERs)\b|\ball\s+(?:the\s+)?"
                         r"(IIT|NIT|IIM|IIIT|IISER|AIIMS|NLU|NIPER)s?\b", re.IGNORECASE)
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
    kind: str                                   # chart | clarify | out_of_scope | not_ranked | no_scores | error
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
    notice: str = ""                            # shown above the chart (a prediction answered with past data)
    more: list[ChartResult] = field(default_factory=list)   # one more chart per extra category (no shared one)
    next_plan: dict | None = None               # no_scores: the chart to offer as a button ...
    next_label: str = ""                        # ... and the button's text


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
            value = raw.pop(k)
            years, note = resolve_years(value, category, check=False)
            if category:            # a year the category does not have -> the nearest one it has (SDG 2019 -> 2025)
                try:
                    typed = resolve_years(value, check=False)[0]
                except NirfInputError:
                    typed = years
                years, fixed = category_year_note(value, years, typed, category)
                note = fixed or note
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
        except (NotRankedError, AmbiguousInstitutionError) as e:
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


def _asked_years(raw: dict) -> list[int] | None:
    """Every year named in the plan, read without a category (used to pick the category)."""
    years: set[int] = set()
    for k in YEAR_KEYS:
        if k in raw:
            try:
                years |= set(resolve_years(raw[k], check=False)[0])
            except NirfInputError:
                pass
    return sorted(years) or None


def _overall_not_asked(raw: dict, question: str) -> bool:
    """The plan says Overall but the question never did (the model's default, not the person's choice)."""
    given = _as_list(raw.get("category")) + _as_list(raw.get("categories"))
    if len(given) != 1 or not question:
        return False
    try:
        return resolve_category(given[0])[0] == "Overall" and "overall" not in question.lower()
    except NirfInputError:
        return False


def engine_call(plan: EnginePlan, alternatives: list[dict] | None = None, swaps: dict[str, str] | None = None,
                question: str = "", info: dict | None = None) -> tuple[dict, list[str] | None, list[str]]:
    """The engine parameters, the state scope and the assumptions for an engine plan.

    `info` (if given) receives what nlq/adapt.py changed: "function" (band_history instead of rank_trajectory),
    "category_picked", "no_scores" (a NoScores) and "more" (extra (function, params) calls, one per category,
    for institutions that share no category).
    """
    fn = functions()[(plan.engine, plan.function)]
    sig = inspect.signature(fn).parameters
    raw = {k: v for k, v in plan.params.items() if v is not None and v != ""}
    notes: list[str] = []
    info = {} if info is None else info
    function = plan.function
    follows = (plan.engine, plan.function) in INSTITUTION_FUNCTIONS

    names = _as_list(raw.pop("institutions", None)) + _as_list(raw.pop("institution", None))
    types = _types(raw, names, sig, question, notes)
    info["types"] = types
    names = [n for n in names if not _is_type_word(n, sig)]
    keys = _institutions(names, notes, alternatives, swaps)

    # Category auto-pick: institutions named, no category named (rules in nlq/adapt.py).
    if follows and keys and "category" in sig and _overall_not_asked(raw, question):
        raw.pop("category", None)
        raw.pop("categories", None)
    named_category = "category" in raw or "categories" in raw
    params, category = _fit_category(raw, sig, plan.function, notes)
    others: list[tuple[str, list[str]]] = []
    if follows and keys and "category" in sig and not named_category:
        pick = pick_category(keys, _asked_years(raw))
        params["category"] = category = pick.category
        if pick.note:
            notes.append(pick.note)
            info["category_picked"] = True
        others = pick.others
        keys = [k for k in keys if all(k not in ks for _, ks in others)]
    explicit_years = any(k in raw for k in YEAR_KEYS)
    params.update(_fit_years(raw, sig, category if isinstance(category, str) else None, notes))
    asked_years = params.get("years")

    if keys and "institutions" in sig:
        params["institutions"] = _keep_ranked(keys, category, params.get("years"), notes)
    elif keys and "institution" in sig:
        params["institution"] = keys[0]
        if len(keys) > 1:
            notes.append("This chart follows one institution, so only the first one named is shown.")
    elif keys:
        notes.append("This analysis covers all institutions, so the institutions named were not singled out.")

    states = []
    for s in (_as_list(raw.pop("states", None)) + _as_list(raw.pop("state", None))
              + _as_list(raw.pop("regions", None)) + _as_list(raw.pop("region", None))):
        region = resolve_region(s)
        if region:                                   # 'South India' -> the states of the South region
            states += region[1]
            notes.append(region[2])
            continue
        name, note = resolve_state(s)
        states.append(name)
        notes += [note] if note else []
    states = list(dict.fromkeys(states))
    scope = None
    if states and "states" in sig:
        params["states"] = states
    elif states:
        scope = states
        if not any(n.startswith("'") and " region in our data" in n for n in notes):
            notes.append(f"Only institutions located in {', '.join(states)} are included (ranks stay national).")

    for k in PARAMETER_KEYS:
        if k in raw:
            value = raw.pop(k)
            if k in sig:
                params[k], note = resolve_parameter(value, category if isinstance(category, str) else None)
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

    if follows and isinstance(category, str):
        chosen = _as_list(params.get("institutions")) or _as_list(params.get("institution"))
        function = _fit_to_institutions(plan.engine, function, params, chosen, category, sig, explicit_years, notes,
                                        info)
        more = []
        for other_category, other_keys in others:      # institutions that share no category: one chart each
            extra = {k: v for k, v in params.items() if k not in ("years", "institution", "institutions")}
            extra["category"] = other_category
            extra["institutions" if "institutions" in sig else "institution"] = (
                other_keys if "institutions" in sig else other_keys[0])
            if asked_years:
                kept = [y for y in asked_years if y in category_years(other_category)]
                if kept:
                    extra["years"] = kept
            extra_fn = _fit_to_institutions(plan.engine, plan.function, extra, other_keys, other_category, sig,
                                            explicit_years, notes, {})
            more.append((extra_fn, extra))
        info["more"] = more
    info["function"] = function
    return params, scope, notes


def _is_type_word(name, sig) -> bool:
    """'IITs', 'all IIMs', 'the NITs' always name a type; a bare 'IIT' only for an analysis of every institution
    (for a chart of named institutions, 'IIT' is a vague name and the person is asked which one)."""
    code = institute_type_code(name)
    if code is None:
        return False
    t = str(name).strip().lower()
    plural = t != code.lower() or code == "AIIMS" and t.startswith("all")
    return plural or not ({"institutions", "institution"} & set(sig))


def _types(raw: dict, names: list, sig, question: str, notes: list[str]) -> list[str]:
    """Institute types to limit the analysis to: the plan's institute_types, type words in its institutions
    list ('IITs'), or plural type words in the question when the plan names no institution."""
    given = [v for k in TYPE_KEYS for v in _as_list(raw.pop(k, None))]
    types = check_types(given) if given else []
    types += [institute_type_code(n) for n in names if _is_type_word(n, sig)]
    if not types and not names and question:
        types += [institute_type_code(a or b) for a, b in _TYPE_WORDS.findall(question)]
    types = list(dict.fromkeys(t for t in types if t))
    if types:
        notes.append(f"Only {' and '.join(type_plural(t) for t in types)} are included ("
                     + "; ".join(INSTITUTE_TYPES[t] for t in types) + "); ranks stay national.")
    return types


def _fit_to_institutions(engine: str, function: str, params: dict, keys: list[str], category: str, sig,
                         explicit_years: bool, notes: list[str], info: dict) -> str:
    """Years the institutions actually have, band chart for band-only institutions, no-scores check.

    Changes `params` in place and returns the function to run (band_history instead of rank_trajectory when
    NIRF published only bands for these institutions)."""
    if not keys:
        return function
    if "years" in sig:
        years, note = institution_years(keys, category, params.get("years"), explicit_years)
        if note:
            params["years"] = years
            # No years asked and the category note already gave the years: the cut needs no second sentence.
            if explicit_years or not info.get("category_picked"):
                notes.append(note)
    years = params.get("years") or ([params["year"]] if "year" in params else None)
    if function == "rank_trajectory" and only_bands(keys, category, years):
        names = ", ".join(short_label(k) for k in keys)
        notes.append(f"NIRF published no exact {category} rank for {names} in these years, only rank bands, so the "
                     f"chart shows the bands instead of a rank line.")
        function = "band_history"
    if (engine, function) in SCORE_FUNCTIONS:
        missing = missing_scores(keys, category, years)
        if missing:
            info["no_scores"] = missing
    return function


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
    states, regions = [], []
    for s in f.states:
        region = resolve_region(s)
        if region:                                   # 'South India' typed as a state -> the region filter
            regions.append(region[0])
            notes.append(region[2])
            continue
        name, note = resolve_state(s)
        states.append(name)
        notes += [note] if note else []
    known_regions = {r.lower(): r for r in data_facts()["regions"]}
    for r in f.regions:
        key = str(r).strip().lower().replace("northeast", "north-east").replace("north east", "north-east")
        if key not in known_regions:
            region = resolve_region(r)
            if region is None:
                raise NirfInputError(f"'{r}' is not a region. Regions: {', '.join(known_regions.values())}.")
            notes.append(region[2])
            key = region[0].lower()
        regions.append(known_regions[key])
    regions = list(dict.fromkeys(regions))
    keys = _institutions(f.institutions, notes, alternatives, swaps)

    chart = _chart(plan.chart)
    groups = [_group(g) for g in plan.group_by]
    metric = str(plan.metric).strip().lower()
    agg = "count" if metric in ("count", "number", "institutions") else plan.agg
    y = None
    if agg != "count":
        y, note = resolve_parameter(metric, cats[0] if len(cats) == 1 else None)
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
    run_fn = run_fn or (lambda e, f, p, s, t=None: run(e, f, p, states=s, types=t))
    dump = plan.model_dump()
    if isinstance(plan, OutOfScopePlan):
        return Answer("out_of_scope", dump, message=plan.message,
                      follow_ups=_follow_ups([], None, None, question))
    if isinstance(plan, ClarifyPlan):
        return Answer("clarify", dump, message=plan.question, options=plan.options[:4])

    engine = plan.engine if isinstance(plan, EnginePlan) else "builder"
    function = plan.function if isinstance(plan, EnginePlan) else None
    answer = Answer("chart", dump, title=plan.title, assumptions=list(plan.assumptions), engine=engine,
                    follow_ups=_follow_ups(plan.follow_ups, engine, function, question), notice=plan.notice.strip())
    swaps: dict[str, str] = {}
    try:
        if isinstance(plan, EnginePlan):
            info: dict = {}
            params, scope, notes = engine_call(plan, answer.alternatives, swaps, question, info)
            if info.get("category_picked"):     # the model's "Category: Overall, as none was named" no longer holds
                answer.assumptions = [a for a in answer.assumptions if not re.search(r"categor", a, re.I)]
            answer.assumptions += notes
            function = info.get("function", plan.function)
            types = info.get("types") or []
            answer.plan["resolved_call"] = {"engine": plan.engine, "function": function, "params": params,
                                            "states": scope, **({"institute_types": types} if types else {})}
            extra = (types,) if types else ()           # a run_fn without a types argument still works
            missing: NoScores | None = info.get("no_scores")
            if missing:
                answer.kind, answer.message = "no_scores", missing.message
                answer.next_plan, answer.next_label = missing.plan, missing.label
            else:
                answer.result = run_fn(plan.engine, function, params, scope, *extra)
                answer.more = [run_fn(plan.engine, f, p, scope, *extra) for f, p in info.get("more", [])]
        else:
            args, notes = custom_call(plan, answer.alternatives, swaps)
            answer.assumptions += notes
            answer.plan["resolved_call"] = {"builder": "build_chart", **args}
            answer.result = build_chart(**args)
    except AmbiguousInstitutionError as e:
        typed = getattr(e, "typed", "")
        answer.kind = "clarify"
        answer.message = (f"'{typed}' fits {e.total} institutions in the NIRF data. Which one did you mean? "
                          f"The best known are below; you can also type the full name.")
        answer.alternatives = [{"typed": typed, "key": k, "label": option_label(k), "picked": True}
                               for k in e.options]
        answer.options = [c["label"] for c in answer.alternatives]
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


def option_label(key: str) -> str:
    """A button label that tells campuses apart: 'Christian Medical College (Vellore)', 'NIT Rourkela'."""
    label = short_label(key)
    rows = load_master()
    city = rows.loc[rows["institution_key"].eq(key), "city"].dropna()
    city = str(city.iloc[-1]).title() if len(city) else ""
    return f"{label} ({city})" if city and city.lower() not in label.lower() else label


def with_institution(plan: dict, question: str, typed: str, key: str, label: str,
                     picked: bool = False) -> tuple[dict, str]:
    """The same plan and question with the institution `typed` replaced by `key` (shown as `label`).

    Used by the "Use IISc instead" buttons and by the buttons that answer "which NIT did you mean?"
    (picked=True): the plan is re-run as it is, without asking the model again.
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
    pattern = re.compile(r"(?<!\w)" + re.escape(typed) + r"(?!\w)", re.IGNORECASE)
    if new.get("title"):
        new["title"] = pattern.sub(label, new["title"])
    if "assumptions" in new:      # the model's notes about the old name no longer apply
        new["assumptions"] = [a for a in new["assumptions"] if not pattern.search(a)]
        new["assumptions"].append(f"You picked {label} for '{typed}'." if picked else
                                  f"You chose {label} instead of {typed}.")
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
