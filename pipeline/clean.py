"""Cleaning and integration pipeline (Phase 4): all raw NIRF CSVs -> one master table.

Reads every raw CSV in data/raw/csv/<year>/ (never changes them) and writes:

  data/processed/nirf_master.parquet (+ .csv)        one row per (year, category, ranked institution):
                                                     every exact-rank row and every rank-band row
  data/processed/nirf_participants.parquet          the "List of Participating Institutions" pages
                                                     and the 2018 Special Mention page (no ranks);
                                                     kept apart so they are never counted as ranked
  data/mappings/institution_aliases.csv              every raw name -> institution_key
  data/mappings/institution_review.csv               uncertain name matches for a human (approve yes/no)
  docs/cleaning_report.md                            what every step did, with real examples

The pipeline is a list of small step functions run in order. Each one takes the table, returns
the cleaned table, and fills a StepRecord (rows before/after, what changed, why, examples) that
becomes one section of the cleaning report. Hand-checked lookup tables (data/mappings/
category_map.csv, state_map.csv, institution_alias_rules.csv) are inputs: if the data holds a value
they do not cover, the pipeline stops and says which value, instead of guessing.

Run from the project root:
    python -m pipeline.clean
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline import identity
from pipeline.audit import fmt_years
from pipeline.report import write_report

ROOT = Path(__file__).resolve().parents[1]
RAW_CSV_DIR = ROOT / "data" / "raw" / "csv"
MAPPINGS = ROOT / "data" / "mappings"
PROCESSED = ROOT / "data" / "processed"
CATEGORY_MAP = MAPPINGS / "category_map.csv"
STATE_MAP = MAPPINGS / "state_map.csv"
ALIAS_RULES = MAPPINGS / "institution_alias_rules.csv"
ALIASES = MAPPINGS / "institution_aliases.csv"
REVIEW = MAPPINGS / "institution_review.csv"
REPORT = ROOT / "docs" / "cleaning_report.md"

YEARS = range(2017, 2026)
RANKED_PAGES = {"ranking", "band"}

# Standard rank bands used for band/transition analysis (Q7.x). A smaller rank is better.
STANDARD_BANDS = [(1, 10), (11, 25), (26, 50), (51, 100), (101, 150), (151, 200), (201, 300)]

PARAMETERS = ["tlr", "rpc", "go", "oi", "pr"]
RESEARCH_PARAMETERS = ["qnr", "qlr", "sfc"]
SCORE_COLUMNS = ["score"] + PARAMETERS + RESEARCH_PARAMETERS
PARAM_RANK_COLUMNS = ["tlr_rank", "rpc_rank", "go_rank", "oi_rank", "pr_rank"]

# Raw column name -> snake_case name.
COLUMN_NAMES = {
    "Institute ID": "institute_id", "Name": "institute_name", "City": "city", "State": "state",
    "Score": "score", "Rank": "rank_raw", "rank_band": "rank_band_nirf", "row_note": "source_note",
}

log = logging.getLogger("pipeline.clean")


# --------------------------------------------------------------------------------------------
# Step bookkeeping
# --------------------------------------------------------------------------------------------

@dataclass
class StepRecord:
    """What one step did, for the log and the cleaning report."""
    number: str
    title: str
    rows_before: int = 0
    rows_after: int = 0
    changed: str = ""                     # what changed, in plain words (markdown)
    why: str = ""                         # why we do it
    examples: pd.DataFrame | None = None  # real before -> after examples
    details: list = field(default_factory=list)   # extra blocks: markdown text or DataFrames


@dataclass
class Context:
    """State shared by the steps: the participants table (split off in step 6b) and the records."""
    records: list[StepRecord] = field(default_factory=list)
    participants: pd.DataFrame | None = None
    identity: identity.IdentityResult | None = None


def run_step(fn, df: pd.DataFrame | None, ctx: Context) -> pd.DataFrame:
    number, title = fn.step
    rec = StepRecord(number, title, rows_before=0 if df is None else len(df))
    t0 = time.perf_counter()
    out = fn(df, rec, ctx)
    rec.rows_after = len(out)
    ctx.records.append(rec)
    log.info("Step %-3s %-32s rows %6d -> %6d  (%.1fs)", number, title, rec.rows_before,
             rec.rows_after, time.perf_counter() - t0)
    return out


def step(number: str, title: str):
    def mark(fn):
        fn.step = (number, title)
        return fn
    return mark


def changed_rows(before: pd.Series, after: pd.Series) -> pd.Series:
    return before.ne(after) & ~(before.isna() & after.isna())


def pick_examples(df: pd.DataFrame, by: str | None = None, n: int = 5) -> pd.DataFrame:
    """Up to n example rows, one per value of `by` first so the examples show different cases."""
    if df.empty:
        return df
    if by is None:
        return df.head(n)
    first = df.drop_duplicates(by).head(n)
    rest = df.drop(first.index).head(n - len(first))
    return pd.concat([first, rest])


# --------------------------------------------------------------------------------------------
# Steps
# --------------------------------------------------------------------------------------------

@step("1", "Combine raw CSVs")
def combine(_df, rec: StepRecord, ctx: Context) -> pd.DataFrame:
    """Stack every raw CSV into one table. All values stay text; missing columns become blank."""
    frames, files = [], []
    for path in sorted(RAW_CSV_DIR.glob("*/*.csv")):
        f = pd.read_csv(path, dtype=str, keep_default_na=False)
        f["_file"] = path.relative_to(ROOT).as_posix()
        frames.append(f)
        files.append((path.relative_to(ROOT).as_posix(), len(f), f["page_type"].iloc[0] if len(f) else ""))
    if not frames:
        raise SystemExit(f"No CSV files in {RAW_CSV_DIR}. Run the scraper first.")
    df = pd.concat(frames, ignore_index=True).fillna("")
    files = pd.DataFrame(files, columns=["file", "rows", "page_type"])
    by_type = files.groupby("page_type").agg(files=("file", "size"), rows=("rows", "sum")).reset_index()
    rec.changed = (f"{len(files)} CSV files stacked into one table of {len(df):,} rows and "
                   f"{df.shape[1] - 1} columns. Files with fewer columns get blank cells for the "
                   "columns they do not have.")
    rec.why = ("Every later rule must see all years and all categories at once, e.g. to spot that "
               "'Pondicherry' and 'Puducherry' are the same state, or that one institution appears in "
               "2017 and 2025 under two spellings.")
    rec.examples = pick_examples(files, by="page_type").rename(columns={"file": "raw file"})
    rec.details.append(by_type.rename(columns={"page_type": "page type"}))
    return df


@step("2", "Column names to snake_case")
def snake_case(df: pd.DataFrame, rec: StepRecord, ctx: Context) -> pd.DataFrame:
    """Rename columns to one snake_case scheme; move the 2023 Innovation 'Band' column into rank_raw.

    For rank-band pages NIRF prints the band (e.g. '101-150') as the page heading instead of a rank,
    so rank_raw holds that band text: it is the rank as NIRF published it.
    """
    before_cols = [c for c in df.columns if not c.startswith("_")]
    df = df.rename(columns=COLUMN_NAMES)
    band_col = df.pop("Band")
    moved = df["rank_raw"].eq("") & band_col.ne("")
    df.loc[moved, "rank_raw"] = band_col[moved]
    is_band = df["page_type"].eq("band")
    df.loc[is_band, "rank_raw"] = df.loc[is_band, "rank_band_nirf"]
    df = df.drop(columns=["scraped_at"])
    renamed = [(old, COLUMN_NAMES[old]) for old in before_cols if old in COLUMN_NAMES]
    renamed.append(("Band (Innovation 2023 only)", "rank_raw"))
    rec.changed = (f"{len(renamed)} columns renamed ({len(before_cols)} raw columns -> "
                   f"{df.shape[1] - 1}). The 2023 Innovation page put its rank in a column called "
                   f"'Band'; those {int(moved.sum())} values were moved into rank_raw. On the "
                   f"{int(is_band.sum()):,} rank-band rows, rank_raw is filled with the band heading "
                   "(e.g. '101-150'), which is the only rank NIRF gives them. The download time "
                   "(scraped_at) is dropped: it describes our scrape, not the data.")
    rec.why = ("One naming scheme means every engine and the chatbox can refer to the same columns in "
               "every year; the raw files used Title Case, lower case and one odd name ('Band').")
    rec.examples = pd.DataFrame(renamed[:4] + renamed[-1:], columns=["raw column", "new column"])
    return df


@step("3", "Year to integer")
def year_to_int(df: pd.DataFrame, rec: StepRecord, ctx: Context) -> pd.DataFrame:
    """Year text -> integer, checked against the folder the file came from and the range 2017-2025."""
    raw = df["year"].copy()
    df["year"] = pd.to_numeric(df["year"], errors="raise").astype(int)
    folder_year = df["_file"].str.extract(r"/(\d{4})/")[0].astype(int)
    bad = df["year"].ne(folder_year) | ~df["year"].isin(YEARS)
    if bad.any():
        raise SystemExit(f"{int(bad.sum())} rows have a year outside 2017-2025 or unlike their folder.")
    rec.changed = (f"'year' converted from text to integer for all {len(df):,} rows. Every year is in "
                   "2017-2025 and equals the year folder of its file (0 mismatches).")
    rec.why = "Years must be numbers to sort them, filter ranges (2019-2023) and draw time axes."
    ex = df.drop_duplicates("year").head(5)
    rec.examples = pd.DataFrame({"file": ex["_file"], "year before (text)": raw[ex.index].map(repr),
                                 "year after (int)": ex["year"]})
    return df


@step("4", "Standard category names")
def categories(df: pd.DataFrame, rec: StepRecord, ctx: Context) -> pd.DataFrame:
    """Add category_std from data/mappings/category_map.csv; category_original is kept unchanged."""
    cmap = pd.read_csv(CATEGORY_MAP, dtype={"year": int}, keep_default_na=False)
    df["category_original"] = df["category_original"].str.strip()
    df = df.merge(cmap[["category_original", "year", "category_std"]], how="left",
                  on=["category_original", "year"], validate="many_to_one")
    missing = df.loc[df["category_std"].isna(), ["category_original", "year"]].drop_duplicates()
    if len(missing):
        raise SystemExit(f"Category labels missing from {CATEGORY_MAP.name}:\n{missing.to_string()}")
    renamed = df[df["category_original"].ne(df["category_std"])]
    ex = (renamed.groupby(["category_original", "year", "category_std"]).size()
          .reset_index(name="rows").sort_values("year", ascending=False)
          .drop_duplicates("category_original"))
    rec.changed = (f"{df['category_original'].nunique()} published labels mapped to "
                   f"{df['category_std'].nunique()} standard categories using {len(cmap)} "
                   f"(label, year) rows in `data/mappings/category_map.csv`. "
                   f"{len(renamed):,} rows got a standard name different from their label. "
                   "`category_original` keeps the label exactly as NIRF printed it that year.")
    rec.why = ("NIRF renamed some lists ('Research' -> 'Research Institutions', 'Architecture' -> "
               "'Architecture and Planning') without changing what they rank. One standard name lets "
               "a trend line run across the rename; the original label is kept for honest "
               "historical comparison.")
    rec.examples = pick_examples(ex[["category_original", "year", "category_std", "rows"]])
    intro = cmap.groupby("category_std")["introduced_year"].first().sort_values()
    notes = cmap[cmap["note"].ne("")].drop_duplicates("category_std")[["category_std", "note"]]
    tbl = (intro.rename("introduced_year").reset_index()
           .merge(notes, how="left", on="category_std").fillna(""))
    rec.details.append(tbl)
    return df


@step("5", "Standard state names + region")
def states(df: pd.DataFrame, rec: StepRecord, ctx: Context) -> pd.DataFrame:
    """Map every raw State spelling to the official current state/UT name and add a region."""
    smap = pd.read_csv(STATE_MAP, keep_default_na=False)
    lookup = smap.set_index("state_raw")
    df["state_original"] = df["state"]
    key = df["state"].str.strip()
    unknown = sorted(set(key) - set(lookup.index))
    if unknown:
        raise SystemExit(f"State values missing from {STATE_MAP.name}: {unknown}")
    df["state"] = key.map(lookup["state_std"])
    df["region"] = key.map(lookup["region"])
    ch = df[df["state"].ne(df["state_original"])]
    ex = (ch.groupby(["state_original", "state"]).size().reset_index(name="rows")
          .sort_values("rows", ascending=False))
    rec.changed = (f"{df['state_original'].nunique()} raw spellings -> {df['state'].nunique()} official "
                   f"states/UTs; {len(ch):,} rows changed. `state_original` keeps the raw text. "
                   f"Every state gets one of {df['region'].nunique()} regions.")
    rec.why = ("A state count (Q2.1) or a map would split one state into several bars "
               "('Jammu & Kashmir', 'Jammu And Kashmir'). Regions follow the Ministry of Home Affairs "
               "zonal councils (Northern, Central, Eastern, Western, Southern), with the eight North "
               "Eastern Council states as North-East.")
    rec.examples = pick_examples(ex, by="state")
    reg = (df.drop_duplicates("state").groupby("region")["state"]
           .apply(lambda s: ", ".join(sorted(s))).reset_index())
    rec.details.append(reg.rename(columns={"state": "states/UTs in the data"}))
    return df


_SMALL_WORDS = {"of", "and", "for", "the", "in", "at", "on", "to", "by", "&"}


def _smart_title(s: str) -> str:
    words = s.lower().split(" ")
    out = []
    for i, w in enumerate(words):
        if i > 0 and w in _SMALL_WORDS:
            out.append(w)
        else:
            out.append(re.sub(r"(^|[(\-/.])([a-z])", lambda m: m.group(1) + m.group(2).upper(), w))
    return " ".join(out)


def tidy_name(s: str) -> str:
    """Display clean-up of an institution name: punctuation, spacing, case and PIN codes (an address
    fragment some colleges add to their name). Words are never changed."""
    s = s.replace(" ", " ")
    s = re.sub(r"(?<=[A-Za-z])[`’�?](?=s\b)", "'", s)      # Xavier`s / Vidyapeeth?s -> Xavier's
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s*[-,]?\s*\b\d{3}\s?\d{3}\b\.?", "", s)               # PIN code: 'Kalady-683 574' -> 'Kalady'
    s = re.sub(r"\s+,", ",", s)                                       # 'College , Amravati' -> 'College, Amravati'
    s = re.sub(r",(?=[^\s\d])", ", ", s)                              # 'Law College,Burtuk' -> ', '
    s = re.sub(r"(?<=\w) -(?=\w)|(?<=\w)- (?=\w)", " - ", s)          # 'Science -Pilani' -> 'Science - Pilani'
    s = re.sub(r"[,;]+$", "", s).strip()
    if re.search(r"\b[a-z]{4,}\.$", s, flags=re.IGNORECASE) and not re.search(r"\bDist\.$", s):
        s = s[:-1]                                                    # 'Rohtak.' -> 'Rohtak'
    letters = re.sub(r"[^A-Za-z ]", "", s)
    if letters.isupper() and len(letters.split()) >= 3:
        s = _smart_title(s)
    return s


def tidy_city(s: str) -> str:
    """Display clean-up of a city: spacing, PIN codes removed, Title Case when all upper/lower."""
    s = re.sub(r"\s+", " ", s.replace(" ", " ")).strip()
    s = re.sub(r",?\s*Pin\s*:?\s*\d{3}\s?\d{3}", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*-?\s*\b\d{3}\s?\d{3}\b", "", s)
    s = re.sub(r"(?<=[A-Za-z])-\d{1,3}$", "", s)                       # 'Calcutta-16' -> 'Calcutta'
    s = re.sub(r"\s+,", ",", s)
    s = re.sub(r",(?=\S)", ", ", s).strip(" ,-")
    if s.isupper() or s.islower():
        s = s.title()
    return s


@step("6", "Text tidy (names, cities)")
def text_tidy(df: pd.DataFrame, rec: StepRecord, ctx: Context) -> pd.DataFrame:
    """Trim spaces, collapse double spaces, normalise commas/hyphens/apostrophes, fix case."""
    df["institute_name_raw"] = df["institute_name"]
    df["institute_name"] = df["institute_name"].map(tidy_name)
    city_raw = df["city"].copy()
    df["city"] = df["city"].map(tidy_city)
    for col in ["institute_id", "rank_raw", "rank_band_nirf"] + SCORE_COLUMNS + PARAM_RANK_COLUMNS:
        df[col] = df[col].str.strip()

    nm = changed_rows(df["institute_name_raw"], df["institute_name"])
    ct = changed_rows(city_raw, df["city"])

    def kind(a: str, b: str) -> str:
        if a.upper() == a and b.upper() != b:
            return "UPPER CASE -> Title Case"
        if re.search(r"[`�?]", a):
            return "broken apostrophe"
        if re.search(r"\s,|,\S", a):
            return "comma spacing"
        if re.search(r"\w -\w|\w- \w", a):
            return "hyphen spacing"
        if re.search(r"\s{2,}|^\s|\s$", a):
            return "extra spaces"
        if re.search(r"\d{3}\s?\d{3}", a):
            return "PIN code removed"
        return "trailing punctuation"

    ex = df.loc[nm, ["institute_name_raw", "institute_name"]].drop_duplicates()
    ex["kind"] = [kind(a, b) for a, b in zip(ex["institute_name_raw"], ex["institute_name"])]
    cex = pd.DataFrame({"institute_name_raw": city_raw[ct], "institute_name": df.loc[ct, "city"]}
                       ).drop_duplicates()
    cex["kind"] = "city"
    allex = pd.concat([pick_examples(ex, by="kind", n=4), cex.head(1)])
    rec.examples = allex.rename(columns={"institute_name_raw": "before", "institute_name": "after"})
    counts = ex["kind"].value_counts()
    rec.changed = (f"Institution names changed on {int(nm.sum()):,} rows ({len(ex):,} distinct "
                   f"spellings): " + ", ".join(f"{k} {v}" for k, v in counts.items()) +
                   f". Cities changed on {int(ct.sum()):,} rows. The untouched name is kept in "
                   "`institute_name_raw` (used by the alias table). Words are never changed here: "
                   "'Govt.' stays 'Govt.'; matching different wordings is step 7's job.")
    rec.why = ("Invisible differences (a double space, ' ,' or a backtick instead of an apostrophe) "
               "would make one name look like two, and UPPER CASE names look broken in charts.")
    return df


@step("6b", "Split ranked rows / participant lists")
def split_lists(df: pd.DataFrame, rec: StepRecord, ctx: Context) -> pd.DataFrame:
    """Keep ranking + rank-band rows in the master table; participant lists go to their own table."""
    ranked = df["page_type"].isin(RANKED_PAGES)
    side = df[~ranked].copy()
    side["list_type"] = side["page_type"].map({"participants": "participant",
                                               "special_mention": "special_mention"})
    ctx.participants = side
    counts = df.groupby("page_type").size().rename("rows").reset_index()
    counts["goes to"] = counts["page_type"].map(
        lambda p: "master table" if p in RANKED_PAGES else "participants table")
    rec.changed = (f"{int(ranked.sum()):,} ranked rows (exact rank or rank band) stay in the master "
                   f"table; {len(side):,} rows from participant lists and the 2018 Special Mention "
                   "page move to `nirf_participants.parquet`.")
    rec.why = ("Participant lists are 5-6 times longer than the rankings and repeat every ranked "
               "institution without a rank. Mixed into the master table they would be counted as "
               "'ranked' in every count, share and top-N question. They stay available for "
               "participation counts.")
    rec.examples = counts
    return df[ranked].copy()


@step("7", "Institution identity")
def institutions(df: pd.DataFrame, rec: StepRecord, ctx: Context) -> pd.DataFrame:
    """institution_key + canonical_name for every row (see pipeline/identity.py for the rules)."""
    smap = pd.read_csv(STATE_MAP, keep_default_na=False)
    state_keys = {s: identity.name_key(s) for s in smap["state_std"].unique()}
    if not ALIAS_RULES.exists():
        pd.DataFrame(columns=identity.RULE_COLUMNS).to_csv(ALIAS_RULES, index=False)
    res = identity.identify(df, ALIAS_RULES, REVIEW, ALIASES, state_keys)
    ctx.identity = res
    res.aliases.to_csv(ALIASES, index=False)
    res.review.to_csv(REVIEW, index=False)
    side = ctx.participants
    side["institution_key"], side["canonical_name"] = identity.lookup_keys(side, res.lookup)

    s = res.stats
    by_method = res.aliases["match_method"].value_counts()
    rec.changed = (
        f"{s['raw_names']:,} raw name spellings ({s['nodes']:,} distinct cleaned name + state "
        f"combinations) were grouped into **{s['institutions']:,} institutions**. Links made: "
        + ", ".join(f"{m} {n}" for m, n in s["links_by_method"].items())
        + f". Proposed links refused because both rows sit in the same ranking list: {len(res.skipped)}. "
        f"Names that stand for 2+ different institutions in one state and were split by city: "
        f"{s['ambiguous_names']}. ID codes that cover several different units in one year and were "
        f"not used for linking: {len(s['parent_codes'])} ({', '.join(s['parent_codes']) or 'none'}). "
        f"**{s['review_waiting']} uncertain pairs wait in `data/mappings/institution_review.csv`** "
        f"(human decisions read back this run: {s['decisions_yes']} yes, {s['decisions_no']} no). "
        f"Hand alias rules applied: {s['n_rules']}. Participant rows linked to a ranked "
        f"institution: {int(side['institution_key'].ne('').sum()):,} of {len(side):,}.")
    rec.why = (
        "Every trend, mobility and new-entrant question follows one institution over the years. "
        "Without one key, 'Indian Institute of Technology, Delhi' (2022) and 'Indian Institute of "
        "Technology Delhi' (other years) would be two institutions, and IIT Delhi's 2022 rank would "
        "vanish from its line. Uncertain cases are left for a human rather than guessed.")
    rec.examples = _identity_examples(res)
    rec.details.append("Alias table rows per match method:")
    rec.details.append(by_method.rename("raw spellings").rename_axis("match_method").reset_index())
    if s["rule_problems"]:
        rec.details.append("Alias rules that could not be applied:\n\n" +
                           "\n".join(f"- {p}" for p in s["rule_problems"]))
    return res.df.drop(columns=["name_key", "city_key", "node", "alias_city"])


def _identity_examples(res: identity.IdentityResult) -> pd.DataFrame:
    a = res.aliases[res.aliases["raw_name"].ne(res.aliases["canonical_name"])]
    a = a.sort_values("match_score")
    out = []
    for m in ["id_code", "alias_rule", "fuzzy", "exact", "review_approved"]:
        sub = a[a["match_method"].eq(m)]
        if len(sub):
            out.append(sub.iloc[[0]] if m == "id_code" else sub.iloc[[len(sub) // 2]])
    ex = pd.concat(out) if out else a.head(5)
    if len(ex) < 5:
        ex = pd.concat([ex, a[a["match_method"].eq("id_code")].iloc[1:1 + 5 - len(ex)]])
    return ex[["raw_name", "state", "canonical_name", "institution_key", "match_method", "match_score"]]


def band_for(lo: int, hi: int) -> tuple[str, int, int]:
    """The standard band that contains [lo, hi], or NIRF's own band when it spans two standard bands."""
    for b_lo, b_hi in STANDARD_BANDS:
        if b_lo <= lo and hi <= b_hi:
            return f"{b_lo}-{b_hi}", b_lo, b_hi
    return f"{lo}-{hi}", lo, hi


