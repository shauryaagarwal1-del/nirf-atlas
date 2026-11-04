"""Fit a chat plan to what the data actually has, and write down every change as a plain sentence.

The model only reads the question; it does not know which lists an institution is in or in which years.
These fixed rules, run by nlq/executor.py after the names are resolved, make sure the chart shows real
data instead of an error or an empty chart:
  * category auto-pick: a question that names institutions but no category uses Overall when every named
    institution is ranked there in every year asked; otherwise the category the institution is ranked in
    for the most years (ties: the most recent, then Overall). Several institutions get the category they
    share for the most years; if they share none, each is shown in its own category;
  * years the institution actually has: the asked years are cut to the span in which the institutions
    are listed in that category ("You asked for 2017-2025; IIT Dharwad is ranked in Engineering only in
    2023-2025, so the chart shows those years"). Missing years are never filled in;
  * years the category does not have: a year before a category started (SDG 2019) becomes the nearest
    year the category has (2025), and the answer says so;
  * band-only institutions: a rank question about an institution with no exact rank in the chosen
    category and years is drawn as its rank bands (trends.band_history); a score question gets a clear
    "NIRF did not publish scores" message with its bands and a button for the band chart;
  * cities used as places ("Bangalore colleges") become their state, because the data is filtered by state.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

import pandas as pd

from core.data import PLACE_SYNONYMS, category_years, fmt_years, load_master, short_label

# Analyses that follow named institutions (category and years are fitted to those institutions).
INSTITUTION_FUNCTIONS = {("trends", "rank_trajectory"), ("trends", "parameter_trends"), ("trends", "band_history"),
                         ("multivariate", "parameter_profile")}
# Of those, the ones that need scores (a band-only institution has none).
SCORE_FUNCTIONS = {("trends", "parameter_trends"), ("multivariate", "parameter_profile")}


def _and(items: list[str]) -> str:
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _names(keys: list[str]) -> str:
    return _and([short_label(k) for k in keys])


def _listed(keys: list[str]) -> pd.DataFrame:
    """The rows in which these institutions appear with an exact rank or a published band."""
    df = load_master()
    rows = df[df["institution_key"].isin(keys)]
    return rows[rows["rank"].notna() | rows["rank_band_nirf"].notna()]


# ---------- category ----------

@dataclass
class CategoryPick:
    category: str
    note: str | None = None
    # Institutions that share no category: [(category, keys), ...] for the 2nd, 3rd ... chart.
    others: list[tuple[str, list[str]]] = field(default_factory=list)


def _best_category(rows: pd.DataFrame) -> str:
    """The category with the most listed years; ties: the most recent last year, then Overall, then more exact
    ranks, then the name."""
    by = rows.groupby("category_std").agg(years=("year", "nunique"), last=("year", "max"),
                                          exact=("rank", lambda s: s.notna().sum()))
    by["overall"] = by.index == "Overall"
    return by.sort_values(["years", "last", "overall", "exact"], ascending=False).index[0]


def pick_category(keys: list[str], asked: list[int] | None) -> CategoryPick:
    """The category for a question that names institutions but no category (rules in the module docstring)."""
    rows = _listed(keys)
    window = rows[rows["year"].isin(asked)] if asked else rows
    if window.empty or not set(keys) <= set(window["institution_key"]):
        window = rows                                   # not ranked in the asked years at all: use every year
    overall_years = [y for y in (asked or category_years("Overall")) if y in category_years("Overall")]
    in_overall = window[window["category_std"].eq("Overall")]
    if overall_years and all(set(overall_years) <= set(in_overall.loc[in_overall["institution_key"].eq(k), "year"])
                             for k in keys):
        return CategoryPick("Overall")

    if len(keys) == 1:
        k = keys[0]
        category = _best_category(window)
        years = fmt_years(window.loc[window["category_std"].eq(category), "year"])
        ov = sorted(in_overall["year"].unique())
        if category == "Overall":
            return CategoryPick("Overall", f"{short_label(k)} is in the Overall ranking only in {fmt_years(ov)}, "
                                           f"its most ranked list, so I used Overall.")
        where = (f"is in the Overall ranking only in {fmt_years(ov)}" if ov else "is not in the Overall ranking")
        return CategoryPick(category, f"{short_label(k)} {where}; it is ranked in {category} ({years}), "
                                      f"so I used {category}.")

    shared = [c for c, g in window.groupby("category_std") if set(keys) <= set(g["institution_key"])]
    if shared:
        def score(c):
            g = window[window["category_std"].eq(c)]
            per_year = g.groupby("year")["institution_key"].nunique()
            return (int((per_year == len(keys)).sum()), len(per_year), int(per_year.index.max()), c == "Overall")
        category = max(shared, key=score)
        g = window[window["category_std"].eq(category)].groupby("year")["institution_key"].nunique()
        together = [int(y) for y, n in g.items() if n == len(keys)]
        when = f" (all of them in {fmt_years(together)})" if together else ""
        every = "in every year asked" if asked else "in every year"
        return CategoryPick(category, f"{_names(keys)} are not all in the Overall ranking {every}; "
                                      f"{category} is the ranking they share for the most years{when}, so I used "
                                      f"{category}.")

    groups: dict[str, list[str]] = {}
    for k in keys:
        groups.setdefault(_best_category(window[window["institution_key"].eq(k)]), []).append(k)
    each = "; ".join(f"{_names(ks)} in {c}" for c, ks in groups.items())
    first, *rest = groups.items()
    return CategoryPick(first[0], f"{_names(keys)} share no NIRF ranking list, so each is shown in its own "
                                  f"category: {each}. Ranks from different lists are not comparable.", rest)


# ---------- years ----------

def nearest_years(asked: list[int], available: list[int]) -> list[int]:
    """Each asked year moved to the closest year in `available` (a tie goes to the later year)."""
    return sorted({min(available, key=lambda a: (abs(a - y), -a)) for y in asked})


def category_year_note(value, years: list[int], raw: list[int], category: str) -> tuple[list[int], str | None]:
    """Fit years the person typed to the years `category` was published.

    `years` = what the resolver kept (inside the category), `raw` = the years typed (any category). If some
    typed years do not exist for the category, the ones that do are used; if none do, the nearest years.
    Phrases ('last 3 years') are already fitted by the resolver and pass unchanged.
    """
    available = category_years(category)
    explicit = isinstance(value, (int, float, list, tuple)) or bool(re.search(r"\b\d{4}\b", str(value)))
    outside = [y for y in raw if y not in available]
    inside = [y for y in years if y in available]
    if not explicit or not outside:
        return inside or years, None
    verb = lambda ys: "is" if len(ys) == 1 else "are"          # noqa: E731
    if inside:
        return inside, (f"{category} rankings exist only for {fmt_years(available)}, so {fmt_years(inside)} "
                        f"{verb(inside)} shown.")
    near = nearest_years(raw, available)
    return near, (f"{category} rankings exist only for {fmt_years(available)}, so {fmt_years(near)} {verb(near)} "
                  f"shown (the nearest to {fmt_years(raw)}).")


def institution_years(keys: list[str], category: str, years: list[int] | None,
                      explicit: bool) -> tuple[list[int] | None, str | None]:
    """The years to show for these institutions in this category, and the sentence that explains a change.

    Years are cut to the span from the first to the last year any of them is listed in the category (a
    year inside that span where one is not listed stays, as a gap). If none of the asked years falls in
    the span, the whole span is shown. `years` None = every year of the category.
    """
    rows = _listed(keys)
    have = sorted(rows.loc[rows["category_std"].eq(category), "year"].unique().tolist())
    if not have:
        return years, None                       # not in this category at all: the analysis explains it
    asked = list(years) if years else category_years(category)
    span = [y for y in category_years(category) if have[0] <= y <= have[-1]]
    used = [y for y in asked if y in span]
    if not set(used) & set(have):
        used = span
    if used == asked:
        return years, None
    who = _names(keys)
    verb = "is" if len(keys) == 1 else "are"
    shown = "those years" if used == have else fmt_years(used)
    lead = f"You asked for {fmt_years(asked)}; " if explicit else ""
    return used, f"{lead}{who} {verb} ranked in {category} only in {fmt_years(have)}, so the chart shows {shown}."


# ---------- band-only institutions ----------

def only_bands(keys: list[str], category: str, years: list[int] | None) -> bool:
    """True when these institutions are listed in the category and years, but never with an exact rank."""
    rows = _listed(keys)
    rows = rows[rows["category_std"].eq(category)]
    if years:
        rows = rows[rows["year"].isin(years)]
    return not rows.empty and rows["rank"].isna().all()


def bands_text(key: str, category: str, years: list[int] | None = None) -> str:
    """'201-250 in 2020 and 251-300 in 2021' (consecutive years in the same band are joined)."""
    rows = _listed([key])
    rows = rows[rows["category_std"].eq(category) & rows["rank"].isna()].sort_values("year")
    if years:
        rows = rows[rows["year"].isin(years)]
    runs: list[tuple[list[int], str]] = []
    for y, band in zip(rows["year"], rows["rank_band_nirf"]):
        if runs and runs[-1][1] == band:
            runs[-1][0].append(int(y))
        else:
            runs.append(([int(y)], band))
    return _and([f"{band} in {fmt_years(ys)}" for ys, band in runs]) if runs else ""


@dataclass
class NoScores:
    """A score question about institutions NIRF published no scores for: the message and the chart to offer."""
    message: str
    plan: dict
    label: str


def missing_scores(keys: list[str], category: str, years: list[int] | None) -> NoScores | None:
    """None when at least one named institution has a published score in this category and these years."""
    rows = _listed(keys)
    rows = rows[rows["category_std"].eq(category)]
    if years:
        rows = rows[rows["year"].isin(years)]
    if rows.empty or rows["score"].notna().any():
        return None
    when = fmt_years(sorted(rows["year"].unique()))
    parts = []
    for k in keys:
        bands = bands_text(k, category, years)
        exact = rows[rows["institution_key"].eq(k) & rows["rank"].notna()]
        ranks = _and([f"{r} in {y}" for y, r in zip(exact["year"], exact["rank_raw"])]) if len(exact) else ""
        placed = "; ".join(p for p in (f"placed in band {bands}" if bands else "",
                                       f"exact rank {ranks}" if ranks else "") if p)
        parts.append(f"{short_label(k)} was {placed}" if placed else f"{short_label(k)} is listed")
    only_bands = rows["rank"].isna().all()
    why = ("NIRF publishes scores only for the institutions in its exact-rank list; positions below it are "
           "published as rank bands, with no score." if only_bands else
           f"The {category} ranking publishes ranks only, with no scores.")
    message = (f"NIRF did not publish scores for {_names(keys)} in {category} ({when}). {'. '.join(parts)}. {why}")
    function = "band_history" if only_bands else "rank_trajectory"
    plan = {"type": "engine", "engine": "trends", "function": function,
            "params": {"institutions": list(keys), "category": category, "years": sorted(rows["year"].unique().tolist())},
            "title": f"{_names(keys)}: {'rank bands' if only_bands else 'ranks'} in {category}",
            "assumptions": ["NIRF published no scores here, so the chart shows what it did publish."]}
    return NoScores(message, plan, "Show the rank bands chart" if only_bands else "Show the rank chart")


# ---------- places ----------

# Big cities people name as places, for when the data spells them differently (Bengaluru, Gurugram ...).
CITY_STATES = {"bangalore": "Karnataka", "bombay": "Maharashtra", "pune": "Maharashtra", "madras": "Tamil Nadu",
               "calcutta": "West Bengal", "hyderabad": "Telangana", "ahmedabad": "Gujarat", "jaipur": "Rajasthan",
               "lucknow": "Uttar Pradesh", "noida": "Uttar Pradesh", "gurgaon": "Haryana", "coimbatore": "Tamil Nadu",
               "bhubaneswar": "Odisha", "chandigarh": "Chandigarh", "kochi": "Kerala", "cochin": "Kerala",
               "mysore": "Karnataka", "mysuru": "Karnataka", "manipal": "Karnataka", "vellore": "Tamil Nadu",
               "nagpur": "Maharashtra", "indore": "Madhya Pradesh", "bhopal": "Madhya Pradesh"}


def _place(text: str) -> str:
    words = re.sub(r"[^a-z ]+", " ", str(text).lower()).split()
    return " ".join(PLACE_SYNONYMS.get(w, w) for w in words)


@lru_cache(maxsize=1)
def _city_index() -> dict[str, str]:
    """City (one spelling per place) -> the state most of its institutions are in, read from the master table."""
    df = load_master().dropna(subset=["city"])
    df = df.assign(place=df["city"].map(_place))
    return df.groupby("place")["state"].agg(lambda s: s.value_counts().index[0]).to_dict()


def city_state(text: str) -> str | None:
    """The state of a city typed as a place ('Bangalore', 'Bengaluru' -> Karnataka), or None if it is not a city."""
    place = _place(text)
    for suffix in (" city", " colleges", " college", " institutes"):
        place = place.removesuffix(suffix)
    return CITY_STATES.get(place) or _city_index().get(place)
