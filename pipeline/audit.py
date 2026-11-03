"""Data audit (Phase 3): look at the raw NIRF data before cleaning it.

Reads every raw CSV in data/raw/csv/<year>/ (read-only, nothing in data/raw/ is changed) and writes
docs/data_audit.md, a report of every inconsistency the cleaning pipeline will have to handle:

  1. rows per year x category, and which categories exist in which year
  2. column names per year
  3. every distinct State value with counts (spelling variants)
  4. every distinct category label per year
  5. rank formats (plain numbers, ties, "21A", bands like "101-150", "Rank Withdrawn", blanks)
     and score / parameter number formats
  6. missing values per column per year
  7. exact duplicate rows and duplicate (year, category, institute) rows
  8. institutions whose names look different across years (near-duplicates found with rapidfuzz)
  9. a ranked list of cleaning problems, each with a proposed fix

Why: the cleaning rules in pipeline/ must be based on what is really in the data, and every rule
must be explainable in the viva. This report is the evidence behind each rule.

Run from the project root:
    python -m pipeline.audit
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz, process

ROOT = Path(__file__).resolve().parents[1]
RAW_CSV_DIR = ROOT / "data" / "raw" / "csv"
REPORT_PATH = ROOT / "docs" / "data_audit.md"

YEARS = list(range(2017, 2026))

# Display order for categories (slugs as written by the scraper). Unknown slugs are appended.
CATEGORY_ORDER = [
    "overall", "university", "college", "research", "engineering", "management", "pharmacy",
    "medical", "dental", "law", "architecture", "agriculture", "innovation", "open_university",
    "skill_university", "state_public_university", "sdg_institutions", "special_mention",
]

# Columns the scraper adds to describe the page; everything else is data from the site.
META_COLUMNS = ["year", "category_original", "category_slug", "page_type", "rank_band",
                "row_note", "source_url", "scraped_at"]
SCORE_COLUMNS = ["Score", "tlr", "rpc", "go", "oi", "pr", "qnr", "qlr", "sfc"]
PARAM_RANK_COLUMNS = ["tlr_rank", "rpc_rank", "go_rank", "oi_rank", "pr_rank"]

# Official names of India's 28 states and 8 union territories (after the 2020 merger of
# Dadra and Nagar Haveli with Daman and Diu). Used only to flag State values that are not official.
OFFICIAL_STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat",
    "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh",
    "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan",
    "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
    "Andaman and Nicobar Islands", "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi", "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
]
# Old or short names whose official form is different (key = state_key() of the raw value).
STATE_RENAMES = {
    "pondicherry": "Puducherry",
    "andaman and nicobar": "Andaman and Nicobar Islands",
    "dadra and nagar haveli": "Dadra and Nagar Haveli and Daman and Diu",
    "daman and diu": "Dadra and Nagar Haveli and Daman and Diu",
}

# Fuzzy matching settings for section 8.
FUZZY_THRESHOLD = 88       # token_sort_ratio (0-100) at or above which two names are "near-duplicates"
N_EXAMPLES = 30


# --------------------------------------------------------------------------------------------
# Loading and small helpers
# --------------------------------------------------------------------------------------------

def load_raw() -> pd.DataFrame:
    """Every raw CSV stacked into one table. All values stay text; a missing column becomes "".

    Two helper columns are added: `_file` (the CSV it came from) and `_cols` (the columns that
    file really has), so we can tell "this page has no such column" apart from "the cell is blank".
    """
    frames = []
    for path in sorted(RAW_CSV_DIR.glob("*/*.csv")):
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        df["_file"] = path.relative_to(ROOT).as_posix()
        df["_cols"] = "|".join(c for c in df.columns if c != "_file")
        frames.append(df)
    if not frames:
        raise SystemExit(f"No CSV files found in {RAW_CSV_DIR}. Run the scraper first.")
    df = pd.concat(frames, ignore_index=True).fillna("")
    df["year"] = df["year"].astype(int)
    return df


def norm_name(name: str) -> str:
    """Matching key for a name: lower case, '&' -> 'and', punctuation -> space, single spaces.

    'Indian Institute of Science Education & Research, Pune' and
    'Indian Institute of Science Education and Research Pune' get the same key.
    """
    s = name.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def state_key(state: str) -> str:
    """Matching key for a State value: same idea as norm_name()."""
    return norm_name(state)


def proposed_state(state: str) -> str:
    """The official state/UT name a raw State value should map to ('' if we cannot tell)."""
    key = state_key(state)
    if key in STATE_RENAMES:
        return STATE_RENAMES[key]
    for official in OFFICIAL_STATES:
        if state_key(official) == key:
            return official
    return ""


def id_code(institute_id: str) -> str:
    """The part of the NIRF Institute ID that stays the same for one institution from 2018 on.

    'IR-2-O-OE-U-0456' (2018), 'IR-O-U-0456' (2019-2025) and 'ARI-U-0456' (Innovation 2023)
    all end in 'U-0456' = IIT Madras. 2017 IDs ('IR17-...') use another scheme and return ''.
    """
    if not institute_id or institute_id.startswith("IR17"):
        return ""
    parts = institute_id.split("-")
    return "-".join(parts[-2:]) if len(parts) >= 3 else ""


def cat_sort_key(slug: str) -> tuple[int, str]:
    return (CATEGORY_ORDER.index(slug) if slug in CATEGORY_ORDER else len(CATEGORY_ORDER), slug)


def md_table(df: pd.DataFrame, index: bool = False) -> str:
    """A pandas DataFrame as a GitHub markdown table (no extra dependency needed)."""
    if index:
        df = df.reset_index()
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for row in df.itertuples(index=False):
        cells = [str(v).replace("|", "\\|").replace("\n", " ") for v in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def fmt_years(years) -> str:
    """[2017, 2018, 2019, 2021] -> '2017-2019, 2021'."""
    ys = sorted(set(int(y) for y in years))
    if not ys:
        return ""
    out, start, prev = [], ys[0], ys[0]
    for y in ys[1:] + [None]:
        if y is not None and y == prev + 1:
            prev = y
            continue
        out.append(str(start) if start == prev else f"{start}-{prev}")
        if y is not None:
            start = prev = y
    return ", ".join(out)


def ranked_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Rows that place an institution in a ranking: exact-rank pages plus rank-band pages."""
    return df[df["page_type"].isin(["ranking", "band"])]


# --------------------------------------------------------------------------------------------
# Section 1: rows per year x category
# --------------------------------------------------------------------------------------------

