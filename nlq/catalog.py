"""The catalog: everything the language model is told about our data and analyses, generated from the code.

The model needs to know what it can ask for, not the data itself. catalog_text() writes a compact
description of:
  * the dataset: the columns (with meanings), the years, the categories and the years each one was
    published, the states and regions, the parameter codes;
  * every public engine function: its name and parameters (read from the function signature), its
    docstring (the questions it answers, the definition and the method) and the Annexure A questions
    that use it, with their default parameters (from core.questions.QUESTION_REGISTRY);
  * the safe custom query (core.builder.build_chart): which groups, numbers, aggregations and charts exist.
Because it is generated, a new engine function or a new sample question appears in the chat automatically.

Also here: which dashboard page shows each engine (for "open this page" links) and closest_questions(),
which finds the sample questions most similar to a typed question without any model (used when the
model cannot be reached).
"""

from __future__ import annotations

import importlib
import inspect
import re
from functools import lru_cache

from rapidfuzz import fuzz

from core.builder import AGGREGATIONS, CHARTS, DIMENSIONS, MEASURES
from core.data import LABELS, fmt_years, load_master
from core.questions import QUESTION_REGISTRY, Question
from core.runner import ENGINES

# The Explore page that shows each engine's analyses (path relative to app/, title).
ENGINE_PAGES = {
    "trends": ("pages/trends.py", "Trends"),
    "geography": ("pages/geography.py", "Geography"),
    "univariate": ("pages/distributions.py", "Distributions"),
    "distribution": ("pages/distributions.py", "Distributions"),
    "bivariate": ("pages/relationships.py", "Relationships"),
    "multivariate": ("pages/multi_parameter.py", "Multi-Parameter"),
    "mobility": ("pages/mobility.py", "Mobility"),
    "outliers": ("pages/outliers.py", "Outliers"),
}

COLUMNS = {
    "year": "ranking year, 2017-2025",
    "category": "NIRF ranking list (Overall, Engineering ...); scores compare only within one category-year",
    "institution": "the institution (canonical name; spelling variants are merged)",
    "state / region / city": "where the institution is located (34 states and UTs, 6 regions)",
    "rank": "exact rank NIRF published (1 = best); empty when NIRF published only a band such as 101-150",
    "rank_band": "rank group: 1-10, 11-25, 26-50, 51-100, 101-150, 151-200, 201-300",
    "score": "overall NIRF score out of 100 (weighted sum of the parameters)",
    "tlr, rpc, go, oi, pr": "the five parameter scores (each out of 100): " + "; ".join(
        LABELS[p] for p in ("tlr", "rpc", "go", "oi", "pr")),
    "qnr, qlr, sfc": "Research Institutions use these instead of tlr, rpc, go: " + "; ".join(
        LABELS[p] for p in ("qnr", "qlr", "sfc")),
    "is_new_entrant": "first year the institution appears in that category's list",
}
NOT_IN_DATA = ("fees, salaries or placement packages, student numbers, cut-offs, QS/THE world rankings, NIRF 2016 "
               "or any year after 2025, and anything not about NIRF")


def functions() -> dict[tuple[str, str], object]:
    """(engine, function name) -> the function, for every public engine function."""
    out = {}
    for engine in ENGINES:
        module = importlib.import_module(f"core.engines.{engine}")
        for name, fn in inspect.getmembers(module, inspect.isfunction):
            if not name.startswith("_") and fn.__module__ == module.__name__:
                out[(engine, name)] = fn
    return out


def _one_line(text: str) -> str:
    return " ".join(str(text).split())


@lru_cache(maxsize=1)
def data_facts() -> dict:
    """Years, categories (with their years), states and regions, read from the master table."""
    df = load_master()
    cats = {c: sorted(g["year"].unique().tolist()) for c, g in df.groupby("category_std")}
    order = ["Overall"] + sorted(c for c in cats if c != "Overall")
    return {"years": sorted(df["year"].unique().tolist()), "categories": {c: cats[c] for c in order},
            "states": sorted(df["state"].unique()), "regions": sorted(df["region"].dropna().unique())}


def describe_data() -> str:
    f = data_facts()
    lines = ["# DATA: one row per year x category x institution (the cleaned NIRF master table)",
             "Columns:"] + [f"- {k}: {v}" for k, v in COLUMNS.items()]
    lines += [f"Years: {fmt_years(f['years'])} (latest = {f['years'][-1]}).",
              "Categories and the years NIRF published them:"]
    lines += [f"- {c}: {fmt_years(ys)}" for c, ys in f["categories"].items()]
    lines += [f"States: {', '.join(f['states'])}.", f"Regions: {', '.join(f['regions'])}.",
              "Innovation and SDG publish ranks/bands only (no scores). A smaller rank is better; "
              "improvement = old rank - new rank (positive = moved up).",
              f"Not in the data: {NOT_IN_DATA}."]
    return "\n".join(lines)


