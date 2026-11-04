"""Validation tests (Phase 5): does the master table keep every promise we make about the data?

Each test checks the cleaned table against something OUTSIDE the cleaning code, so a pipeline bug
cannot hide itself: the official list of India's states and UTs (typed here, not read from our own
mapping file), the year x category table in docs/source_map.md, and the raw CSVs + scrape log.

    python -m pipeline.clean
    python -m pytest tests/test_data.py -v
"""

import re
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "data" / "processed" / "nirf_master.parquet"
DUPLICATE_LOG = ROOT / "data" / "processed" / "dropped_duplicates.csv"
RAW_CSV_DIR = ROOT / "data" / "raw" / "csv"
SCRAPE_LOG = ROOT / "data" / "raw" / "scrape_log.csv"
CATEGORY_MAP = ROOT / "data" / "mappings" / "category_map.csv"
SOURCE_MAP = ROOT / "docs" / "source_map.md"

YEARS = list(range(2017, 2026))
SCORE_COLUMNS = ["score", "tlr", "rpc", "go", "oi", "pr"]

# Scores are printed with 2 decimals, so a gap of 0.01 or less is rounding, not a real inversion.
SCORE_TOLERANCE = 0.01

# India's 28 states and 8 union territories, official names (Ministry of Home Affairs, 2020 onwards).
STATES = {
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat",
    "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh",
    "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan",
    "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
}
UNION_TERRITORIES = {
    "Andaman and Nicobar Islands", "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi", "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
}


@pytest.fixture(scope="module")
def m() -> pd.DataFrame:
    if not MASTER.exists():
        pytest.skip("run `python -m pipeline.clean` first")
    return pd.read_parquet(MASTER)


@pytest.fixture(scope="module")
def std_name() -> dict:
    """Any label NIRF ever printed -> our standard category name (from the hand-checked map)."""
    cmap = pd.read_csv(CATEGORY_MAP, keep_default_na=False)
    return dict(zip(cmap["category_original"], cmap["category_std"]))


def test_official_lists_have_28_states_and_8_uts():
    assert len(STATES) == 28 and len(UNION_TERRITORIES) == 8


# ---------- 1. duplicates ----------

def test_no_duplicate_year_category_institution(m):
    dup = m[m.duplicated(["year", "category_std", "institution_key"], keep=False)]
    assert dup.empty, dup[["year", "category_std", "institution_key", "institute_name"]].to_string()


# ---------- 2. states ----------

def test_every_state_is_an_official_state_or_ut(m):
    assert m["state"].notna().all()
    unknown = sorted(set(m["state"]) - STATES - UNION_TERRITORIES)
    assert not unknown, f"not an official state/UT name: {unknown}"


# ---------- 3. score ranges ----------

@pytest.mark.parametrize("col", SCORE_COLUMNS)
def test_scores_between_0_and_100(m, col):
    v = m[col].dropna()
    bad = m.loc[v.index[~v.between(0, 100)], ["year", "category_std", "institute_name", col]]
    assert bad.empty, bad.to_string()


# ---------- 4. rank and score agree ----------

def test_better_rank_never_has_clearly_lower_score(m):
    """Within each list, every institution's score must be at least the best score of anyone ranked
    below it (minus rounding). Institutions sharing a rank number (ties, '21A') are not compared."""
    ranked = m[m["rank"].notna() & m["score"].notna()]
    problems = []
    for (year, cat), g in ranked.groupby(["year", "category_std"]):
        per_rank = g.groupby("rank")["score"].agg(["min", "max"]).sort_index()
        # Lowest score among all strictly better ranks, for each rank.
        worst_above = per_rank["min"].cummin().shift(1)
        broken = per_rank[per_rank["max"] > worst_above + SCORE_TOLERANCE]
        for rank, row in broken.iterrows():
            problems.append(f"{year} {cat}: rank {rank} scores {row['max']} but a better rank scores "
                            f"{worst_above[rank]}")
    assert not problems, "\n".join(problems)


# ---------- 4b. score = NIRF's weighted sum of the parameters ----------

# NIRF's published weights (TLR, RPC, GO, OI, PR; Research Institutions: QnR, QlR, SFC, OI, PR), typed here
# from the methodology, not computed from our data. (category, first year, last year) -> weights.
STANDARD_WEIGHTS = (0.30, 0.30, 0.20, 0.10, 0.10)
WEIGHTS = {
    ("College", 2017, 2017): (0.30, 0.20, 0.25, 0.15, 0.10),
    ("College", 2018, 2025): (0.40, 0.15, 0.25, 0.10, 0.10),
    ("Law", 2018, 2025): (0.40, 0.15, 0.25, 0.10, 0.10),
    ("Architecture & Planning", 2019, 2025): (0.40, 0.20, 0.20, 0.10, 0.10),
}
# Each published parameter and the score are rounded to 2 decimals, so small gaps are rounding.
WEIGHTED_SUM_TOLERANCE = 0.05