def section_rows(df: pd.DataFrame, facts: dict) -> str:
    """Count rows per (category, year) for each page type, and list the categories per year.

    Definition: "ranked" = rows on the main ranking page (exact rank); "band" = rows on the
    rank-band pages (only a band such as 101-150); "participants" = rows on the
    "List of Participating Institutions" pages (no rank at all).
    """
    counts = df.groupby(["category_slug", "year", "page_type"]).size().unstack(fill_value=0)
    slugs = sorted(df["category_slug"].unique(), key=cat_sort_key)

    def n(slug: str, year: int, kind: str) -> int:
        return int(counts.loc[(slug, year)].get(kind, 0)) if (slug, year) in counts.index else 0

    def ranked_cell(slug: str, year: int) -> str:
        r, b = n(slug, year, "ranking"), n(slug, year, "band")
        return f"{r} + {b}" if b else (str(r) if r else "–")

    cats = [s for s in slugs if s != "special_mention"]
    rank_tbl = pd.DataFrame([[s] + [ranked_cell(s, y) for y in YEARS] for s in cats],
                            columns=["Category (slug)"] + YEARS)
    part_tbl = pd.DataFrame([[s] + [str(n(s, y, "participants") or "–") for y in YEARS] for s in cats],
                            columns=["Category (slug)"] + YEARS)

    per_type = df.groupby(["year", "page_type"]).size().unstack(fill_value=0).reindex(YEARS, fill_value=0)
    per_type["total"] = per_type.sum(axis=1)
    per_type.loc["total"] = per_type.sum()

    cats_by_year = (df[df["page_type"] == "ranking"].groupby("year")["category_slug"]
                    .apply(lambda s: sorted(set(s), key=cat_sort_key)))
    growth, seen = [], set()
    for y in YEARS:
        cats = cats_by_year.get(y, [])
        new = [c for c in cats if c not in seen]
        seen.update(cats)
        growth.append([y, len(cats), ", ".join(new) if y > YEARS[0] else ", ".join(cats)])
    growth_tbl = pd.DataFrame(growth, columns=["Year", "Ranking categories", "New this year (2017: all)"])

    facts["n_rows"] = len(df)
    facts["n_files"] = df["_file"].nunique()
    facts["cats_2017"] = len(cats_by_year.get(2017, []))
    facts["cats_2025"] = len(cats_by_year.get(2025, []))
    facts["n_categories"] = len(seen)
    facts["n_ranked_rows"] = int((df["page_type"] == "ranking").sum())
    facts["n_band_rows"] = int((df["page_type"] == "band").sum())
    facts["n_participant_rows"] = int((df["page_type"] == "participants").sum())

    return "\n\n".join([
        "## 1. Rows per year × category",
        f"{facts['n_files']} raw CSV files, **{facts['n_rows']:,} rows** in total. Rows by page type:",
        md_table(per_type, index=True),
        "### 1a. Categories per year: how NIRF grew",
        f"NIRF ranked **{facts['cats_2017']} categories in 2017 and {facts['cats_2025']} in 2025** "
        f"({facts['n_categories']} different categories over the nine years). The 2018 \"Special Mention\" "
        "page (4 institutions, no rank, no score) is not counted as a category.",
        md_table(growth_tbl),
        "### 1b. Institutions in the ranking per category-year",
        "`exact + band` = institutions with an exact rank on the main page + institutions listed only "
        "inside rank bands (e.g. 101-150). `–` = category not published that year.",
        md_table(rank_tbl),
        "### 1c. Participating institutions per category-year",
        "From the \"List of Participating Institutions\" pages (no rank). `–` = no list published "
        "(University and Research never have one; Innovation 2023 and State Public University 2025 neither).",
        md_table(part_tbl),
        "Note: the participant lists are **8–9 times larger** than the ranked lists "
        f"({facts['n_participant_rows']:,} vs {facts['n_ranked_rows'] + facts['n_band_rows']:,} rows) "
        "and they repeat the ranked institutions. They must stay in a separate table and never be "
        "counted as ranked rows.",
    ])


# --------------------------------------------------------------------------------------------
# Section 2: column names per year
# --------------------------------------------------------------------------------------------

def section_columns(df: pd.DataFrame, facts: dict) -> str:
    """Which columns exist in which year, per page type, and which files differ from the norm.

    Method: every file keeps its own column list (`_cols`); we take the union per year and
    group files with an identical column list ("signature").
    """
    files = df.drop_duplicates("_file")[["_file", "year", "category_slug", "page_type", "_cols"]]
    out = ["## 2. Column names per year"]

    for ptype in ["ranking", "band", "participants", "special_mention"]:
        f = files[files["page_type"] == ptype]
        if f.empty:
            continue
        all_cols = []
        for cols in f["_cols"]:
            for c in cols.split("|"):
                if c not in all_cols and c not in META_COLUMNS:
                    all_cols.append(c)
        rows = []
        for c in all_cols:
            row = [f"`{c}`"]
            for y in YEARS:
                fy = f[f["year"] == y]
                if fy.empty:
                    row.append("")
                    continue
                n_with = sum(c in cols.split("|") for cols in fy["_cols"])
                row.append("✓" if n_with == len(fy) else (f"{n_with}/{len(fy)}" if n_with else "✗"))
            rows.append(row)
        out.append(f"### Page type `{ptype}` ({len(f)} files)")
        out.append("✓ = column in every file of that year, `n/m` = in n of m files, ✗ = in none. "
                   "Metadata columns added by the scraper (year, category_original, category_slug, "
                   "page_type, rank_band, row_note, source_url, scraped_at) are in every file and not shown.")
        out.append(md_table(pd.DataFrame(rows, columns=["Column"] + YEARS)))

    # Ranking-page signatures: which files have an unusual column list.
    rk = files[files["page_type"] == "ranking"].copy()
    rk["data_cols"] = rk["_cols"].apply(lambda s: ", ".join(c for c in s.split("|") if c not in META_COLUMNS))
    sig = (rk.groupby("data_cols")
             .apply(lambda g: "; ".join(f"{y} {c}" for y, c in sorted(zip(g["year"], g["category_slug"]))),
                    include_groups=False)
             .reset_index(name="files"))
    sig["n_files"] = sig["files"].str.count(";") + 1
    sig = sig.sort_values("n_files", ascending=False)
    sig["files"] = sig.apply(lambda r: "(most ranking pages)" if r["n_files"] > 25 else r["files"], axis=1)
    out.append("### Ranking pages grouped by identical column list")
    out.append(md_table(sig[["data_cols", "n_files", "files"]].rename(
        columns={"data_cols": "Data columns", "n_files": "Files", "files": "Which pages"})))
    facts["n_col_signatures"] = len(sig)
    out.append(
        "**What changes:** the core columns (`Institute ID, Name, City, State, Score, Rank`) are the same "
        "in every year. The differences are: (a) per-parameter ranks `tlr_rank … pr_rank` exist only where "
        "NIRF published the \"By TLR / By RPC\" tabs (all pages in 2017-2018, University only from 2019); "
        "(b) Research uses `qnr, qlr, sfc` instead of `tlr, rpc, go`; (c) rank-only categories (Innovation, "
        "Open/Skill University, SDG) have no `Score`; (d) Innovation 2023 has no `City` and calls its rank "
        "column `Band`.")
    return "\n\n".join(out)


# --------------------------------------------------------------------------------------------
# Section 3: State values
# --------------------------------------------------------------------------------------------

def section_states(df: pd.DataFrame, facts: dict) -> str:
    """Every distinct raw State value with its row count, the years it appears and the official
    name it should map to. Also: institutions (same ID code) whose State changes between years.
    """
    g = df.groupby("State").agg(rows=("State", "size"), years=("year", lambda s: fmt_years(s)))
    g = g.reset_index().sort_values("rows", ascending=False)
    g["official"] = g["State"].apply(proposed_state)
    g["status"] = g.apply(
        lambda r: "ok" if r["State"] in OFFICIAL_STATES
        else ("**variant** → " + r["official"] if r["official"] else "**unknown**"), axis=1)
    tbl = g[["State", "rows", "years", "status"]].rename(
        columns={"State": "State (raw)", "rows": "Rows", "years": "Years", "status": "Status / proposed name"})

    groups = g[g["official"] != ""].groupby("official")["State"].apply(list)
    multi = groups[groups.apply(len) > 1]
    var_tbl = pd.DataFrame(
        [[off, len(v), ", ".join(f"`{x}`" for x in v)] for off, v in multi.items()],
        columns=["Official name", "Raw spellings", "Spellings found"])

    facts["n_state_values"] = len(g)
    facts["n_state_official"] = len(set(g["official"]) - {""})
    facts["n_state_nonofficial_rows"] = int(g.loc[g["status"] != "ok", "rows"].sum())
    facts["n_state_nonofficial_values"] = int((g["status"] != "ok").sum())
    facts["state_unknown"] = g.loc[g["official"] == "", "State"].tolist()
    facts["n_state_blank"] = int((df["State"] == "").sum())

    # Same institution (2018+ ID code), different state across rows.
    rk = df[df["page_type"] == "ranking"].copy()
    rk["code"] = rk["Institute ID"].map(id_code)
    rk["state_official"] = rk["State"].map(proposed_state)
    rk = rk[rk["code"] != ""]
    moved = rk.groupby("code").filter(lambda x: x["state_official"].nunique() > 1)
    moved_rows = []
    for code, x in moved.groupby("code"):
        parts = [f"{st} ({fmt_years(x.loc[x['state_official'] == st, 'year'])})"
                 for st in x["state_official"].unique()]
        moved_rows.append([code, x["Name"].iloc[-1], "; ".join(parts)])
    facts["n_code_state_changes"] = len(moved_rows)

    out = [
        "## 3. State values",
        f"**{facts['n_state_values']} distinct raw State values** for {facts['n_state_official']} real "
        f"states/UTs. {facts['n_state_nonofficial_values']} values ({facts['n_state_nonofficial_rows']} rows) "
        f"are not the official spelling. Blank State cells: {facts['n_state_blank']}.",
        "The official list used is the 28 states and 8 union territories as they stand today "
        "(Dadra and Nagar Haveli and Daman and Diu merged in January 2020).",
        md_table(tbl),
        "### Spelling groups (same state, several raw spellings)",
        md_table(var_tbl),
    ]
    if moved_rows:
        out += ["### Same institution (same ID code), different State in different rows",
                "These are either a real correction by NIRF or a data-entry slip. The cleaning step should "
                "use one state per institution only if the change is clearly an error.",
                md_table(pd.DataFrame(moved_rows, columns=["ID code", "Name (latest)", "State (years)"]))]
    else:
        out.append("No institution (by ID code) changes State between years once spellings are mapped.")
    return "\n\n".join(out)


