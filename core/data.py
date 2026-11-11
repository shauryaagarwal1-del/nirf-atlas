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
Institute-type scope works the same way: inside `with only_types(["IIT"]):` only IITs are returned
("Which IITs improved the most?"). The type comes from the cleaned name (institute_types()).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz, process

from pipeline.audit import fmt_years  # noqa: F401  (re-exported for the engines: [2017, 2018] -> '2017-2018')

ROOT = Path(__file__).resolve().parents[1]
MASTER_PATH = ROOT / "data" / "processed" / "nirf_master.parquet"
# Every institution that took part in a NIRF category-year, ranked or not (institution_key empty = not ranked).
PARTICIPANTS_PATH = ROOT / "data" / "processed" / "nirf_participants.parquet"

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
# Plain words first, NIRF's code in brackets: what a chart prints on an axis, a legend or a label.
PLAIN = {
    "score": "Overall score",
    "tlr": "Teaching score (TLR)",
    "rpc": "Research score (RPC)",
    "go": "Graduation score (GO)",
    "oi": "Outreach & inclusivity score (OI)",
    "pr": "Perception score (PR)",
    "qnr": "Research quantity score (QnR)",
    "qlr": "Research quality score (QlR)",
    "sfc": "Students, faculty & collaboration score (SFC)",
    "rank": "Rank",
}
# One word for tight spots (a bar label, a title): "Teaching", "Research" ...
WORD = {"score": "Overall", "tlr": "Teaching", "rpc": "Research", "go": "Graduation", "oi": "Outreach",
        "pr": "Perception", "qnr": "Research quantity", "qlr": "Research quality", "sfc": "Students & faculty",
        "rank": "Rank"}
NUMERIC_COLUMNS = list(LABELS)

# Standard rank bands in order (from the pipeline), plus NIRF's own 11-50 band used by Innovation/SDG.
BAND_ORDER = ["1-10", "11-25", "11-50", "26-50", "51-100", "101-150", "151-200", "201-300"]

# India's 28 states and 8 union territories (official names). Two have no NIRF-ranked institution
# (Ladakh, Lakshadweep): typing one gets "No institution from Ladakh appears ..." instead of "not a state".
INDIA_STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat", "Haryana",
    "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
    "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
    "Uttar Pradesh", "Uttarakhand", "West Bengal", "Andaman and Nicobar Islands", "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
]

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
    "iiest": "indian institute of engineering science and technology",
    "nlu": "national law university",
    "niper": "national institute of pharmaceutical education and research",
    "univ": "university",
    "govt": "government",
}
# One spelling per place, applied to names, cities and what people type alike ('IIT Mumbai' = 'IIT Bombay').
# The old names are kept because the famous institutes carry them (IIT Bombay, IIT Madras, IIM Calcutta).
# 'bengluru' is how NIRF itself spelled IIIT Bangalore's city.
PLACE_SYNONYMS = {
    "bengaluru": "bangalore", "bengluru": "bangalore", "mumbai": "bombay", "chennai": "madras",
    "kolkata": "calcutta", "trichy": "tiruchirappalli", "gurugram": "gurgaon", "prayagraj": "allahabad",
    "kozhikode": "calicut", "pondicherry": "puducherry", "orissa": "odisha",
}

# Institute families, checked in this order on the normalised name (IIIT before IIT, IISER before IISc).
# IIIT covers the Indian, International and Indraprastha Institutes of Information Technology and IIITDM.
FAMILIES = [
    ("IIIT", r"\b(?:indian|international|indraprastha) institute of information technology\b|\biiit\w*"),
    ("IIEST", r"\bindian institute of engineering science and technology\b"),
    ("IISER", r"\bindian institute of science education and research\b|\biiser\b"),
    ("IISc", r"\bindian institute of science\b(?! education)|\biisc\b"),
    ("IIT", r"\bindian institute of technology\b"),
    ("NIT", r"\bnational institute of technology\b"),
    ("IIM", r"\bindian institute of management\b(?! and commerce)"),
    ("AIIMS", r"\ball india institute of medical sciences\b"),
    ("NIPER", r"\bnational institute of pharmaceutical education and research\b|\bniper\b"),
    ("NLU", r"\bnational law\b|\bnational university of (?:law|juridical|advanced legal|study and research in law)\b"
            r"|\bnalsar\b|\bnujs\b|\bnuals\b"),
]
# "IIT Bangalore" does not exist: try these families in the same city (or state), in this order.
FAMILY_SWAPS = {"IIT": ["IIIT", "NIT", "IIEST", "IISc", "IISER", "IIM"], "NIT": ["IIIT", "IIT"],
                "IIIT": ["IIT", "NIT"], "IIM": ["IIT", "IIIT"]}