@step("8", "Ranks, ties and rank bands")
def ranks(df: pd.DataFrame, rec: StepRecord, ctx: Context) -> pd.DataFrame:
    """rank (exact integer), rank_status, is_tie, rank_band (+ low/high), is_banded, in_top10/50/100.

    rank_status: exact | lettered (NIRF printed e.g. '21A') | band | withdrawn.
    """
    raw = df["rank_raw"]
    plain = raw.str.fullmatch(r"\d+")
    lettered = raw.str.fullmatch(r"\d+[A-Za-z]")
    withdrawn = raw.str.contains("withdrawn", case=False)
    banded = df["page_type"].eq("band")
    status = np.select([plain, lettered, withdrawn, banded], ["exact", "lettered", "withdrawn", "band"], "")
    if (status == "").any():
        bad = df.loc[status == "", ["year", "category_std", "institute_name", "rank_raw"]]
        raise SystemExit(f"Unknown rank formats:\n{bad.to_string()}")
    df["rank_status"] = status
    df["rank"] = pd.array(raw.str.extract(r"^(\d+)")[0].where(plain | lettered).astype(float), dtype="Int64")
    exact = df["rank_status"].eq("exact")
    tie_size = df[exact].groupby(["year", "category_std", "rank"])["rank"].transform("size")
    df["is_tie"] = False
    df.loc[tie_size.index, "is_tie"] = tie_size.gt(1)
    df["is_banded"] = banded

    lo = df["rank"].astype(float)
    hi = df["rank"].astype(float)
    bnd = df.loc[banded, "rank_band_nirf"].str.extract(r"^(\d+)-(\d+)$").astype(float)
    lo[banded], hi[banded] = bnd[0], bnd[1]
    bands = [band_for(int(a), int(b)) if pd.notna(a) else ("", np.nan, np.nan) for a, b in zip(lo, hi)]
    df["rank_band"] = [b[0] for b in bands]
    df["rank_band_low"] = pd.array([b[1] for b in bands], dtype="Int64")
    df["rank_band_high"] = pd.array([b[2] for b in bands], dtype="Int64")
    df["rank_band"] = df["rank_band"].replace("", pd.NA)
    df["rank_band_nirf"] = df["rank_band_nirf"].replace("", pd.NA)
    top_of = df["rank"].astype(float).where(~banded, df["rank_band_high"].astype(float))
    for n in (10, 50, 100):
        df[f"in_top{n}"] = top_of.le(n).fillna(False).astype(bool)

    odd = df[~df["rank_band"].isin([f"{a}-{b}" for a, b in STANDARD_BANDS]) & df["rank_band"].notna()]
    counts = df["rank_status"].value_counts()
    rec.changed = (
        f"rank_status: " + ", ".join(f"{k} {v:,}" for k, v in counts.items()) + ". "
        f"`rank` is an integer for exact ranks; {int(df['is_tie'].sum())} rows share their rank with "
        f"another institution (`is_tie`). Banded rows keep `rank` empty: NIRF gives only the band, "
        f"and we never invent a mid-point. Every row with a known position gets a standard "
        f"`rank_band` ({', '.join(f'{a}-{b}' for a, b in STANDARD_BANDS)}); NIRF bands like 51-75 or "
        f"102-125 fall inside one standard band. {len(odd)} banded rows ({', '.join(sorted(odd['rank_band'].unique()))}) "
        f"span two standard bands and keep NIRF's band. `in_top10/50/100` use the exact rank, or the "
        f"band's upper limit for banded rows (a 76-100 row is in the top 100 for sure). 'Lettered' "
        f"ranks ('21A', '26A', '16A' in 2018) keep their number: each one's score is just above the "
        f"plain rank with the same number (e.g. 21A = 53.24 vs rank 21 = 53.16), so NIRF slotted "
        f"them in without renumbering; they are flagged so the team can revisit this choice. "
        f"'Rank Withdrawn' rows get no rank.")
    rec.why = ("Rank is the main measure in most of the 40 questions. Keeping rank_raw shows exactly "
               "what NIRF printed; the clean numeric rank and the bands make 'top 50', 'moved from "
               "51-100 into the top 50' (Q7.1) and 'same band next year' (Q7.3) simple filters.")
    pick = pd.concat([
        df[exact & ~df["is_tie"]].head(1), df[df["is_tie"]].head(1),
        df[df["rank_status"].eq("lettered")].head(1), df[banded].drop_duplicates("rank_band_nirf").iloc[[1]],
        df[df["rank_status"].eq("withdrawn")].head(1)])
    rec.examples = pick[["year", "category_std", "institute_name", "rank_raw", "rank", "rank_status",
                         "is_tie", "rank_band", "in_top100"]]
    bt = (df[banded].groupby(["rank_band_nirf", "rank_band"]).size().reset_index(name="rows")
          .assign(_lo=lambda t: t["rank_band_nirf"].str.extract(r"^(\d+)")[0].astype(int))
          .sort_values("_lo").drop(columns="_lo"))
    rec.details.append("NIRF band -> standard band:")
    rec.details.append(bt)
    return df