# --------------------------------------------------------------------------------------------
# Section 4: category labels per year
# --------------------------------------------------------------------------------------------

def section_categories(df: pd.DataFrame, facts: dict) -> str:
    """Every distinct category label (as NIRF wrote it in the page heading) per year."""
    rows = []
    for slug in sorted(df["category_slug"].unique(), key=cat_sort_key):
        sub = df[df["category_slug"] == slug]
        labels = sub.groupby("category_original")["year"].apply(fmt_years)
        latest = sub.loc[sub["year"] == sub["year"].max(), "category_original"].mode().iloc[0]
        rows.append([slug, "; ".join(f"`{lab}` ({yrs})" for lab, yrs in labels.items()),
                     len(labels), latest])
    tbl = pd.DataFrame(rows, columns=["Slug", "Label as published (years)", "Labels", "Proposed label (latest)"])
    changed = tbl[tbl["Labels"] > 1]
    facts["n_category_labels"] = df["category_original"].nunique()
    facts["category_label_changes"] = changed["Slug"].tolist()

    year_rows = []
    for y in YEARS:
        labs = df.loc[df["year"] == y, "category_original"].unique()
        year_rows.append([y, len(labs), ", ".join(sorted(labs))])
    return "\n\n".join([
        "## 4. Category labels per year",
        f"**{facts['n_category_labels']} distinct labels** for {df['category_slug'].nunique()} categories "
        f"(incl. Special Mention). {len(changed)} categories changed their label over the years: "
        + ", ".join(f"`{s}`" for s in changed["Slug"]) + ".",
        md_table(tbl),
        "### All labels per year",
        md_table(pd.DataFrame(year_rows, columns=["Year", "Labels", "Labels used"])),
        "Also note: within a year the same label is used on the ranking page, the band pages and the "
        "participant list, so the label is reliable per page; only the cross-year wording changes.",
    ])


# --------------------------------------------------------------------------------------------
# Section 5: rank formats (and number formats)
# --------------------------------------------------------------------------------------------

def classify_ranks(df: pd.DataFrame) -> pd.DataFrame:
    """One row per ranking-page row with `rank_raw` (the text that holds the rank) and `rank_format`.

    Formats: plain integer, tied integer (same number as another row in the same list),
    number + letter (21A), Rank Withdrawn, number in a 'Band' column (Innovation 2023), blank.
    """
    rk = df[df["page_type"] == "ranking"].copy()
    rk["rank_raw"] = rk["Rank"].where(rk["Rank"] != "", rk["Band"])
    rk["rank_col"] = rk.apply(lambda r: "Rank" if r["Rank"] != "" else ("Band" if r["Band"] else ""), axis=1)

    def fmt(r) -> str:
        v = r["rank_raw"].strip()
        if v == "":
            return "blank"
        if re.fullmatch(r"\d+", v):
            return "plain integer" if r["rank_col"] == "Rank" else "integer in a 'Band' column"
        if re.fullmatch(r"\d+[A-Za-z]", v):
            return "number + letter (e.g. 21A)"
        if "withdrawn" in v.lower():
            return "text 'Rank Withdrawn'"
        if re.fullmatch(r"\d+\s*-\s*\d+", v):
            return "band text inside Rank column"
        return "other text"

    rk["rank_format"] = rk.apply(fmt, axis=1)
    is_int = rk["rank_raw"].str.fullmatch(r"\d+")
    dup = rk[is_int].duplicated(["year", "category_slug", "rank_raw"], keep=False)
    rk.loc[dup[dup].index, "rank_format"] = rk.loc[dup[dup].index, "rank_format"].str.replace(
        "plain integer", "tied integer (shared rank)").str.replace(
        "integer in a 'Band' column", "integer in a 'Band' column (tied)")
    return rk