_FILLER = {"of", "the", "and", "at", "in"}


class NirfInputError(ValueError):
    """A user input the data cannot answer (unknown name, year outside a category's range ...).

    The message is written for the person using the dashboard, so the app can show it as is.
    """


class NotRankedError(NirfInputError):
    """The institution took part in NIRF but never appeared in a published ranked list.

    Not a mistake by the person asking: the message says when and where it took part, and `similar`
    holds up to two ranked institutions from the same state and category to look at instead.
    """

    def __init__(self, message: str, similar: list[str]):
        super().__init__(message)
        self.similar = similar


class AmbiguousInstitutionError(NirfInputError):
    """What was typed fits several ranked institutions ('NIT', 'Christian Medical College': two campuses).

    `options` holds up to 4 of them, best known first (best recent rank), so the app can offer them as
    buttons instead of guessing.
    """

    def __init__(self, message: str, options: list[str], total: int):
        super().__init__(message)
        self.options, self.total = options, total


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
# The institute types it is limited to (None = every institution); set only through only_types().
_TYPE_SCOPE: ContextVar[tuple[str, ...] | None] = ContextVar("type_scope", default=None)


def load_master() -> pd.DataFrame:
    """The cleaned master table (one row per year x category x institution), plus `rank_upper`.

    Read once and cached; every call returns a copy so an engine can never change the shared table.
    Inside only_states(...), only the rows of institutions in those states are returned.
    """
    df = _master()
    scope = _STATE_SCOPE.get()
    if scope:
        df = df[df["state"].isin(scope)]
    types = _TYPE_SCOPE.get()
    if types:
        df = df[df["institution_key"].map(institute_types()).isin(types)]
    return df.copy()


def current_states() -> tuple[str, ...] | None:
    """The states the running analysis is limited to, or None for all of India."""
    return _STATE_SCOPE.get()


def current_types() -> tuple[str, ...] | None:
    """The institute types the running analysis is limited to, or None for every institution."""
    return _TYPE_SCOPE.get()


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


@contextmanager
def only_types(types) -> Iterator[tuple[str, ...] | None]:
    """Limit every load_master() inside this block to institutes of these types ('IIT', 'NIT' ...).

    types=None or empty means no limit. Words such as 'IITs' or 'all IIMs' are accepted (check_types).
    """
    scope = tuple(check_types(types)) if types else None
    token = _TYPE_SCOPE.set(scope)
    try:
        yield scope
    finally:
        _TYPE_SCOPE.reset(token)


# ---------- institute types ----------

# The institute types the type filter offers, with what each covers. Each is found from the cleaned name with
# the FAMILIES patterns ('Indian Institute of Technology ...' = IIT). Central / state universities are not
# offered: NIRF does not publish that status and it cannot be read reliably from a name.
INSTITUTE_TYPES = {
    "IIT": "Indian Institutes of Technology (incl. IIT (BHU) Varanasi and IIT (ISM) Dhanbad)",
    "NIT": "National Institutes of Technology (incl. VNIT Nagpur, MNIT Jaipur, SVNIT Surat ...)",
    "IIIT": "Institutes of Information Technology (Indian, International and Indraprastha IIITs, IIITDM)",
    "IIM": "Indian Institutes of Management",
    "IISER": "Indian Institutes of Science Education and Research",
    "AIIMS": "All India Institutes of Medical Sciences",
    "NLU": "National law universities and law schools (NLSIU, NALSAR, NUJS, NLU Delhi ...)",
    "NIPER": "National Institutes of Pharmaceutical Education and Research",
}


@lru_cache(maxsize=1)
def institute_types() -> pd.Series:
    """institution_key -> its institute type (IIT, NIT, IIIT, IIM, IISER, AIIMS, NLU, NIPER) or None.

    Read from the canonical (most recent) name with the same family patterns the name search uses, e.g.
    'Indian Institute of Technology (Indian School of Mines)' -> IIT, 'Visvesvaraya National Institute of
    Technology, Nagpur' -> NIT, 'Indian Institute of Management and Commerce' -> none.
    """
    names = _master().drop_duplicates("institution_key").set_index("institution_key")["canonical_name"]
    fam = names.map(lambda n: family_of(_expand(n))[0])
    return fam.where(fam.isin(list(INSTITUTE_TYPES)))


def institute_type_code(text) -> str | None:
    """'IITs', 'all IIMs', 'the NITs', 'Indian Institutes of Technology', 'iiser' -> the type code, else None."""
    t = _norm(str(text))
    t = re.sub(r"^(?:all|the|every|only|all the)\s+", "", t)
    t = re.sub(r"\s+(?:only|institutes|campuses)$", "", t)
    codes = {c.lower(): c for c in INSTITUTE_TYPES}
    if t in codes:
        return codes[t]
    if t.endswith("s") and t[:-1] in codes:
        return codes[t[:-1]]
    t = re.sub(r"\binstitutes\b", "institute", t)
    t = re.sub(r"\buniversities\b", "university", t)
    family, rest = family_of(_expand(t))
    return family if family in INSTITUTE_TYPES and not rest else None