@step("9", "Numbers to float, range check")
def numbers(df: pd.DataFrame, rec: StepRecord, ctx: Context) -> pd.DataFrame:
    """score + parameters -> float (outside 0-100 -> NaN, logged); parameter ranks -> integer."""
    raw = df[SCORE_COLUMNS].copy()
    bad_rows = []
    for col in SCORE_COLUMNS:
        v = pd.to_numeric(df[col].replace("", np.nan), errors="coerce")
        not_number = df[col].ne("") & v.isna()
        out_of_range = v.notna() & ~v.between(0, 100)
        for i in df.index[not_number | out_of_range]:
            bad_rows.append({"year": df.at[i, "year"], "category": df.at[i, "category_std"],
                             "institute": df.at[i, "institute_name"], "column": col, "raw": df.at[i, col]})
        df[col] = v.where(~out_of_range).astype(float)
    for col in PARAM_RANK_COLUMNS:
        df[col] = pd.array(pd.to_numeric(df[col].replace("", np.nan), errors="raise"), dtype="Int64")
    for r in bad_rows:
        log.warning("Value set to NaN: %s", r)
    exact = df[df["rank_status"].eq("exact") & df["score"].notna()]
    order_breaks = 0
    for _, g in exact.groupby(["year", "category_std"]):
        g = g.sort_values("rank")
        order_breaks += int((g["score"].diff() > 0).sum())
    rec.changed = (f"{len(SCORE_COLUMNS)} score columns ({', '.join(SCORE_COLUMNS)}) converted from text "
                   f"to decimal numbers, 5 parameter-rank columns to integers. Values that were not a "
                   f"number or were outside 0-100 and became NaN: **{len(bad_rows)}**. Check that a "
                   f"better rank never has a lower score: {order_breaks} violations.")
    rec.why = ("Means, medians, correlations and box plots need numbers. Every NIRF score is out of "
               "100, so a value outside 0-100 can only be an error and must not reach a chart.")
    ex = df[df["score"].notna()].drop_duplicates("category_std").head(5)
    rec.examples = pd.DataFrame({"institute": ex["institute_name"], "category": ex["category_std"],
                                 "score text": raw.loc[ex.index, "score"].map(repr),
                                 "score number": ex["score"],
                                 "pr text": raw.loc[ex.index, "pr"].map(repr), "pr number": ex["pr"]})
    if bad_rows:
        rec.details.append(pd.DataFrame(bad_rows))
    return df