def section_ranks(df: pd.DataFrame, facts: dict) -> str:
    """Rank formats on ranking pages, band labels on band pages, rank-sequence and score checks."""
    rk = classify_ranks(df)
    out = ["## 5. Rank formats (and number formats)"]

    # 5a. format summary
    summ = []
    for f_, g in rk.groupby("rank_format"):
        where = g.groupby(["year", "category_slug"]).size()
        where_txt = ", ".join(f"{y} {c} ({n})" for (y, c), n in where.items()) if len(where) <= 12 \
            else f"{len(where)} category-years"
        examples = ", ".join(f"`{v}`" for v in g["rank_raw"].drop_duplicates().head(4))
        summ.append([f_, len(g), examples, where_txt])
    band = df[df["page_type"] == "band"]
    summ.append(["band label on a rank-band page (e.g. 101-150)", len(band),
                 ", ".join(f"`{b}`" for b in sorted(band["rank_band"].unique(),
                                                     key=lambda s: int(s.split("-")[0]))[:6]) + " …",
                 f"{band.groupby(['year', 'category_slug']).ngroups} category-years"])
    summ_tbl = pd.DataFrame(summ, columns=["Format", "Rows", "Examples", "Where (year category (rows))"])
    summ_tbl = summ_tbl.sort_values("Rows", ascending=False)
    out += ["### 5a. Every rank format found", md_table(summ_tbl)]

    special = rk[~rk["rank_format"].isin(["plain integer", "tied integer (shared rank)"])]
    sp_tbl = special[["year", "category_slug", "Name", "rank_raw", "Score", "rank_format", "row_note"]]
    out += ["Rows whose rank is not a plain number:", md_table(sp_tbl.rename(columns={
        "category_slug": "category", "rank_raw": "rank (raw)", "rank_format": "format", "row_note": "scraper note"}))]

    facts["n_rank_special"] = int((~rk["rank_format"].isin(
        ["plain integer", "tied integer (shared rank)", "integer in a 'Band' column",
         "integer in a 'Band' column (tied)"])).sum())
    facts["n_tied_rows"] = int(rk["rank_format"].str.contains("tied").sum())
    facts["n_rank_band_col"] = int(rk["rank_format"].str.contains("'Band' column").sum())

    # 5b. ties
    ties = (rk[rk["rank_format"].str.contains("tied")]
            .groupby(["year", "category_slug", "rank_raw"])["Name"].apply(lambda s: " / ".join(s)).reset_index())
    tied = rk[rk["rank_format"].str.contains("tied")]
    tie_scores = tied.groupby(["year", "category_slug", "rank_raw"])["Score"].nunique()
    tie_has_score = tied[tied["Score"] != ""].groupby(["year", "category_slug", "rank_raw"]).size()
    n_tie_unequal = int((tie_scores[tie_has_score.index] > 1).sum())
    ties["rank_raw"] = ties["rank_raw"].astype(int)
    ties = ties.sort_values(["year", "category_slug", "rank_raw"])
    facts["n_tie_groups"] = len(ties)
    facts["n_tie_unequal_scores"] = n_tie_unequal
    out += ["### 5b. Ties (two or more institutions with the same rank)",
            f"{len(ties)} tie groups, {facts['n_tied_rows']} rows. Ties are common because scores have only "
            "2 decimals. After a tie NIRF skips the next number (two at 100, next is 102): the usual "
            "\"competition ranking\" (1, 2, 2, 4). Check: tie groups (with scores) whose scores are NOT equal: "
            f"**{n_tie_unequal}**.",
            md_table(ties.rename(columns={"category_slug": "category", "rank_raw": "rank",
                                          "Name": "institutions sharing the rank"}))]

    # 5c. sequence check: with competition ranking, a number may only be missing right after a tie.
    seq_rows = []
    for (y, c), g in rk.groupby(["year", "category_slug"]):
        ints = g.loc[g["rank_raw"].str.fullmatch(r"\d+"), "rank_raw"].astype(int)
        if ints.empty:
            continue
        counts = ints.value_counts()
        tie_gaps = {r + k for r, n in counts.items() for k in range(1, n)}
        missing = sorted(set(range(1, ints.max() + 1)) - set(ints) - tie_gaps)
        n_a = int(g["rank_raw"].str.fullmatch(r"\d+[A-Za-z]").sum())
        n_wd = int(g["rank_raw"].str.contains("withdrawn", case=False).sum())
        if not missing and not n_a and not n_wd:
            continue
        if n_wd and len(missing) == n_wd:
            reason = "the 'Rank Withdrawn' row keeps its place, its number is not reused"
        elif n_a and len(missing) == n_a:
            reason = (f"not explained on the page; the count ({len(missing)}) equals the number of "
                      "'A' ranks in the same list")
        elif missing:
            reason = "not explained on the page"
        else:
            reason = "no number missing; 'A' rows sit between numbers"
        seq_rows.append([y, c, len(g), int(ints.max()), n_a, n_wd,
                         ", ".join(map(str, missing)) or "none", reason])
    seq = pd.DataFrame(seq_rows, columns=["year", "category", "rows", "max rank", "'A' ranks",
                                          "withdrawn", "missing rank numbers (not from ties)", "observation"])
    n_lists = rk.groupby(["year", "category_slug"]).ngroups
    facts["n_seq_issues"] = len(seq)
    facts["seq_missing"] = "; ".join(f"{r[0]} {r[1]}: {r[6]}" for r in seq_rows if r[6] != "none")
    out += ["### 5c. Rank sequence check",
            "Rule: in competition ranking a rank number may only be missing right after a tie "
            f"(two at 21 → no 22). {n_lists - len(seq)} of {n_lists} ranked lists follow this exactly. "
            "The others:",
            md_table(seq) if len(seq) else "_All lists pass._"]

    # 5d. bands
    b = band.groupby(["year", "category_slug", "rank_band"]).size().reset_index(name="rows")
    b["width"] = b["rank_band"].apply(lambda s: int(s.split("-")[1]) - int(s.split("-")[0]) + 1)
    b["note"] = b.apply(lambda r: "" if r["rows"] == r["width"] else
                        ("fewer rows than places" if r["rows"] < r["width"] else "more rows than places"), axis=1)
    odd_b = b[(b["note"] != "") | b["rank_band"].str.match(r"10[2-9]-")]
    labels = band.groupby("rank_band")["year"].apply(fmt_years).reset_index()
    labels["_k"] = labels["rank_band"].apply(lambda s: int(s.split("-")[0]))
    out += ["### 5d. Rank bands",
            "All band labels found (they come from the band page heading, never from a rank cell):",
            md_table(labels.sort_values("_k")[["rank_band", "year"]].rename(
                columns={"rank_band": "Band label", "year": "Years"})),
            "Bands whose row count differs from the band width, or that start at 102 because of a tie "
            "at 100 (a band is a list of names in alphabetical order, so a band of 50 places can hold 49 or "
            "51 names when ranks are tied or withdrawn):",
            md_table(odd_b.rename(columns={"category_slug": "category", "rank_band": "band"}))]
    facts["n_odd_bands"] = len(odd_b)

    # 5e. number formats
    nums = []
    for col in SCORE_COLUMNS + PARAM_RANK_COLUMNS:
        if col not in rk.columns:
            continue
        v = rk[col]
        v = v[v != ""]
        if v.empty:
            continue
        numeric = pd.to_numeric(v, errors="coerce")
        non_num = v[numeric.isna()]
        dec = v[numeric.notna()].str.extract(r"\.(\d+)$")[0].str.len().fillna(0).astype(int)
        nums.append([f"`{col}`", len(v), len(non_num),
                     ", ".join(f"`{x}`" for x in non_num.unique()[:3]),
                     f"{numeric.min():g} – {numeric.max():g}",
                     ", ".join(f"{k} dp: {n}" for k, n in dec.value_counts().sort_index().items())])
    nums_tbl = pd.DataFrame(nums, columns=["Column", "Non-blank", "Not a number", "Examples",
                                           "Min – max", "Decimal places"])
    facts["score_out_of_range"] = int(sum(
        ((pd.to_numeric(rk[c], errors="coerce") > 100) | (pd.to_numeric(rk[c], errors="coerce") < 0)).sum()
        for c in SCORE_COLUMNS if c in rk.columns))

    # Score must fall as rank gets worse.
    inv_rows = []
    for (y, c), g in rk.groupby(["year", "category_slug"]):
        g = g[g["rank_raw"].str.fullmatch(r"\d+") & (g["Score"] != "")]
        if g.empty:
            continue
        g = g.assign(r=g["rank_raw"].astype(int), s=g["Score"].astype(float)).sort_values(["r", "s"],
                                                                                         ascending=[True, False])
        bad = g[g["s"].diff() > 0]
        for _, row in bad.iterrows():
            prev = g[g["r"] < row["r"]].iloc[-1]
            inv_rows.append([y, c, f"{prev['r']} ({prev['s']:.2f})", f"{row['r']} ({row['s']:.2f})", row["Name"]])
    facts["n_score_inversions"] = len(inv_rows)
    out += ["### 5e. Score and parameter number formats",
            "Scores and parameters on ranking pages (text in the raw files, to be converted to numbers):",
            md_table(nums_tbl),
            f"Scores or parameters outside 0–100: **{facts['score_out_of_range']}**. "
            "Parameter ranks (`*_rank`) go above 100 because they rank all evaluated institutions, not only "
            "the published list.",
            f"**Score order check:** a better (smaller) rank should never have a lower score. "
            f"Violations: **{len(inv_rows)}**."]
    if inv_rows:
        out.append(md_table(pd.DataFrame(inv_rows, columns=["year", "category", "rank above (score)",
                                                            "rank below (score)", "institution below"])))
    return "\n\n".join(out)


# --------------------------------------------------------------------------------------------
# Section 6: missing values
# --------------------------------------------------------------------------------------------