def check_types(types) -> list[str]:
    """Type codes for what was typed ('IITs' -> 'IIT'); a NirfInputError lists the types on offer."""
    out = []
    for t in _as_list(types):
        code = institute_type_code(t)
        if code is None:
            raise NirfInputError(f"'{t}' is not an institute type we can filter by. Choose from: "
                                 f"{', '.join(INSTITUTE_TYPES)}.")
        out.append(code)
    return list(dict.fromkeys(out))


def type_plural(code: str) -> str:
    """'IIT' -> 'IITs'; 'AIIMS' stays 'AIIMS'."""
    return code if code.endswith("S") else code + "s"


def scope_phrase(states=None, types=None, singular: bool = False) -> str:
    """Who an analysis covers: 'institutions in Kerala', 'IITs', 'IITs in Kerala' (singular: 'IIT in Kerala')."""
    def join(items):
        items = list(items)
        return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
    who = (join(types if singular else [type_plural(t) for t in types]) if types
           else ("institution" if singular else "institutions"))
    if singular and types and len(types) > 1:
        who = "institute of type " + join(types)
    return who + (f" in {join(states)}" if states else "")


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


def n_years(n: int) -> str:
    """'1 year', '3 years'."""
    return f"{n} year{'' if n == 1 else 's'}"


def change_years(category: str, df: pd.DataFrame | None = None) -> list[int]:
    """category_years() for an analysis of change over time (movers, transitions, volatility ...).

    A category NIRF ranked in only one year (SDG: 2025) has no change to show; this says so in one
    clear sentence instead of "the start year (2025) must be before the end year (2025)". Checked on
    the whole table, so a state filter never changes the reason.
    """
    national = category_years(category)
    if len(national) == 1:
        raise NirfInputError(f"{category} was ranked only in {national[0]}, so there is no change over time to show.")
    return category_years(category, df)


def list_sizes(category: str, years) -> pd.Series:
    """year -> the number of places in NIRF's national list of that category-year (the worst certain rank:
    200 for Overall, 40 for Law 2025), whatever state or institute-type filter is on."""
    df = _master()
    rows = df[df["category_std"].eq(category) & df["year"].isin(list(years))]
    return rows.groupby("year")["rank_upper"].max().dropna()


def check_year(year, category: str, df: pd.DataFrame | None = None) -> int:
    """Return `year` as an int, or explain which years the category exists in."""
    available = category_years(category, df)
    try:
        y = int(year)
    except (TypeError, ValueError):
        raise NirfInputError(f"'{year}' is not a year. {category} rankings exist for {fmt_years(available)}.")
    if y not in available:
        scope, types = _STATE_SCOPE.get(), _TYPE_SCOPE.get()
        if (scope or types) and y in category_years(category, _master()):
            # NIRF did publish this year; only the chosen states / institute types have no institution in it.
            seen = (f"they appear in {fmt_years(available)}" if available else "none appears in any year")
            raise NirfInputError(f"No {scope_phrase(scope, types, singular=True)} is in the {category} ranking of "
                                 f"{y} ({seen}).")
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
        # A one-letter slip ('Telengana'): plain similarity >= 87 and clearly ahead of the next state
        # (the closest two real states, Andhra / Madhya Pradesh, are 86 apart, so they never mix).
        close = process.extract(k, list(lookup), scorer=fuzz.ratio, score_cutoff=87, limit=5)
        firsts = list(dict.fromkeys(lookup[c] for c, _, _ in close))
        if close and (len(firsts) == 1 or close[0][1] - max(sc for c, sc, _ in close if lookup[c] != firsts[0]) >= 5):
            out.append(firsts[0])
            continue
        real = next((r for r in INDIA_STATES if _norm(r) == k), None)
        if real:                                  # a real state or UT that simply has no ranked institution
            raise NirfInputError(f"No institution from {real} appears in any NIRF ranking.")
        raise NirfInputError(f"'{s}' is not a state or union territory in the NIRF data. "
                             f"Known states: {', '.join(known)}.")
    return list(dict.fromkeys(out))


def region_states(region: str) -> list[str]:
    """The states of one region of the cleaned data ('South' -> Andhra Pradesh, Karnataka, Kerala ...)."""
    df = _master()
    return sorted(df.loc[df["region"].eq(region), "state"].unique())


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
    """_norm(), then short forms written out (IIT -> indian institute of technology) and one spelling per place."""
    return " ".join(ABBREVIATIONS.get(w) or PLACE_SYNONYMS.get(w, w) for w in _norm(text).split())