CATEGORY_PARAMETERS = {"Research Institutions": RESEARCH_PARAMETERS + ["oi", "pr"]}


@step("10", "Missing values (never invented)")
def missing_values(df: pd.DataFrame, rec: StepRecord, ctx: Context) -> pd.DataFrame:
    """Leave NaN; add has_score and has_parameter_scores; explain every gap."""
    df["has_score"] = df["score"].notna()
    has_params = pd.Series(False, index=df.index)
    for cat, g in df.groupby("category_std"):
        cols = CATEGORY_PARAMETERS.get(cat, PARAMETERS)
        has_params[g.index] = g[cols].notna().all(axis=1)
    df["has_parameter_scores"] = has_params

    def reason(r) -> str:
        if r.rank_status == "band":
            return "rank-band row: NIRF lists only the name, city and state"
        if r.rank_status == "withdrawn":
            return "rank withdrawn by NIRF: no score shown"
        if r.category_std in ("Innovation", "Open University", "Skill University", "SDG"):
            return "rank-only category: NIRF publishes no scores"
        return "blank on the NIRF page"

    gaps = df[~df["has_score"] | ~df["has_parameter_scores"]]
    tbl = (gaps.assign(reason=[reason(r) for r in gaps.itertuples()])
           .groupby(["reason", "category_std"])
           .agg(rows=("year", "size"), years=("year", lambda y: fmt_years(y)),
                no_score=("has_score", lambda s: int((~s).sum())),
                no_parameters=("has_parameter_scores", lambda s: int((~s).sum())))
           .reset_index().sort_values(["reason", "rows"], ascending=[True, False]))
    research = df["category_std"].eq("Research Institutions")
    rec.changed = (
        f"No value is filled in or estimated. `has_score` is False on {int((~df['has_score']).sum()):,} "
        f"rows and `has_parameter_scores` on {int((~df['has_parameter_scores']).sum()):,} rows; the "
        f"table below says why. Research Institutions ({int(research.sum())} rows) have no TLR/RPC/GO "
        f"by design (they use QNR/QLR/SFC instead), so for them `has_parameter_scores` checks QNR, QLR, "
        f"SFC, OI and PR. City is blank on {int(df['city'].eq('').sum())} rows (the 2023 Innovation page "
        f"has no City column).")
    rec.why = ("A made-up score (e.g. a band mid-point or a category average) would look like real "
               "NIRF data in every chart. Flags let each engine filter to rows that really have the "
               "numbers a question needs, and the reason table lets us answer 'why is this missing?'.")
    rec.examples = pick_examples(gaps[["year", "category_std", "institute_name", "rank_raw", "score",
                                       "tlr", "pr"]], by="category_std")
    rec.details.append(tbl)
    return df