def section_missing(df: pd.DataFrame, facts: dict) -> str:
    """Blank cells per column per year, counted only in files that HAVE that column.

    "n/a" = no file of that page type has the column in that year (a structural gap, e.g.
    Research has no TLR), which is different from a blank cell in a column that exists.
    """
    out = ["## 6. Missing values per column per year",
           "Cell = blank cells / rows, counted only over files that have the column. `n/a` = the column "
           "does not exist on any page of that type that year (not missing data, just not published)."]
    detail = []
    for ptype in ["ranking", "band", "participants"]:
        sub = df[df["page_type"] == ptype]
        cols = []
        for cs in sub["_cols"].unique():
            for c in cs.split("|"):
                if c not in cols and c not in META_COLUMNS:
                    cols.append(c)
        rows = []
        for c in cols:
            row = [f"`{c}`"]
            for y in YEARS:
                sy = sub[sub["year"] == y]
                has = sy[sy["_cols"].str.split("|").apply(lambda l: c in l)]
                if sy.empty:
                    row.append("")
                elif has.empty:
                    row.append("n/a")
                else:
                    blanks = int((has[c].str.strip() == "").sum())
                    row.append(f"**{blanks}**/{len(has)}" if blanks else f"0/{len(has)}")
                    if blanks:
                        for cat, n in has[has[c].str.strip() == ""].groupby("category_slug").size().items():
                            detail.append([ptype, y, cat, c, n, int((has["category_slug"] == cat).sum())])
            rows.append(row)
        out += [f"### Page type `{ptype}`", md_table(pd.DataFrame(rows, columns=["Column"] + YEARS))]

    det = pd.DataFrame(detail, columns=["page type", "year", "category", "column", "blank", "rows"])
    det["why"] = det.apply(_missing_reason, axis=1).replace("", "real blank cell on the site")
    facts["n_missing_cells"] = int(det["blank"].sum())
    facts["n_missing_unexplained"] = int(det.loc[det["why"] == "real blank cell on the site", "blank"].sum())
    grouped = (det.groupby(["page type", "category", "why"])
                  .agg(columns=("column", lambda s: ", ".join(f"`{c}`" for c in dict.fromkeys(s))),
                       years=("year", fmt_years), blank_cells=("blank", "sum"))
                  .reset_index().sort_values(["page type", "blank_cells"], ascending=[False, False]))
    out += ["### Where the blanks are, and why",
            f"{facts['n_missing_cells']:,} blank cells in columns that exist. Only "
            f"**{facts['n_missing_unexplained']}** are real gaps; all others are structural "
            "(the category does not publish that value).",
            md_table(grouped.rename(columns={"blank_cells": "blank cells", "why": "reason"}))]
    return "\n\n".join(out)


def _missing_reason(r) -> str:
    """Plain-English reason for a block of blank cells, where we know it from docs/source_map.md."""
    if r["category"] == "research" and r["column"] in ("tlr", "rpc", "go"):
        return "Research uses QNR/QLR/SFC instead"
    if r["category"] in ("innovation", "open_university", "skill_university", "sdg_institutions") \
            and r["column"] in ("Score", "tlr", "rpc", "go", "oi", "pr"):
        return "rank-only category, no scores published"
    if r["column"] in ("Rank",) and r["category"] == "innovation" and r["year"] == 2023:
        return "rank is in the 'Band' column"
    if r["column"] in ("Score", "tlr", "rpc", "go", "oi", "pr") and r["year"] == 2025 and r["category"] == "dental":
        return "'Rank Withdrawn*' row"
    if r["column"].endswith("_rank") and r["blank"] == r["rows"]:
        return "parameter tabs not published"
    return ""


# --------------------------------------------------------------------------------------------
# Section 7: duplicates
# --------------------------------------------------------------------------------------------

def section_duplicates(df: pd.DataFrame, facts: dict) -> str:
    """Exact duplicate rows, and the same institution twice in one (year, category) list.

    Checks, in order of strictness:
      - exact: every data column identical (ignoring the download time and file name)
      - same Institute ID twice in one ranking list
      - same Name twice in one list, then same normalised name, then whether the City differs
        (same name + different city = two different campuses, not a duplicate)
      - an institution both on the exact-rank page and on a band page of the same category-year
    """
    data_cols = [c for c in df.columns if c not in ("_file", "_cols", "scraped_at")]
    exact = df[df.duplicated(data_cols, keep=False)]
    facts["n_exact_dupes"] = int(df.duplicated(data_cols).sum())

    rows = []
    rk = df[df["page_type"] == "ranking"]
    idd = rk[(rk["Institute ID"] != "") & rk.duplicated(["year", "category_slug", "Institute ID"], keep=False)]
    rows.append(["Same Institute ID twice in one ranking list", len(idd),
                 "; ".join(f"{r.year} {r.category_slug}: {r.Name}" for r in idd.head(6).itertuples())])

    lists = {"ranked (exact + band)": ranked_rows(df), "participants": df[df["page_type"] == "participants"]}
    dupe_examples = []
    for label, sub in lists.items():
        sub = sub.assign(nkey=sub["Name"].map(norm_name), ckey=sub["City"].map(norm_name))
        d_name = sub[sub.duplicated(["year", "category_slug", "Name"], keep=False)]
        d_norm = sub[sub.duplicated(["year", "category_slug", "nkey"], keep=False)]
        d_city = sub[sub.duplicated(["year", "category_slug", "nkey", "ckey"], keep=False)]
        d_full = sub[sub.duplicated(["year", "category_slug", "nkey", "ckey", "State"], keep=False)]
        rows.append([f"{label}: same Name twice in one year-category", len(d_name), ""])
        rows.append([f"{label}: same name after normalising case/punctuation", len(d_norm), ""])
        rows.append([f"{label}: same name AND same city", len(d_city), ""])
        rows.append([f"{label}: same name, city AND state (true duplicate)", len(d_full),
                     "; ".join(sorted({f"{r.year} {r.category_slug}: {r.Name}, {r.City}"
                                       for r in d_full.itertuples()})[:6])])
        facts[f"dupe_{label.split()[0]}_name"] = len(d_name)
        facts[f"dupe_{label.split()[0]}_true"] = len(d_full)
        diff_city = d_norm[~d_norm.index.isin(d_city.index)]
        for (y, c, k), g in diff_city.groupby(["year", "category_slug", "nkey"]):
            if len(dupe_examples) < 12:
                dupe_examples.append([label, y, c, g["Name"].iloc[0], " / ".join(g["City"] + ", " + g["State"])])

    both, both_name_only = [], 0
    rb = ranked_rows(df).assign(nkey=lambda x: x["Name"].map(norm_name) + " | " + x["City"].map(norm_name))
    for (y, c), g in rb.groupby(["year", "category_slug"]):
        inter = set(g.loc[g["page_type"] == "ranking", "nkey"]) & set(g.loc[g["page_type"] == "band", "nkey"])
        both += [[y, c, k] for k in inter]
        names = g["nkey"].str.split(" | ", regex=False).str[0]
        both_name_only += len(set(names[g["page_type"] == "ranking"]) & set(names[g["page_type"] == "band"]))
    rows.append(["Same name on the exact-rank page AND a band page (same year-category)", both_name_only,
                 "all are same-name institutions in different cities (see table below)" if not both else ""])
    rows.append(["… same name AND same city on both pages", len(both),
                 "; ".join(f"{y} {c}: {k}" for y, c, k in both[:6])])
    facts["n_rank_and_band"] = len(both)

    # Same institution in several categories of the same year (expected, not a duplicate).
    rk2 = rk.assign(code=rk["Institute ID"].map(id_code))
    multi_cat = rk2[rk2["code"] != ""].groupby(["year", "code"])["category_slug"].nunique()
    facts["n_multi_category"] = int((multi_cat > 1).sum())

    out = ["## 7. Duplicates",
           f"**Exact duplicate rows** (all columns identical except download time): **{facts['n_exact_dupes']}** "
           "extra copies."]
    if len(exact):
        grp = (exact.groupby(["year", "category_slug", "page_type", "Name", "City", "State"])
               .size().reset_index(name="copies"))
        facts["exact_dupe_pages"] = ", ".join(sorted(grp["page_type"].unique()))
        out += [f"All of them are on `{facts['exact_dupe_pages']}` pages. These lists have no ID, and the "
                "City cell often holds a district, so several copies of e.g. \"Government Degree College, "
                "Srikakulam\" may be **different colleges in the same district**, not a scraping error. "
                "They only matter for participation counts.",
                md_table(grp)]
    out += ["### Duplicate (year, category, institute) rows",
            md_table(pd.DataFrame(rows, columns=["Check", "Rows", "Examples"]))]
    if dupe_examples:
        out += ["Same name, different city (different campuses or branches that share a name; "
                "**not** duplicates, so the institution key must include city/state):",
                md_table(pd.DataFrame(dupe_examples, columns=["list", "year", "category", "name", "cities"]))]
    out.append(
        f"**Expected repeats, not duplicates:** {facts['n_multi_category']} (year, institution) pairs appear in "
        "more than one category of the same year (e.g. IIT Madras in Overall, Engineering, Research, Innovation …), "
        "and the participant lists repeat the ranked institutions. The master-table key is therefore "
        "(year, category, institution), never (year, institution).")
    return "\n\n".join(out)