def weights_for(category: str, year: int) -> tuple[float, ...]:
    for (cat, first, last), w in WEIGHTS.items():
        if cat == category and first <= year <= last:
            return w
    return STANDARD_WEIGHTS


def test_score_is_the_weighted_sum_of_the_parameters(m):
    """Every published score equals NIRF's weighted sum of its five parameters (within rounding), so the
    scores and parameters in the master table agree with each other and with NIRF's formula."""
    problems, checked = [], 0
    for (year, cat), g in m[m["score"].notna()].groupby(["year", "category_std"]):
        research = cat == "Research Institutions"
        params = ["qnr", "qlr", "sfc", "oi", "pr"] if research else ["tlr", "rpc", "go", "oi", "pr"]
        g = g.dropna(subset=params)
        if g.empty:
            continue
        gap = (g[params].to_numpy() @ weights_for(cat, year) - g["score"].to_numpy())
        checked += len(g)
        for name, d in zip(g["institute_name"], gap):
            if abs(d) > WEIGHTED_SUM_TOLERANCE:
                problems.append(f"{year} {cat}: {name} weighted sum differs from score by {d:+.2f}")
    assert checked > 6000, f"only {checked} scored rows checked"
    assert not problems, "\n".join(problems[:20])


# ---------- 5. years and categories ----------

def published_categories() -> dict[int, set[str]]:
    """{year: set of category labels} from the year x category table in docs/source_map.md
    (a cell starting with a tick means the category was published that year)."""
    lines = SOURCE_MAP.read_text(encoding="utf-8").splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("## 2. Year"))
    header = next(l for l in lines[start:] if l.startswith("| Category |"))
    years = [int(y) for y in re.findall(r"\d{4}", header)]
    out = {y: set() for y in years}
    for line in lines[lines.index(header) + 2:]:
        if not line.startswith("|"):
            break
        cells = [c.strip() for c in line.strip("|").split("|")]
        label = re.sub(r"\s*\(.*\)$", "", cells[0])
        for year, cell in zip(years, cells[1:]):
            if cell.lstrip("[").startswith("✓"):
                out[year].add(label)
    return out


def test_every_year_present(m):
    assert sorted(m["year"].unique()) == YEARS


def test_categories_per_year_match_source_map(m, std_name):
    expected = published_categories()
    assert sorted(expected) == YEARS
    for year in YEARS:
        # Special Mention (2018) is not a ranking: it lives in the participants table on purpose.
        want = {std_name[c] for c in expected[year] if not c.startswith("Special Mention")}
        got = set(m.loc[m["year"].eq(year), "category_std"])
        assert got == want, f"{year}: missing {sorted(want - got)}, unexpected {sorted(got - want)}"


# ---------- 6. nothing silently lost ----------

def raw_ranked_rows(std_name: dict) -> pd.Series:
    """Rows per (year, category_std) on the raw ranking and rank-band pages."""
    counts = []
    for path in sorted(RAW_CSV_DIR.glob("*/*.csv")):
        f = pd.read_csv(path, dtype=str, keep_default_na=False)
        f = f[f["page_type"].isin(["ranking", "band"])]
        if len(f):
            counts.append(f.groupby(["year", "category_original"]).size())
    s = pd.concat(counts).reset_index(name="rows")
    s["year"] = s["year"].astype(int)
    s["category_std"] = s["category_original"].map(std_name)
    return s.groupby(["year", "category_std"])["rows"].sum()


def test_raw_csvs_match_scrape_log():
    """The raw CSVs on disk still hold exactly the rows the scraper logged for each page."""
    log = pd.read_csv(SCRAPE_LOG)
    assert log["status"].eq("ok").all()
    for r in log.itertuples():
        path = RAW_CSV_DIR / str(r.year) / f"{r.page}.csv"
        assert len(pd.read_csv(path, dtype=str, keep_default_na=False)) == r.rows, r.page


def test_master_rows_equal_raw_rows_minus_logged_duplicates(m, std_name):
    raw = raw_ranked_rows(std_name)
    dropped = pd.read_csv(DUPLICATE_LOG)
    dropped_n = dropped.groupby(["year", "category_std"]).size()
    expected = raw.sub(dropped_n, fill_value=0).astype(int)
    got = m.groupby(["year", "category_std"]).size()
    table = pd.DataFrame({"raw": raw, "dropped": dropped_n, "expected": expected, "master": got}
                         ).fillna(0).astype(int)
    bad = table[table["expected"] != table["master"]]
    assert bad.empty, bad.to_string()