@step("11", "Duplicates")
def duplicates(df: pd.DataFrame, rec: StepRecord, ctx: Context) -> pd.DataFrame:
    """Drop exact duplicate rows; for duplicate (year, category_std, institution_key) keep the most
    complete row (most non-blank values) and log the dropped one."""
    data_cols = [c for c in df.columns if not c.startswith("_")]
    exact_dup = df.duplicated(subset=data_cols)
    dropped_exact = df[exact_dup]
    df = df[~exact_dup].copy()
    df["_filled"] = df[data_cols].notna().sum(axis=1) + df[data_cols].astype(str).ne("").sum(axis=1)
    df = df.sort_values("_filled", ascending=False, kind="stable")
    key_dup = df.duplicated(subset=["year", "category_std", "institution_key"])
    dropped_key = df[key_dup]
    for r in dropped_key.itertuples():
        log.warning("Duplicate key dropped: %s %s %s %s", r.year, r.category_std, r.institution_key,
                    r.institute_name)
    df = df[~key_dup].drop(columns="_filled").sort_index()
    side = ctx.participants
    side_dups = int(side.duplicated(subset=["year", "category_std", "list_type", "institute_name_raw",
                                            "city", "state"]).sum())
    rec.changed = (f"Exact duplicate rows dropped: **{len(dropped_exact)}**. Duplicate (year, category, "
                   f"institution_key) rows dropped: **{len(dropped_key)}**. The identity step already "
                   f"refuses to give two rows of one list the same key, so 0 is expected and confirms "
                   f"it. In the participants table, {side_dups} rows repeat another row's name, city "
                   f"and state in the same list; they are kept, because several are different colleges "
                   f"with the same generic name in one district (e.g. 'Government Degree College', "
                   f"Srikakulam, 5 times in 2018).")
    rec.why = ("A duplicate would count one institution twice in every count and average and break "
               "the rule 'one row per institution per category per year'.")
    ex = pd.concat([dropped_exact, dropped_key])
    rec.examples = (ex[["year", "category_std", "institute_name", "rank_raw"]] if len(ex) else
                    pd.DataFrame({"result": ["no duplicate rows found in the master table"]}))
    return df