# --------------------------------------------------------------------------------------------
# Section 8: names that differ across years
# --------------------------------------------------------------------------------------------

def diff_type(a: str, b: str) -> str:
    """What kind of difference separates two spellings of a name."""
    if a.lower() == b.lower():
        return "letter case only"
    if re.sub(r"[^a-z0-9&]", "", a.lower()) == re.sub(r"[^a-z0-9&]", "", b.lower()):
        return "punctuation / spacing only"
    if norm_name(a) == norm_name(b):
        return "'&' vs 'and' (+ punctuation)"
    ta, tb = Counter(norm_name(a).split()), Counter(norm_name(b).split())
    if ta < tb or tb < ta:
        return "word(s) added or dropped (city, campus, legal form)"
    return "spelling / wording"


def section_names(df: pd.DataFrame, facts: dict) -> str:
    """Find spellings of the same institution that differ between years.

    Method (plain words):
      1. Take every distinct Name on ranking and band pages, with the years, states and
         ID codes it appears with.
      2. Compare every pair of names with rapidfuzz `token_sort_ratio` (0-100: how many character
         edits separate the two names after sorting their words) on the normalised names.
      3. Keep pairs with score >= FUZZY_THRESHOLD, in the same state, that appear in different years
         and never side by side in the same list (two names in one list are two institutions).
      4. Use the ID code (stable from 2018) as ground truth: same code = confirmed same institution,
         different code = a trap that fuzzy matching alone would merge wrongly.
    """
    rb = ranked_rows(df).copy()
    rb["code"] = rb["Institute ID"].map(id_code)
    rb["skey"] = rb["State"].map(lambda s: proposed_state(s) or s)
    info = {}
    for name, g in rb.groupby("Name"):
        info[name] = {
            "years": set(g["year"]), "states": set(g["skey"]), "codes": set(g["code"]) - {""},
            "lists": set(zip(g["year"], g["category_slug"])), "n": len(g),
        }
    names = list(info)
    keys = [norm_name(n) for n in names]
    facts["n_distinct_names"] = len(names)
    facts["n_distinct_norm"] = len(set(keys))

    # Ground truth from ID codes: one code, several spellings.
    code_names = defaultdict(set)
    for r in rb[rb["code"] != ""].itertuples():
        code_names[r.code].add(r.Name)
    multi = {c: ns for c, ns in code_names.items() if len(ns) > 1}
    facts["n_codes"] = len(code_names)
    facts["n_codes_multi_names"] = len(multi)
    facts["n_codes_multi_norm"] = sum(1 for ns in multi.values() if len({norm_name(n) for n in ns}) > 1)
    by_type = defaultdict(int)
    for ns in multi.values():
        ns = sorted(ns)
        for b in ns[1:]:
            by_type[diff_type(ns[0], b)] += 1

    # Fuzzy pairs.
    scores = process.cdist(keys, keys, scorer=fuzz.token_sort_ratio, score_cutoff=FUZZY_THRESHOLD,
                           dtype="uint8", workers=-1)
    pairs = []
    ii, jj = scores.nonzero()
    for i, j in zip(ii, jj):
        if i >= j:
            continue
        a, b = names[i], names[j]
        A, B = info[a], info[b]
        if not (A["states"] & B["states"]) or (A["lists"] & B["lists"]):
            continue
        if A["years"] == B["years"] and len(A["years"]) == 1:
            continue
        if A["codes"] and B["codes"]:
            evidence = "same ID code" if A["codes"] & B["codes"] else "DIFFERENT ID code"
        else:
            evidence = "no ID to confirm (2017 or band page)"
        pairs.append({"a": a, "b": b, "score": int(scores[i, j]), "evidence": evidence,
                      "type": diff_type(a, b), "years_a": fmt_years(A["years"]),
                      "years_b": fmt_years(B["years"]), "weight": A["n"] + B["n"]})
    pairs = pd.DataFrame(pairs)
    facts["n_fuzzy_pairs"] = len(pairs)
    facts["n_fuzzy_traps"] = int((pairs["evidence"] == "DIFFERENT ID code").sum()) if len(pairs) else 0
    facts["n_fuzzy_confirmed"] = int((pairs["evidence"] == "same ID code").sum()) if len(pairs) else 0

    # 30 examples: good matches only, spread over the kinds of difference, most-seen institutions first.
    good = pairs[pairs["evidence"] != "DIFFERENT ID code"].sort_values(["weight", "score"], ascending=False)
    picked, buckets = [], {t: g for t, g in good.groupby("type")}
    order = ["word(s) added or dropped (city, campus, legal form)", "'&' vs 'and' (+ punctuation)",
             "punctuation / spacing only", "letter case only", "spelling / wording"]
    pos = {t: 0 for t in buckets}
    while len(picked) < N_EXAMPLES and any(pos[t] < len(buckets[t]) for t in buckets):
        for t in order:
            if t in buckets and pos[t] < len(buckets[t]) and len(picked) < N_EXAMPLES:
                picked.append(buckets[t].iloc[pos[t]])
                pos[t] += 1
    ex = pd.DataFrame(picked).reset_index(drop=True)
    ex.index += 1
    ex_tbl = ex.assign(A=ex["a"] + " (" + ex["years_a"] + ")", B=ex["b"] + " (" + ex["years_b"] + ")")[
        ["A", "B", "score", "type", "evidence"]].rename(
        columns={"A": "Spelling A (years)", "B": "Spelling B (years)", "score": "Similarity",
                 "type": "Difference", "evidence": "Confirmed by"})

    def where(name: str) -> str:
        g = rb[rb["Name"] == name]
        return f"{', '.join(sorted(set(g['code']) - {''})) or 'no ID'}; {g['City'].iloc[-1]}; {fmt_years(g['year'])}"

    traps = pairs[pairs["evidence"] == "DIFFERENT ID code"].sort_values("score", ascending=False).head(12)
    trap_tbl = pd.DataFrame([[r.a, where(r.a), r.b, where(r.b), r.score] for r in traps.itertuples()],
                            columns=["Name A", "A: ID code; city; years", "Name B", "B: ID code; city; years",
                                     "Similarity"])

    # Per ID code: the spellings used, with the years of each (code, spelling) pair.
    coded = rb[rb["code"] != ""].assign(nkey=lambda x: x["Name"].map(norm_name))
    renames, shared_code = [], []
    for code, g in coded.groupby("code"):
        if g["nkey"].nunique() < 2:
            continue
        spell = g.groupby("Name")["year"].agg(lambda s: fmt_years(s))
        spell = spell.loc[sorted(spell.index, key=lambda n: g.loc[g["Name"] == n, "year"].min())]
        keys = g["nkey"].unique()
        lo = min(fuzz.token_sort_ratio(x, y) for x in keys for y in keys if x < y)
        # Two clearly different names under one code in the SAME year = one code, several units.
        # "Clearly different" = not similar AND neither name is the other plus extra words (a city suffix).
        def different(x: str, y: str) -> bool:
            cx, cy = Counter(x.split()), Counter(y.split())
            return fuzz.token_sort_ratio(x, y) < FUZZY_THRESHOLD and not (cx <= cy or cy <= cx)
        same_year = any(different(x, y) for ks in g.groupby("year")["nkey"].unique()
                        for x in ks for y in ks if x < y)
        row = [code, " → ".join(f"{n} ({ys})" for n, ys in spell.items()), int(lo)]
        if same_year:
            cats = g.groupby("Name")["category_slug"].agg(lambda s: ", ".join(sorted(set(s))))
            shared_code.append([code, "; ".join(f"{n} [{cats[n]}]" for n in spell.index)])
        elif lo < FUZZY_THRESHOLD:
            renames.append(row)
    renames.sort(key=lambda r: r[2])
    facts["n_renames"] = len(renames)
    facts["n_shared_codes"] = len(shared_code)

    # One normalised name, several ID codes (different campuses that share a name).
    name_codes = coded.groupby("nkey").agg(codes=("code", lambda s: sorted(set(s))), name=("Name", "last"),
                                           cities=("City", lambda s: ", ".join(dict.fromkeys(s))))
    shared_name = name_codes[name_codes["codes"].apply(len) > 1]
    facts["n_shared_names"] = len(shared_name)
    shared_name_tbl = shared_name.assign(codes=shared_name["codes"].apply(", ".join))[
        ["name", "codes", "cities"]].head(15).rename(columns={"name": "Name", "codes": "ID codes", "cities": "Cities"})

    # Same year, same category: does the participant list spell ranked names the same way?
    part = df[df["page_type"] == "participants"]
    cross = []
    for y in YEARS:
        r_y, p_y = rb[rb["year"] == y], part[part["year"] == y]
        if p_y.empty:
            continue
        n_tot = n_exact = n_norm = 0
        for c, g in r_y.groupby("category_slug"):
            pc = p_y[p_y["category_slug"] == c]
            if pc.empty:
                continue
            p_exact, p_norm = set(pc["Name"]), set(pc["Name"].map(norm_name))
            n_tot += len(g)
            n_exact += int(g["Name"].isin(p_exact).sum())
            n_norm += int(g["Name"].map(norm_name).isin(p_norm).sum())
        if n_tot:
            cross.append([y, n_tot, f"{n_exact} ({n_exact / n_tot:.0%})", f"{n_norm} ({n_norm / n_tot:.0%})"])
    cross_tbl = pd.DataFrame(cross, columns=["Year", "Ranked rows (categories with a list)",
                                             "Found in participant list: exact name",
                                             "… after normalising case/punctuation"])

    upper = df[df["Name"].str.fullmatch(r"[^a-z]+") & df["Name"].str.contains(r"[A-Z]{4}")]
    bad_enc = df[df["Name"].str.contains("\ufffd") | df["City"].str.contains("\ufffd|\\?")]
    trail = df[df["Name"].str.contains(r"[,.;:]\s*$")]
    facts["n_upper_names"] = len(upper)
    facts["n_bad_encoding"] = len(bad_enc)
    facts["n_trailing_punct"] = len(trail)

    type_tbl = pd.DataFrame(sorted(by_type.items(), key=lambda kv: -kv[1]), columns=["Kind of difference", "Pairs"])
    return "\n\n".join([
        "## 8. Institution names that differ across years",
        f"Ranking + band pages hold **{facts['n_distinct_names']:,} distinct name strings**; normalising case, "
        f"'&'/'and' and punctuation alone brings this down to **{facts['n_distinct_norm']:,}**.",
        f"**Ground truth from ID codes (2018-2025):** {facts['n_codes']:,} institutions have an ID code; "
        f"**{facts['n_codes_multi_names']}** of them appear under more than one spelling, and "
        f"{facts['n_codes_multi_norm']} still differ after normalising. Kinds of difference "
        "(each spelling compared with the first one alphabetically):",
        md_table(type_tbl),
        "### 8a. 30 examples (found with rapidfuzz)",
        f"Method: every pair of distinct names compared with `rapidfuzz.fuzz.token_sort_ratio` on normalised "
        f"names; kept if similarity ≥ {FUZZY_THRESHOLD}, same state, different years, never in the same list. "
        f"This finds **{facts['n_fuzzy_pairs']} candidate pairs**: {facts['n_fuzzy_confirmed']} confirmed by the "
        f"same ID code, {facts['n_fuzzy_traps']} contradicted by different ID codes (see 8b), the rest "
        "cannot be checked by ID (2017 or band pages). Examples are spread over the kinds of difference, "
        "most frequently ranked institutions first.",
        md_table(ex_tbl, index=True),
        "### 8b. Traps: similar names, different ID codes",
        "High similarity and same state, but different ID codes. Some are truly different institutions "
        "(Jammu vs Kashmir campus; a generic name vs one IIM); others look like the same institution "
        "registered under a new ID. A fuzzy score alone cannot tell these apart, so every match without "
        "ID evidence must be hand-checked:",
        md_table(trap_tbl) if len(trap_tbl) else "_None found._",
        "### 8c. Renames that fuzzy matching cannot find",
        f"Same ID code, one name per year, but the spellings are less than {FUZZY_THRESHOLD}% similar "
        f"(**{facts['n_renames']} institutions**, the 15 least similar shown). Only the ID code links these; "
        "for 2017 they need a hand-made alias entry.",
        md_table(pd.DataFrame(renames[:15], columns=["ID code", "Spellings (years)", "Lowest similarity"]))
        if renames else "_None found._",
        "### 8f. One ID code, several different institutions in the same year",
        f"**{facts['n_shared_codes']} ID code(s)** carry clearly different names in the same year, usually a "
        "university and its constituent school ranked in a subject category. So the ID code identifies the "
        "*registered parent*, not always the unit that was ranked: the cleaned key must be "
        "(ID code + name) where this happens.",
        md_table(pd.DataFrame(shared_code, columns=["ID code", "Names [categories]"])) if shared_code
        else "_None found._",
        "### 8g. One name, several ID codes",
        f"**{facts['n_shared_names']} normalised names** belong to more than one ID code. Mostly different "
        "campuses that publish the same name (the name alone is not a key; city/state or ID is needed). "
        "A few look like one institution that got a new code after a change of status (e.g. COEP Pune: "
        "college code `C-41593`, then university code `U-1257`), so a code can also change over time.",
        md_table(shared_name_tbl) if len(shared_name_tbl) else "_None found._",
        "### 8d. Same year, same category, two pages spell names differently",
        "Share of ranked institutions whose exact name is found in that year's participant list for the "
        "same category:",
        md_table(cross_tbl),
        "### 8e. Other name-format issues",
        f"- Names written fully in UPPER CASE: **{facts['n_upper_names']}** rows "
        "(Innovation 2023 page, and many entries in participant lists).\n"
        f"- Broken characters (`�`, `?` where an apostrophe or accent was): **{facts['n_bad_encoding']}** rows "
        "(e.g. `St. Joseph�s College`).\n"
        f"- Names ending in a comma or full stop: **{facts['n_trailing_punct']}** rows.\n"
        "- 2017 IDs (`IR17-…`) use a different scheme and cannot be linked to 2018+ IDs; "
        "2017 must be linked by name + state.",
    ])