def family_of(norm: str) -> tuple[str | None, str]:
    """(institute family or None, the words left once the family phrase is taken out) of a normalised name.

    'indian institute of technology madras' -> ('IIT', 'madras'); 'bangalore institute of technology'
    -> (None, the whole name). Filler words (of, the, and) are dropped from what is left.
    """
    for code, pattern in FAMILIES:
        m = re.search(pattern, norm)
        if m:
            rest = (norm[:m.start()] + " " + norm[m.end():]).split()
            return code, " ".join(w for w in rest if w not in _FILLER)
    return None, norm


def _words(text) -> frozenset[str]:
    return frozenset(_expand(text).split()) if isinstance(text, str) else frozenset()


def _index(names: pd.DataFrame, places: pd.DataFrame) -> pd.DataFrame:
    """One row per (institution_key, normalised spelling) with its family, name words, city and state words.

    names: columns institution_key, name. places: institution_key -> city, state.
    """
    rows = names.dropna().drop_duplicates().copy()
    rows["norm"] = rows["name"].map(_expand)
    rows = rows[rows["norm"].ne("")].drop_duplicates(["institution_key", "norm"]).reset_index(drop=True)
    fam = [family_of(n) for n in rows["norm"]]
    rows["family"] = [f for f, _ in fam]
    rows["rest"] = [r for _, r in fam]
    rows["words"] = rows["norm"].str.split().map(frozenset)
    rows["rest_words"] = rows["rest"].str.split().map(frozenset)
    rows["city"] = rows["institution_key"].map(places["city"].map(_words))
    rows["state"] = rows["institution_key"].map(places["state"].map(_words))
    rows["place"] = [c | s for c, s in zip(rows["city"], rows["state"])]
    # For the spelling step: the name (or the part after the family) plus any city word it lacks, so
    # 'Christian Medical Colege Vellore' is compared with 'christian medical college vellore'.
    rows["norm_city"] = [" ".join([n, *sorted(c - w)]) for n, c, w in zip(rows["norm"], rows["city"], rows["words"])]
    rows["rest_city"] = [" ".join([r, *sorted(c - w)]).strip()
                         for r, c, w in zip(rows["rest"], rows["city"], rows["words"])]
    return rows


@lru_cache(maxsize=1)
def _name_index() -> pd.DataFrame:
    """Every spelling (canonical, published, raw) of every ranked institution -> its key."""
    df = _master()
    rows = pd.concat([df[["institution_key", c]].set_axis(["institution_key", "name"], axis=1)
                      for c in ("canonical_name", "institute_name", "institute_name_raw")])
    return _index(rows, df.drop_duplicates("institution_key").set_index("institution_key")[["city", "state"]])


@lru_cache(maxsize=1)
def _participants() -> pd.DataFrame:
    """Rows of institutions that took part in NIRF but were never ranked, keyed 'P:<name without spaces>'.

    The key ignores spaces so that 'B.B.A. College' and 'B. B. A College' are one institution.
    """
    cols = ["institution_key", "institute_name", "city", "state", "year", "category_std"]
    if not PARTICIPANTS_PATH.exists():
        return pd.DataFrame(columns=cols)
    p = pd.read_parquet(PARTICIPANTS_PATH, columns=cols)
    p = p[p["institution_key"].isna() & p["institute_name"].notna()].copy()
    p["institution_key"] = "P:" + p["institute_name"].map(_expand).str.replace(" ", "", regex=False)
    return p


@lru_cache(maxsize=1)
def _participant_index() -> pd.DataFrame:
    """The never-ranked participants, indexed like _name_index() (spellings of ranked institutions left out)."""
    p = _participants()
    latest = p.sort_values("year").drop_duplicates("institution_key", keep="last").set_index("institution_key")
    idx = _index(p[["institution_key", "institute_name"]].set_axis(["institution_key", "name"], axis=1),
                 latest[["city", "state"]])
    return idx[~idx["norm"].isin(set(_name_index()["norm"]))].reset_index(drop=True)


@lru_cache(maxsize=1)
def _place_words() -> frozenset[str]:
    """Words that name a place: every state word, plus city words that are not common in institution names.

    City fields also hold words such as 'college' or 'gandhi'; a word used in 10+ institution names is
    not treated as a place.
    """
    df, p = _master(), _participants()
    in_names = pd.Series([w for ws in _name_index().drop_duplicates("institution_key")["words"] for w in ws])
    common = set(in_names.value_counts().loc[lambda c: c >= 10].index)
    states = {w for s in pd.concat([df["state"], p["state"]]).dropna().unique() for w in _words(s)
              if w.isalpha() and len(w) >= 3 and w not in _FILLER}
    cities = {w for c in pd.concat([df["city"], p["city"]]).dropna().unique() for w in _words(c)
              if w.isalpha() and len(w) >= 4 and w not in common}
    return frozenset(states | cities | set(PLACE_SYNONYMS.values()))