@step("12", "Derived columns")
def derived(df: pd.DataFrame, rec: StepRecord, ctx: Context) -> pd.DataFrame:
    """first_year_seen, is_new_entrant, years_present: all per institution per category."""
    g = df.groupby(["institution_key", "category_std"])["year"]
    df["first_year_seen"] = g.transform("min").astype(int)
    df["years_present"] = g.transform("nunique").astype(int)
    launch = df.groupby("category_std")["year"].transform("min")
    df["is_new_entrant"] = df["year"].eq(df["first_year_seen"]) & df["year"].gt(launch)
    new = df[df["is_new_entrant"]]
    rec.changed = (f"`first_year_seen` = the first year the institution appears in that category's "
                   f"ranked list (exact or band). `years_present` = how many different years it appears "
                   f"there. `is_new_entrant` = this row is its first appearance AND the category already "
                   f"existed the year before (nobody is 'new' in 2017, the first year of our data, or in "
                   f"a category's launch year). New-entrant rows: {len(new):,}.")
    rec.why = ("Q2.5 (states producing the most new institutions) and the mobility questions need to "
               "know when an institution first entered a list and how often it has been there.")
    ex_keys = ["Indian Institute of Technology Madras"]
    pick = pd.concat([
        df[df["canonical_name"].isin(ex_keys) & df["category_std"].eq("Overall")].sort_values("year").head(1),
        new.sort_values("year").drop_duplicates("category_std").head(4)])
    rec.examples = pick[["institution_key", "canonical_name", "category_std", "year", "first_year_seen",
                         "is_new_entrant", "years_present"]]
    return df