# --------------------------------------------------------------------------------------------
# Section 9: ranked cleaning problems
# --------------------------------------------------------------------------------------------

def section_problems(facts: dict) -> str:
    """The cleaning problems found above, most important first, each with a proposed fix.

    Importance = how badly the problem would break the 40 Annexure A questions if left alone
    (wrong trends / wrong counts first, cosmetic last).
    """
    p = [
        ("High", "Institution identity across years",
         f"{facts['n_codes_multi_names']} institutions (by ID code) have 2+ spellings; "
         f"{facts['n_renames']} renames are not even similar (UPES, Krea, IMI …); 2017 IDs cannot be linked; "
         f"{facts['n_fuzzy_traps']} similar-looking pairs have different codes; {facts['n_shared_names']} names "
         f"belong to 2+ codes; {facts['n_shared_codes']} code(s) cover several units in one year (Amrita).",
         "Build `institution_id` from the ID code (e.g. `U-0456`) for 2018+. Link 2017, band and participant "
         "rows by normalised name + state (+ city) with rapidfuzz; write every proposed link to "
         "`data/mappings/institution_aliases.csv` with its score and hand-check it. Split shared codes by name; "
         "merge known code changes (COEP) by hand. Display name = latest official spelling."),
        ("High", "Banded institutions have no exact rank, score, ID or parameters",
         f"{facts['n_band_rows']:,} band rows.",
         "Keep them as rows with `rank = NaN`, `rank_band = '101-150'`, `band_low = 101`, `band_high = 150`, "
         "`rank_type = 'band'`. Never invent an exact rank (no mid-point). Use bands only in band/transition charts."),
        ("High", "Non-numeric ranks",
         f"{facts['n_rank_special']} rows: `21A`, `26A`, `16A` (2018), `Rank Withdrawn` (2018 College), "
         "`Rank Withdrawn*` (2025 Dental). Rank numbers missing without a tie: "
         f"{facts['seq_missing']}.",
         "Keep the original in `rank_raw`. Withdrawn → `rank = NaN`, `rank_status = 'withdrawn'` (ignore the "
         "hidden '18'). 'A' ranks → `rank = NaN` + flag until the 2018 report confirms their meaning; ask the team."),
        ("High", "Ties and shifted bands",
         f"{facts['n_tie_groups']} tie groups ({facts['n_tied_rows']} rows); bands like `102-150`, `102-125`.",
         "Keep tied ranks as published (competition ranking). Read band limits from the label, never assume "
         "101-150. Row count ≠ last rank, so 'top N' means `rank <= N`, not 'first N rows'."),
        ("High", "Category labels change over the years",
         f"{facts['n_category_labels']} labels for {facts['n_categories'] + 1} slugs; label changes in "
         + ", ".join(facts["category_label_changes"]) + ".",
         "Add `category` (one standard label per slug, via `data/mappings/categories.csv`) and keep "
         "`category_original` exactly as published, for honest historical comparison."),
        ("High", "Participant lists mixed with rankings",
         f"{facts['n_participant_rows']:,} participant rows vs {facts['n_ranked_rows'] + facts['n_band_rows']:,} "
         "ranked rows; the lists overlap.",
         "Put participants in a separate table (`nirf_participants.parquet`, used only for participation "
         "counts). The master table holds ranking + band rows only. 2018 Special Mention → a small notes table."),
        ("Medium", "State spelling variants",
         f"{facts['n_state_values']} raw values for {facts['n_state_official']} states/UTs; "
         f"{facts['n_state_nonofficial_rows']} rows not official (`Jammu & Kashmir`, `UTTAR PRADESH`, "
         "`Pondicherry`, `Andaman & Nicobar` …).",
         "`data/mappings/states.csv`: raw → official name (keep `state_original`). Pondicherry → Puducherry; "
         "Dadra and Nagar Haveli / Daman and Diu → the merged UT (for the map), with a note."),
        ("Medium", "Different parameter sets per category",
         "Research uses QNR/QLR/SFC; Innovation, Open, Skill, SDG publish no scores; parameter ranks only "
         "in 2017-2018 and University 2019+.",
         "Keep `qnr/qlr/sfc` separate from `tlr/rpc/go`; mark `has_scores` per category; never plot "
         "categories with different parameters in one chart without a visible note."),
        ("Medium", "Everything is text",
         "Scores, parameters, ranks and years are strings in the raw CSVs.",
         "Convert: year → int, rank → nullable int, Score and parameters → float (2 dp). Check 0 ≤ score ≤ 100 "
         f"(currently {facts['score_out_of_range']} out of range) and that a better rank never has a lower score "
         f"(currently {facts['n_score_inversions']} violations)."),
        ("Medium", "Same name, different institution",
         "Several colleges/branches share a name and differ only by city (see section 7).",
         "Matching key = normalised name + state (+ city when the name repeats); never name alone."),
        ("Low", "Innovation 2023 format",
         f"{facts['n_rank_band_col']} rows: rank in a column called `Band`, no City, names and states in "
         "UPPER CASE, ARIIA-style IDs (`ARI-U-0456`).",
         "Move `Band` into `rank`; leave City blank; use the ID code (which matches later years) to "
         "get the normal spelling."),
        ("Low", "Letter case, punctuation and broken characters in names",
         f"{facts['n_upper_names']} UPPER CASE names, {facts['n_bad_encoding']} rows with broken characters, "
         f"{facts['n_trailing_punct']} names ending in `,` or `.`.",
         "Strip trailing punctuation and extra spaces; fix the few broken characters by hand in the alias "
         "table; use the normalised key only for matching, not for display."),
        ("Low", "Messy City values",
         "City sometimes holds taluka/district/PIN text (`Adipur, Taluka- Gandhidham, Pin : 370205`), "
         "upper case, or is blank.",
         "Light clean (title case, drop PIN and 'Ta:/Dist:' prefixes) for display only; City is never used "
         "as an analysis dimension."),
        ("Low", "Duplicates",
         f"{facts['n_exact_dupes']} exact duplicate rows, all in participant lists (may be different colleges "
         f"in one district); {facts['dupe_ranked_true']} true duplicates in ranked lists; "
         f"{facts['n_rank_and_band']} institutions both ranked and banded in one list.",
         "Ranked lists: nothing to drop. Participant lists: count distinct (name, city, state) and log the "
         "repeats instead of silently deleting. Re-check after name standardising."),
    ]
    tbl = pd.DataFrame(p, columns=["Severity", "Problem", "Evidence (from this audit)", "Proposed fix"])
    tbl.index += 1
    return "\n\n".join([
        "## 9. Cleaning problems, most important first",
        "Ranked by how badly each would break the 40 Annexure A questions if left alone: wrong identities, "
        "ranks and categories first (they corrupt every trend), cosmetic issues last.",
        md_table(tbl, index=True).replace("| index |", "| # |", 1),
        "**Decisions needed from the team:** (1) the meaning of `21A / 26A / 16A` in 2018; "
        "(2) whether to map the old UTs Dadra and Nagar Haveli / Daman and Diu to the merged UT; "
        "(3) sign-off on the hand-checked alias table before it is used.",
    ])