def _places_in(words: Iterable[str]) -> dict[str, frozenset[str]]:
    """The place words of a query, as {typed word: the spellings it may stand for}.

    A word of 5+ letters also stands for the places spelt almost the same (rapidfuzz ratio >= 88), so a
    typo such as 'banglore' or 'hyderbad' still counts as Bangalore or Hyderabad (city fields contain
    typos too, so a typed word can be a known 'place' and still be a misspelling).
    """
    places = _place_words()
    out = {}
    for w in words:
        same = {w} if w in places else set()
        if len(w) >= 5 and w.isalpha():
            same |= {hit for hit, _, _ in process.extract(w, places, scorer=fuzz.ratio, score_cutoff=88, limit=5)}
        if same:
            out[w] = frozenset(same)
    return out


def _in_place(places: dict[str, frozenset[str]], where: frozenset[str]) -> bool:
    """True if every typed place word (in one of its spellings) is in `where`."""
    return all(spellings & where for spellings in places.values())


def institution_names(keys: Iterable[str]) -> dict[str, str]:
    """institution_key -> canonical (most recent) name."""
    df = _master()
    names = df.drop_duplicates("institution_key").set_index("institution_key")["canonical_name"]
    return {k: names[k] for k in keys}


def institution_keys_named(name: str) -> list[str]:
    """Every institution key whose canonical name is `name` (two 'National Law University': Delhi, Cuttack)."""
    df = _master()
    return df.loc[df["canonical_name"].eq(name), "institution_key"].unique().tolist()


def institution_city(key: str) -> str:
    """The city of an institution in its most recent year (its state if no city was published)."""
    rows = _master().loc[lambda d: d["institution_key"].eq(key)].sort_values("year")
    city = rows["city"].dropna().iloc[-1] if rows["city"].notna().any() else ""
    return city or rows["state"].iloc[-1]