# --------------------------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------------------------

MASTER_COLUMNS = [
    "institution_key", "canonical_name", "institute_name", "institute_id", "city", "state",
    "state_original", "region", "year", "category_std", "category_original",
    "rank_raw", "rank", "rank_status", "is_tie", "is_banded", "rank_band", "rank_band_low",
    "rank_band_high", "rank_band_nirf", "in_top10", "in_top50", "in_top100",
    "score", *PARAMETERS, *RESEARCH_PARAMETERS, *PARAM_RANK_COLUMNS,
    "has_score", "has_parameter_scores", "first_year_seen", "is_new_entrant", "years_present",
    "institute_name_raw", "source_url", "source_note",
]
PARTICIPANT_COLUMNS = [
    "institution_key", "canonical_name", "institute_name", "city", "state", "state_original", "region",
    "year", "category_std", "category_original", "list_type", "institute_name_raw", "source_url",
]


def save(master: pd.DataFrame, participants: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    master = master[MASTER_COLUMNS].sort_values(
        ["year", "category_std", "rank_band_low", "rank", "institute_name"]).reset_index(drop=True)
    for c in ["city", "institute_id", "source_note"]:
        master[c] = master[c].replace("", pd.NA)
    participants = participants[PARTICIPANT_COLUMNS].copy()
    participants["institution_key"] = participants["institution_key"].replace("", pd.NA)
    participants["canonical_name"] = participants["canonical_name"].replace("", pd.NA)
    participants = participants.sort_values(["year", "category_std", "list_type", "institute_name"]
                                            ).reset_index(drop=True)
    master.to_parquet(PROCESSED / "nirf_master.parquet", index=False)
    master.to_csv(PROCESSED / "nirf_master.csv", index=False)
    participants.to_parquet(PROCESSED / "nirf_participants.parquet", index=False)
    return master, participants


STEPS = [combine, snake_case, year_to_int, categories, states, text_tidy, split_lists, institutions,
         ranks, numbers, missing_values, duplicates, derived]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ctx = Context()
    df = None
    for fn in STEPS:
        df = run_step(fn, df, ctx)
    master, participants = save(df, ctx.participants)
    write_report(REPORT, ctx.records, master, participants, ctx.identity)
    log.info("Master table: %d rows x %d columns -> %s", len(master), master.shape[1],
             (PROCESSED / "nirf_master.parquet").relative_to(ROOT))
    log.info("Participants table: %d rows", len(participants))
    log.info("Review file: %d pairs wait for a human decision -> %s",
             ctx.identity.stats["review_waiting"], REVIEW.relative_to(ROOT))
    log.info("Report -> %s", REPORT.relative_to(ROOT))


if __name__ == "__main__":
    main()
