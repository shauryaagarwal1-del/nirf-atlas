"""Shared data access for every engine: load the master table, filter it, and check user inputs.

The engines never read files themselves. They call load_master() once (cached), narrow it with
filter_df(), and use the check_* / find_institutions() helpers so that a wrong input produces a
friendly message ("IIT Madras is not ranked in Law in 2019") instead of an empty chart.

Rank conventions used everywhere (same as the cleaning pipeline):
  * a smaller rank is better; improvement = old_rank - new_rank (positive = moved up);
  * `rank` is the exact rank NIRF printed (empty when NIRF published only a band);
  * `rank_upper` (added here) is the worst position a row can have: the exact rank, or the upper
    end of NIRF's own band (a "76-100" row is certainly within the top 100, never within the top 75).

State scope: inside `with only_states(["Kerala"]):` every load_master() call returns only the rows of
institutions located in those states, so ANY engine analysis can be asked "for Kerala only" without
each engine needing its own state filter. Ranks stay the national NIRF ranks.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz, process

from pipeline.audit import fmt_years  # noqa: F401  (re-exported for the engines: [2017, 2018] -> '2017-2018')

ROOT = Path(__file__).resolve().parents[1]
MASTER_PATH = ROOT / "data" / "processed" / "nirf_master.parquet"

YEARS = list(range(2017, 2026))
LATEST_YEAR = YEARS[-1]

# The five NIRF parameters, and the three that replace TLR/RPC/GO for Research Institutions.
PARAMETERS = ["tlr", "rpc", "go", "oi", "pr"]
RESEARCH_PARAMETERS = ["qnr", "qlr", "sfc", "oi", "pr"]
LABELS = {
    "score": "Overall score",
    "tlr": "TLR (Teaching, Learning & Resources)",
    "rpc": "RPC (Research & Professional Practice)",
    "go": "GO (Graduation Outcomes)",
    "oi": "OI (Outreach & Inclusivity)",
    "pr": "PR (Perception)",
    "qnr": "QnR (Quantitative Research)",
    "qlr": "QlR (Qualitative Research)",
    "sfc": "SFC (Student, Faculty & Collaboration)",
    "rank": "Rank",
}
SHORT = {"score": "Overall score", "tlr": "TLR", "rpc": "RPC", "go": "GO", "oi": "OI", "pr": "PR",
         "qnr": "QnR", "qlr": "QlR", "sfc": "SFC", "rank": "Rank"}
NUMERIC_COLUMNS = list(LABELS)

# Standard rank bands in order (from the pipeline), plus NIRF's own 11-50 band used by Innovation/SDG.
BAND_ORDER = ["1-10", "11-25", "11-50", "26-50", "51-100", "101-150", "151-200", "201-300"]

# Common short forms people type for institutions -> the words NIRF uses.
ABBREVIATIONS = {
    "iit": "indian institute of technology",
    "iits": "indian institute of technology",
    "nit": "national institute of technology",
    "iim": "indian institute of management",
    "iisc": "indian institute of science",
    "iiser": "indian institute of science education and research",
    "iiit": "indian institute of information technology",
    "aiims": "all india institute of medical sciences",
    "bhu": "banaras hindu university",
    "jnu": "jawaharlal nehru university",
    "amu": "aligarh muslim university",
    "jmi": "jamia millia islamia",
    "bits": "birla institute of technology and science",
    "vit": "vellore institute of technology",
    "dtu": "delhi technological university",
    "nlsiu": "national law school of india university",
    "univ": "university",
    "bangalore": "bengaluru",
    "govt": "government",
}


class NirfInputError(ValueError):
    """A user input the data cannot answer (unknown name, year outside a category's range ...).

    The message is written for the person using the dashboard, so the app can show it as is.
    """


# ---------- loading ----------

@lru_cache(maxsize=1)
def _master() -> pd.DataFrame:
    if not MASTER_PATH.exists():
        raise FileNotFoundError(f"{MASTER_PATH} not found: run `python -m pipeline.clean` first.")
    df = pd.read_parquet(MASTER_PATH)
    band_high = pd.to_numeric(df["rank_band_nirf"].str.extract(r"-(\d+)$")[0], errors="coerce")
    df["rank_upper"] = df["rank"].astype("Float64").fillna(band_high.astype("Float64"))
    return df


# The states the current analysis is limited to (None = every state); set only through only_states().
_STATE_SCOPE: ContextVar[tuple[str, ...] | None] = ContextVar("state_scope", default=None)


def load_master() -> pd.DataFrame:
    """The cleaned master table (one row per year x category x institution), plus `rank_upper`.

    Read once and cached; every call returns a copy so an engine can never change the shared table.
    Inside only_states(...), only the rows of institutions in those states are returned.
    """
    df = _master()
    scope = _STATE_SCOPE.get()
    if scope:
        df = df[df["state"].isin(scope)]
    return df.copy()


def current_states() -> tuple[str, ...] | None:
    """The states the running analysis is limited to, or None for all of India."""
    return _STATE_SCOPE.get()


@contextmanager
def only_states(states) -> Iterator[tuple[str, ...] | None]:
    """Limit every load_master() inside this block to institutions located in `states`.

    states=None or empty means no limit. Names are checked (and spelling variants mapped) first.
    The limit is per thread of execution (a ContextVar), so two dashboard users never affect each other.
    """
    scope = tuple(check_states(states)) if states else None
    token = _STATE_SCOPE.set(scope)
    try:
        yield scope
    finally:
        _STATE_SCOPE.reset(token)


# ---------- input checks ----------

def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, (str, int)):
        return [value]
    return list(value)


def check_category(category: str, df: pd.DataFrame | None = None) -> str:
    """Return the standard category name for `category` (case and '&'/'and' do not matter)."""
    df = _master() if df is None else df
    known = sorted(df["category_std"].unique())
    if category is None:
        raise NirfInputError(f"Please choose a category: {', '.join(known)}.")
    key = _norm(str(category))
    lookup = {_norm(c): c for c in known}
    lookup.update({_norm(c): s for c, s in zip(df["category_original"], df["category_std"])})
    if key in lookup:
        return lookup[key]
    starts = [c for k, c in lookup.items() if k.startswith(key)]
    if len(set(starts)) == 1:
        return starts[0]
    raise NirfInputError(f"'{category}' is not a NIRF category. Choose one of: {', '.join(known)}.")


def category_years(category: str, df: pd.DataFrame | None = None) -> list[int]:
    """The years in which NIRF published a ranking for this (standard) category."""
    df = _master() if df is None else df
    return sorted(df.loc[df["category_std"].eq(category), "year"].unique().tolist())


def check_year(year, category: str, df: pd.DataFrame | None = None) -> int:
    """Return `year` as an int, or explain which years the category exists in."""
    available = category_years(category, df)
    try:
        y = int(year)
    except (TypeError, ValueError):
        raise NirfInputError(f"'{year}' is not a year. {category} rankings exist for {fmt_years(available)}.")
    if y not in available:
        raise NirfInputError(f"NIRF has no {category} ranking for {y}. "
                             f"{category} rankings exist for {fmt_years(available)}.")
    return y


def check_years(years, category: str, df: pd.DataFrame | None = None) -> list[int]:
    """None -> every year of the category; otherwise keep the requested years and check each one."""
    available = category_years(category, df)
    if years is None:
        return available
    ys = sorted({check_year(y, category, df) for y in _as_list(years)})
    if not ys:
        raise NirfInputError(f"Please choose at least one year ({category}: {fmt_years(available)}).")
    return ys


def category_year(category: str, year=None) -> tuple[pd.DataFrame, str, int]:
    """Rows of one category-year, plus the checked category name and year.

    year=None means the latest year in which NIRF ranked the category.
    """
    df = _master()
    category = check_category(category, df)
    year = check_year(category_years(category, df)[-1] if year is None else year, category, df)
    return filter_df(load_master(), categories=category, years=year), category, year


def check_states(states, df: pd.DataFrame | None = None) -> list[str]:
    """Return official state names for the given spellings (case-insensitive, 'TN'-style not guessed)."""
    df = _master() if df is None else df
    known = sorted(df["state"].unique())
    lookup = {_norm(s): s for s in known}
    lookup.update({_norm(o): s for o, s in zip(df["state_original"], df["state"])})
    out = []
    for s in _as_list(states):
        k = _norm(str(s))
        if k in lookup:
            out.append(lookup[k])
            continue
        best = process.extractOne(k, list(lookup), scorer=fuzz.WRatio, score_cutoff=90)
        if best:
            out.append(lookup[best[0]])
            continue
        raise NirfInputError(f"'{s}' is not a state or union territory in the NIRF data. "
                             f"Known states: {', '.join(known)}.")
    return list(dict.fromkeys(out))


def check_column(column: str, category: str, df: pd.DataFrame) -> str:
    """Return the column name for a score/parameter, or explain why it cannot be used here."""
    col = _norm(str(column)).replace(" ", "")
    aliases = {"overall": "score", "overallscore": "score", "teaching": "tlr", "research": "rpc",
               "graduation": "go", "outcomes": "go", "outreach": "oi", "inclusivity": "oi",
               "perception": "pr"}
    col = aliases.get(col, col)
    if col not in NUMERIC_COLUMNS:
        raise NirfInputError(f"'{column}' is not a NIRF number. Choose one of: "
                             f"{', '.join(SHORT[c] for c in NUMERIC_COLUMNS)}.")
    if df[col].notna().sum() == 0:
        have = [SHORT[c] for c in NUMERIC_COLUMNS if df[c].notna().any()]
        raise NirfInputError(f"NIRF did not publish {SHORT[col]} for {category} in this selection. "
                             f"Available here: {', '.join(have) if have else 'none'}.")
    return col


def parameters_of(df: pd.DataFrame) -> list[str]:
    """The parameter columns that have values in `df` (TLR..PR, or QnR/QlR/SFC/OI/PR for Research)."""
    order = PARAMETERS[:3] + RESEARCH_PARAMETERS          # NIRF's order: TLR RPC GO / QnR QlR SFC, then OI PR
    return [p for p in dict.fromkeys(order) if df[p].notna().any()]


# ---------- institution names ----------

def _norm(text: str) -> str:
    """Lower case, '&' -> 'and', punctuation removed, single spaces."""
    t = str(text).lower().replace("&", " and ")
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return " ".join(t.split())


def _expand(text: str) -> str:
    return " ".join(ABBREVIATIONS.get(w, w) for w in _norm(text).split())


@lru_cache(maxsize=1)
def _name_index() -> pd.DataFrame:
    """Every spelling (canonical, published, raw) of every institution -> its key."""
    df = _master()
    rows = pd.concat([df[["institution_key", c]].set_axis(["institution_key", "name"], axis=1)
                      for c in ("canonical_name", "institute_name", "institute_name_raw")])
    rows = rows.dropna().drop_duplicates()
    rows["norm"] = rows["name"].map(_expand)
    return rows.drop_duplicates(["institution_key", "norm"]).reset_index(drop=True)


def institution_names(keys: Iterable[str]) -> dict[str, str]:
    """institution_key -> canonical (most recent) name."""
    df = _master()
    names = df.drop_duplicates("institution_key").set_index("institution_key")["canonical_name"]
    return {k: names[k] for k in keys}


_SHORT_FORMS = [
    (r"^Indian Institute of Technology\s*\(?Banaras Hindu University\)?\s*", "IIT (BHU) "),
    (r"^Indian Institute of Technology\b", "IIT"),
    (r"^Indian Institute of Management\b", "IIM"),
    (r"^Indian Institute of Science Education (?:&|and) Research\b", "IISER"),
    (r"^Indian Institute of Information Technology\b", "IIIT"),
    (r"^National Institute of Technology\b", "NIT"),
    (r"^All India Institute of Medical Sciences\b", "AIIMS"),
    (r"\s*\((?:Deemed[- ]to[- ]be[- ]University)\)", ""),
]


def short_name(name: str, max_len: int = 48) -> str:
    """A shorter label for charts: 'Indian Institute of Technology Madras' -> 'IIT Madras'.

    Only well-known prefixes are shortened; the full name stays in hover text and tables.
    """
    s = str(name)
    for pattern, repl in _SHORT_FORMS:
        s = re.sub(pattern, repl, s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip(" ,-")
    return s if len(s) <= max_len else s[: max_len - 1].rstrip() + "…"


def chart_labels(keys: Iterable[str]) -> dict[str, str]:
    """institution_key -> short chart label, unique within this set (adds the city on a clash).

    Unique labels matter: two bars with the same label would be drawn as one.
    """
    df = _master().drop_duplicates("institution_key").set_index("institution_key")
    keys = list(dict.fromkeys(keys))
    labels = {k: short_name(df.at[k, "canonical_name"]) for k in keys}
    counts = pd.Series(labels).value_counts()
    for k, lab in labels.items():
        if counts[lab] > 1:
            labels[k] = f"{lab} ({df.at[k, 'city'] or df.at[k, 'state']})"
    counts = pd.Series(labels).value_counts()
    for k, lab in labels.items():
        if counts[lab] > 1:
            labels[k] = f"{lab} [{k}]"
    return labels


def _describe(keys: Iterable[str]) -> str:
    df = _master().drop_duplicates("institution_key").set_index("institution_key")
    return "; ".join(f"{df.at[k, 'canonical_name']} ({df.at[k, 'city']}, {df.at[k, 'state']})" for k in keys)


def find_institution(name: str) -> str:
    """Turn what a person typed ('IIT Madras', 'iisc', a full name or an INST- key) into one key.

    Steps, stopping at the first that gives exactly one institution:
      1. an institution_key typed directly;
      2. the same name after normalising (case, '&', punctuation) and expanding short forms
         (IIT -> Indian Institute of Technology ...), against every spelling NIRF ever used;
      3. every typed word appears in the name ('IIT Madras' -> Indian Institute of Technology Madras);
      4. close spelling (rapidfuzz WRatio >= 90, clearly ahead of the next candidate).
    If several institutions fit, the message lists them so the person can be more specific.
    """
    idx = _name_index()
    text = str(name).strip()
    if text.upper() in set(idx["institution_key"]):
        return text.upper()
    q = _expand(text)
    if not q:
        raise NirfInputError("Please type an institution name.")

    exact = idx.loc[idx["norm"].eq(q), "institution_key"].unique()
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise NirfInputError(f"'{name}' matches {len(exact)} institutions: {_describe(exact[:6])}. "
                             f"Please add the city.")

    words = set(q.split())
    contains = idx.loc[idx["norm"].map(lambda n: words <= set(n.split())), "institution_key"].unique()
    if len(contains) == 1:
        return contains[0]
    if len(contains) > 1:
        raise NirfInputError(f"'{name}' fits {len(contains)} institutions, e.g. {_describe(contains[:6])}. "
                             f"Please be more specific.")

    hits = process.extract(q, idx["norm"].tolist(), scorer=fuzz.WRatio, limit=10)
    seen: dict[str, float] = {}
    for _, score, i in hits:
        seen.setdefault(idx.at[i, "institution_key"], score)
    ranked = sorted(seen.items(), key=lambda kv: -kv[1])
    if ranked and ranked[0][1] >= 90 and (len(ranked) == 1 or ranked[0][1] - ranked[1][1] >= 3):
        return ranked[0][0]
    suggestions = _describe([k for k, _ in ranked[:5]]) if ranked else "none"
    raise NirfInputError(f"No institution called '{name}' in the NIRF data. Did you mean: {suggestions}?")


def find_institutions(names) -> list[str]:
    """find_institution() for each name; keeps the order given and drops repeats."""
    return list(dict.fromkeys(find_institution(n) for n in _as_list(names)))


# ---------- filtering ----------

def filter_df(df: pd.DataFrame, years=None, categories=None, states=None, institutions=None,
              rank_max: int | None = None, exact_ranks_only: bool = False) -> pd.DataFrame:
    """Keep only the rows that match every filter given (None = no filter on that column).

    years: one year or a list. categories: names in any case ('engineering', 'Research').
    states: official names or published spellings. institutions: names, short forms or keys.
    rank_max: keep rows certainly within the top `rank_max` (exact rank <= rank_max, or a NIRF band
      whose worst rank <= rank_max; a 101-150 row is never counted in the top 100).
    exact_ranks_only: drop rows that have only a rank band (or a withdrawn rank), for calculations
      that need the rank as a number.
    """
    out = df
    if years is not None:
        out = out[out["year"].isin([int(y) for y in _as_list(years)])]
    if categories is not None:
        out = out[out["category_std"].isin([check_category(c, df) for c in _as_list(categories)])]
    if states is not None:
        out = out[out["state"].isin(check_states(states, df))]
    if institutions is not None:
        out = out[out["institution_key"].isin(find_institutions(institutions))]
    if rank_max is not None:
        upper = out["rank_upper"] if "rank_upper" in out else out["rank"].astype("Float64")
        out = out[upper.le(rank_max).fillna(False).astype(bool)]
    if exact_ranks_only:
        out = out[out["rank"].notna()]
    return out.copy()