_SHORT_FORMS = [
    (r"^Indian Institute of Technology\s*\(?Banaras Hindu University\)?\s*", "IIT (BHU) "),
    (r"^Indian Institute of Technology\b", "IIT"),
    (r"^Indian Institute of Management\b", "IIM"),
    (r"^Indian Institute of Science Education (?:&|and) Research\b", "IISER"),
    (r"^Indian Institute of Information Technology\b", "IIIT"),
    (r"^National Institute of Technology\b", "NIT"),
    (r"^All India Institute of Medical Sciences\b", "AIIMS"),
    (r"^National Institute of Pharmaceutical Education (?:&|and) Research\b", "NIPER"),
    (r"^(IIT|IIM|IISER|IIIT|NIT|AIIMS|NIPER),\s*", r"\1 "),        # 'IISER, Mohali' -> 'IISER Mohali'
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


def short_label(key: str) -> str:
    """The everyday short name of an institution: 'IIM Bangalore', 'IISc', 'IIIT Bangalore'.

    short_name() where it shortens the name; otherwise, for a family institute, the family plus the place
    written after the family phrase (or its city); otherwise the name itself.
    """
    row = _master().drop_duplicates("institution_key").set_index("institution_key").loc[key]
    name = row["canonical_name"]
    short = short_name(name, 60)
    if short != name:
        return short
    norm = _norm(name)
    family, _ = family_of(norm)
    if family in (None, "NLU"):
        return short
    tail = norm[re.search(dict(FAMILIES)[family], norm).end():].split()
    if family == "IISc" and not tail:
        return "IISc"
    if tail and all(PLACE_SYNONYMS.get(w, w) in _place_words() for w in tail):
        return f"{family} {' '.join(tail).title()}"
    return f"{family} {row['city']}" if isinstance(row["city"], str) and row["city"] else short


CHART_LABEL_LEN = 36   # longest institution label on a chart axis (fits a 1366 px projector next to the bars)


def chart_labels(keys: Iterable[str]) -> dict[str, str]:
    """institution_key -> short chart label, unique within this set (adds the city on a clash).

    Unique labels matter: two bars with the same label would be drawn as one. A label cut to
    CHART_LABEL_LEN characters is remembered with its full name, so the chart's hover shows the full name.
    """
    from core.theme import FULL_NAMES

    df = _master().drop_duplicates("institution_key").set_index("institution_key")
    keys = list(dict.fromkeys(keys))
    labels = {k: short_name(df.at[k, "canonical_name"], CHART_LABEL_LEN) for k in keys}
    counts = pd.Series(labels).value_counts()
    for k, lab in labels.items():
        if counts[lab] > 1:
            labels[k] = f"{lab} ({df.at[k, 'city'] or df.at[k, 'state']})"
    counts = pd.Series(labels).value_counts()
    for k, lab in labels.items():
        if counts[lab] > 1:
            labels[k] = f"{lab} [{k}]"
    for k, lab in labels.items():
        if "…" in lab:
            FULL_NAMES[lab] = df.at[k, "canonical_name"]
    return labels


def _describe(keys: Iterable[str]) -> str:
    df = _master().drop_duplicates("institution_key").set_index("institution_key")
    return "; ".join(f"{df.at[k, 'canonical_name']} ({df.at[k, 'city']}, {df.at[k, 'state']})" for k in keys)


@dataclass
class InstitutionMatch:
    """What match_institution() found: the key, the step that found it and, for a swap, the other options."""
    key: str
    how: str                                   # key | exact | words | spelling | swap
    alternatives: list[str] = field(default_factory=list)


def _where(df: pd.DataFrame, mask: list[bool]) -> pd.DataFrame:
    """Rows of df where mask is True (safe for an empty df, unlike df[[...]])."""
    return df[pd.Series(mask, index=df.index, dtype=bool)]


def _search(idx: pd.DataFrame, q: str, family: str | None, rest: str,
            places: dict[str, frozenset[str]]) -> tuple[str | None, str, list[str]]:
    """Steps 2-4 of match_institution() on one index: exact name, word match, spelling.

    Returns (key, step, []) when exactly one institution fits; otherwise (None, 'ambiguous-exact' or
    'ambiguous', the keys that fit) or (None, 'none', the closest spellings that pass both guards).
    """
    # Family guard: 'IIIT Bangalore' may only match a IIIT, never 'Bangalore Institute of Technology'.
    pool = idx if family is None else idx[idx["family"].eq(family)]
    words = frozenset((rest if family else q).split())
    names = pool["rest_words"] if family else pool["words"]

    exact = pool.loc[pool["norm"].eq(q), "institution_key"].unique()
    if len(exact) == 1:
        return exact[0], "exact", []
    contains = _where(pool, [words <= n for n in names])["institution_key"].unique()
    if len(exact) == 0 and len(contains) == 1:
        return contains[0], "words", []

    # Name + place: 'Christian Medical College Vellore', 'IIT Kerala'. The place words are matched against
    # the city and state, the other words against the name (for a family, the family itself is the name).
    def placed(n, p) -> bool:
        here = words & p
        return bool(here) and (family is not None or bool(words - here)) and (words - here) <= n
    near = _where(pool, [placed(n, p) for n, p in zip(names, pool["place"])])["institution_key"].unique()
    if len(near) == 1:
        return near[0], "words", []
    if len(exact) > 1:
        return None, "ambiguous-exact", list(exact)
    for many in (contains, near):
        if len(many) > 1:
            return None, "ambiguous", list(many)

    # Spelling, last. Place guard: every place word typed must be the candidate's city, state or in its name.
    pool = _where(pool, [_in_place(places, p | w) for p, w in zip(pool["place"], pool["words"])])
    # Each name is scored as written and with its city added; the better score counts.
    query, columns, cutoff = (rest, ("rest", "rest_city"), 80) if family else (q, ("norm", "norm_city"), 90)
    if pool.empty or not query:
        return None, "none", []
    best: dict[str, float] = {}
    for col in columns:
        for _, score, i in process.extract(query, pool[col].tolist(), scorer=fuzz.WRatio, limit=12):
            key = pool["institution_key"].iloc[i]
            best[key] = max(best.get(key, 0), score)
    ranked = sorted(best.items(), key=lambda kv: -kv[1])
    # A very short query (an unknown short form such as 'LPU') is never matched by spelling: it would
    # match any name that merely contains those letters ('lpu' in 'Samba-lpu-r University').
    long_enough = len(query.replace(" ", "")) >= (3 if family else 6)
    if long_enough and ranked[0][1] >= cutoff and (len(ranked) == 1 or ranked[0][1] - ranked[1][1] >= 3):
        return ranked[0][0], "spelling", []
    # Suggestions: WRatio also scores partial matches high ('JU' in 'B. V. Raju College', 'goa' in 'Goa
    # University'), so a suggestion must also be similar as a whole name (token_sort_ratio >= 70) and the
    # query long enough to be a name rather than an unknown short form.
    if not long_enough:
        return None, "none", []
    whole = {k: max(fuzz.token_sort_ratio(query, v) for c in columns
                    for v in pool.loc[pool["institution_key"].eq(k), c]) for k, _ in ranked[:3]}
    return None, "none", [k for k, score in ranked[:3] if score >= 80 and whole[k] >= 70]


def _join(items: list[str]) -> str:
    """['A'] -> 'A'; ['A', 'B', 'C'] -> 'A, B and C'."""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _family_swap(family: str | None, places: dict[str, frozenset[str]]) -> list[str]:
    """For a family that has no institute in the place typed ('IIT Bangalore'): the other families there.

    Institutes in the same city come first; only if there are none, the same state (the state typed, or
    the state that city is in: 'IIT Kochi' -> Kerala). One institute per family, in the order of
    FAMILY_SWAPS (IIT -> IIIT, NIT, IIEST, IISc, IISER, IIM); within a family, the one NIRF ranked in the
    most years.
    """
    if family not in FAMILY_SWAPS or not places:
        return []
    order, idx = FAMILY_SWAPS[family], _name_index()
    pool = idx[idx["family"].isin(order)]
    here = _where(pool, [_in_place(places, c | r) for c, r in zip(pool["city"], pool["rest_words"])])
    if here.empty:
        states = {s for c, s in zip(idx["city"], idx["state"]) if _in_place(places, c)}
        here = _where(pool, [_in_place(places, s) or s in states for s in pool["state"]])
    years = _master().groupby("institution_key")["year"].nunique()
    picks = []
    for fam in order:
        keys = here.loc[here["family"].eq(fam), "institution_key"].unique()
        if len(keys):
            picks.append(max(keys, key=lambda k: (years.get(k, 0), k)))
    return picks


def _similar_ranked(rows: pd.DataFrame, family: str | None, n: int = 2) -> list[str]:
    """Up to n ranked institutions like a never-ranked one: same state, same category (its most frequent one).

    Same family first, then same city, then the most recent year and the best rank in it.
    """
    df = _master()
    category = rows["category_std"].value_counts().index[0]
    state, city = rows["state"].iloc[-1], rows["city"].iloc[-1]
    pool = df[df["state"].eq(state) & df["category_std"].eq(category)]
    if pool.empty:
        pool = df[df["state"].eq(state)]
    latest = pool.sort_values("year").drop_duplicates("institution_key", keep="last")
    fam = _name_index().drop_duplicates("institution_key").set_index("institution_key")["family"]
    latest = latest.assign(same_family=latest["institution_key"].map(fam).eq(family) if family else False,
                           same_city=latest["city"].eq(city), rank_sort=latest["rank_upper"].fillna(10_000))
    latest = latest.sort_values(["same_family", "same_city", "year", "rank_sort"],
                                ascending=[False, False, False, True])
    return latest["institution_key"].head(n).tolist()


def _not_ranked(pkey: str, typed: str, family: str | None) -> NotRankedError:
    """The message for an institution that took part but was never ranked, with similar ranked ones."""
    rows = _participants()
    rows = rows[rows["institution_key"].eq(pkey)].sort_values("year")
    name = rows["institute_name"].iloc[-1]
    counts = rows.groupby("category_std")["year"].nunique()
    categories = sorted(counts.index, key=lambda c: (-counts[c], c))
    who = typed if _norm(typed) == _norm(name) else f"{typed} ({name})"
    message = (f"{who} took part in NIRF ({_join(categories)}, {fmt_years(sorted(rows['year'].unique()))}) but was "
               f"not in the published ranked list in any year, so there is no rank or score to chart.")
    return NotRankedError(message, _similar_ranked(rows, family))


def _best_known(keys, by_main_category: bool = False) -> list[str]:
    """Institution keys, best known first: by Overall rank in the latest year they were ranked (exact rank,
    else the band's worst rank), then by their best rank in any category that year, then by name.

    by_main_category=True (a family such as 'IIM'): the category most of them are ranked in (Management for
    the IIMs) is used instead of Overall, so the options are the family's best known members.
    """
    df = _master()
    rows = df[df["institution_key"].isin(list(keys))]
    latest = rows[rows["year"].eq(rows.groupby("institution_key")["year"].transform("max"))]
    main = "Overall"
    if by_main_category and not rows.empty:
        main = rows.groupby("category_std")["institution_key"].nunique().sort_values(ascending=False).index[0]
    overall = latest[latest["category_std"].eq(main)].groupby("institution_key")["rank_upper"].min()
    anywhere = latest.groupby("institution_key")["rank_upper"].min()
    names = rows.drop_duplicates("institution_key").set_index("institution_key")["canonical_name"]
    return sorted(dict.fromkeys(keys), key=lambda k: (overall.get(k, 10_000) if pd.notna(overall.get(k)) else 10_000,
                                                      anywhere.get(k, 10_000) if pd.notna(anywhere.get(k)) else 10_000,
                                                      names.get(k, k)))


def match_institution(name: str, typed: str | None = None) -> InstitutionMatch:
    """Turn what a person typed into one institution key, and say which rule found it.

    Rules, in order (the first that gives exactly one institution wins):
      1. an institution_key typed directly (INST-00804);
      2. the exact name after normalising (case, '&', punctuation, IIT -> Indian Institute of Technology,
         Bengaluru = Bangalore, Mumbai = Bombay ...), against every spelling NIRF ever used;
      3. word match: every typed word is in the name ('IIT Madras'), or the name words are in the name and
         the rest are its city or state ('Christian Medical College Vellore', 'IIT Kerala');
      4. close spelling, last (rapidfuzz WRatio >= 90 on the whole name, or >= 80 on the part after the
         family, clearly ahead of the next candidate).
    Two guards: a typed family (IIT, IIIT, NIT, IIM, IISER, IISc, AIIMS, NLU, IIEST) only ever matches an
    institute of that family, and in step 4 every place word typed must be the candidate's city or state
    (or be in its name). If nothing fits:
      5. an institution that took part in NIRF but was never ranked -> NotRankedError with a clear message;
      6. a family that has no institute in that place ('IIT Bangalore') -> the other families there
         (how='swap': the first is chosen, the others are `alternatives`);
      7. otherwise NirfInputError with at most 3 suggestions that pass the guards.
    A name that fits several institutions (only a family typed, such as 'NIT', or two campuses with the same
    name, such as 'Christian Medical College') raises AmbiguousInstitutionError with the 4 best known ones.
    The short forms the chat knows ('iitb', 'LPU') are handled before this, in nlq/resolve.py.
    `typed` is the text quoted in messages (default: `name`).
    """
    typed = str(typed or name).strip()
    idx = _name_index()
    text = str(name).strip()
    if text.upper() in set(idx["institution_key"]):
        return InstitutionMatch(text.upper(), "key")
    q = _expand(text)
    if not q:
        raise NirfInputError("Please type an institution name.")
    family, rest = family_of(q)
    places = _places_in((rest if family else q).split())      # the family phrase never names a place

    # Only a family typed ('NIT', 'IIT', 'IISER'), unless it is one institute's full name ('Indraprastha
    # Institute of Information Technology' is IIIT Delhi). The short code itself ('IISER') always asks, even
    # though one IISER was listed in 2017 under the bare family name.
    code_only = _norm(text) in {c.lower() for c, _ in FAMILIES} | {c.lower() + "s" for c, _ in FAMILIES}
    if family and not rest and (code_only or idx.loc[idx["norm"].eq(q), "institution_key"].nunique() != 1):
        members = idx.loc[idx["family"].eq(family), "institution_key"].unique()
        if len(members) > 1:
            found = _best_known(members, by_main_category=True)
            raise AmbiguousInstitutionError(
                f"'{typed}' fits {len(found)} institutions, e.g. {_describe(found[:6])}. Please be more specific, "
                f"e.g. '{short_label(found[0])}'.", found[:4], len(found))
    key, how, found = _search(idx, q, family, rest, places)
    if key:
        return InstitutionMatch(key, how)
    if how == "ambiguous-exact":
        found = _best_known(found)
        city = _master().set_index("institution_key").loc[found[0], "city"].iloc[0]
        raise AmbiguousInstitutionError(f"'{typed}' matches {len(found)} institutions: {_describe(found[:6])}. "
                                        f"Please add the city (e.g. '{text} {city}').", found[:4], len(found))
    if how == "ambiguous":
        found = _best_known(found)
        raise AmbiguousInstitutionError(f"'{typed}' fits {len(found)} institutions, e.g. {_describe(found[:6])}. "
                                        f"Please be more specific.", found[:4], len(found))

    pkey, _, _ = _search(_participant_index(), q, family, rest, places)
    if pkey:
        raise _not_ranked(pkey, typed, family)
    swaps = _family_swap(family, places)
    if swaps:
        return InstitutionMatch(swaps[0], "swap", swaps[1:])
    hint = f" Did you mean: {_describe(found)}?" if found else ""
    raise NirfInputError(f"No institution called '{typed}' in the NIRF data.{hint}")


def find_institution(name: str) -> str:
    """The institution key for what a person typed (rules in match_institution()).

    A family swap ('IIT Bangalore') is not made silently here: the message names the institutes that do
    exist in that place, so the person can pick one. The chat (nlq/resolve.py) makes the swap and says so.
    """
    m = match_institution(name)
    if m.how == "swap":
        options = [short_label(k) for k in [m.key, *m.alternatives]]
        listed = options[0] if len(options) == 1 else ", ".join(options[:-1]) + " or " + options[-1]
        raise NirfInputError(f"There's no {str(name).strip()} in the NIRF rankings. Did you mean {listed}?")
    return m.key


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