def _questions_by_function() -> dict[tuple[str, str], list[Question]]:
    out: dict[tuple[str, str], list[Question]] = {}
    for q in QUESTION_REGISTRY.values():
        out.setdefault((q.engine, q.function), []).append(q)
    return out


def describe_functions() -> str:
    by_fn = _questions_by_function()
    lines = ["# ANALYSES: engine.function(parameters) - use these names exactly"]
    for (engine, name), fn in functions().items():
        sig = str(inspect.signature(fn)).replace(" -> 'ChartResult'", "").replace("'", "")
        lines.append(f"\n## {engine}.{name}{sig}")
        lines.append(_one_line(inspect.getdoc(fn) or ""))
        for q in by_fn.get((engine, name), []):
            lines.append(f"Sample {q.id}: \"{q.text}\" -> params {q.default_params}")
    return "\n".join(lines)


def describe_custom() -> str:
    return "\n".join([
        "# CUSTOM QUERY (only when no analysis above fits): a safe group-and-summarise chart",
        f"group_by (1 to 3 items: x axis, then colour, then panels): {', '.join(DIMENSIONS)}",
        f"metric: count (number of institutions) or one of {', '.join(MEASURES)}",
        f"agg: {', '.join(AGGREGATIONS)} (use count when metric is count)",
        f"chart: {', '.join(CHARTS)}. line needs group_by[0] = year; pie and stacked_bar need metric = count; "
        "grouped_bar, stacked_bar and heatmap need two group_by items; scatter/bubble/histogram need x "
        "(a number) instead of a group.",
        "filters: categories (list), years, states (list), regions (list), institutions (list), "
        "rank_max (keep ranks 1..rank_max, e.g. 100 for 'top 100')",
        "limit: for bar charts, show only the N largest groups (e.g. 10 for 'top 10 states').",
    ])


@lru_cache(maxsize=1)
def catalog_text() -> str:
    """The full catalog the planner sends to the model (about 9,000 tokens)."""
    return "\n\n".join([describe_data(), describe_functions(), describe_custom()])


# ---------- offline helpers ----------

_STOP = {"the", "a", "an", "of", "in", "to", "and", "or", "is", "are", "which", "what", "how", "have", "has", "do",
         "does", "did", "for", "by", "with", "institution", "institutions", "institute", "institutes", "college",
         "colleges", "nirf", "show", "me", "their", "there", "than", "from", "between", "selected", "a", "any"}
# Words with the same meaning share one stem, so "most" matches "highest" and "fell" matches "decline".
_SAME = {"most": "high", "highest": "high", "largest": "high", "greatest": "high", "biggest": "high",
         "improved": "improv", "improvement": "improv", "climbed": "improv", "climbers": "improv", "rose": "improv",
         "declined": "declin", "decline": "declin", "fell": "declin", "fallers": "declin", "dropped": "declin",
         "varies": "variab", "variability": "variab", "spread": "dispers", "dispersed": "dispers",
         "research": "rpc", "teaching": "tlr", "perception": "pr", "correlation": "correl", "related": "correl",
         "relate": "correl", "associated": "correl", "ranks": "rank", "ranking": "rank", "rankings": "rank",
         "scores": "score", "states": "state", "moved": "move", "movements": "move", "changed": "chang",
         "change": "chang", "new": "new", "newly": "new", "entrants": "new", "appearing": "new"}


def _words(text: str) -> set[str]:
    words = re.sub(r"[^a-z0-9 ]+", " ", str(text).lower()).split()
    return {_SAME.get(w, w[:6]) for w in words if w not in _STOP}


def closest_questions(text: str, k: int = 3) -> list[Question]:
    """The k sample questions that share the most words with `text` (no model involved).

    Score = share of the typed question's words (filler words removed, synonyms such as most/highest
    merged) that also appear in the sample question; ties are broken by rapidfuzz word-order similarity.
    Used to suggest a ready-made answer when the model cannot be reached. Questions sharing no word
    are not suggested.
    """
    typed = _words(text)
    if not typed:
        return []
    scored = []
    for q in QUESTION_REGISTRY.values():
        overlap = len(typed & _words(q.text)) / len(typed)
        scored.append((overlap, fuzz.token_sort_ratio(str(text).lower(), q.text.lower()), q))
    scored.sort(key=lambda t: (-t[0], -t[1]))
    return [q for overlap, _, q in scored[:k] if overlap > 0]


def page_for(engine: str) -> tuple[str, str]:
    """(page path, page title) of the Explore page for an engine; the Chart Builder for custom queries."""
    return ENGINE_PAGES.get(engine, ("pages/chart_builder.py", "Chart Builder"))