# --------------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------------

def build_report(df: pd.DataFrame) -> tuple[str, dict]:
    facts: dict = {}
    sections = [
        section_rows(df, facts),
        section_columns(df, facts),
        section_states(df, facts),
        section_categories(df, facts),
        section_ranks(df, facts),
        section_missing(df, facts),
        section_duplicates(df, facts),
        section_names(df, facts),
        section_problems(facts),
    ]
    header = "\n\n".join([
        "# NIRF raw data audit",
        f"Generated by `python -m pipeline.audit` on {date.today():%d %B %Y} from the raw CSVs in "
        "`data/raw/csv/` (read-only: no raw file is changed). Re-run after any new scrape.",
        "Purpose: list every inconsistency **before** cleaning, so each cleaning rule in `pipeline/` "
        "is based on evidence. Sections 1-8 are the checks; section 9 ranks the problems and proposes fixes.",
        "Contents: [1 Rows](#1-rows-per-year--category) · [2 Columns](#2-column-names-per-year) · "
        "[3 States](#3-state-values) · [4 Categories](#4-category-labels-per-year) · "
        "[5 Ranks](#5-rank-formats-and-number-formats) · [6 Missing](#6-missing-values-per-column-per-year) · "
        "[7 Duplicates](#7-duplicates) · [8 Names](#8-institution-names-that-differ-across-years) · "
        "[9 Problems](#9-cleaning-problems-most-important-first)",
    ])
    return header + "\n\n" + "\n\n".join(sections) + "\n", facts


def main() -> None:
    df = load_raw()
    report, facts = build_report(df)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"Wrote {REPORT_PATH.relative_to(ROOT)} ({len(report.splitlines())} lines)")
    for k, v in facts.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
