"""Data checks on the cleaned master table (data/processed/nirf_master.parquet).

These tests guard the promises the cleaning pipeline makes: one row per (year, category,
institution), ranks and scores in valid ranges, standard states and categories, no invented
scores, and correct links for a few institutions whose names changed. Run after the pipeline:

    python -m pipeline.clean
    python -m pytest tests/test_master.py
"""

from pathlib import Path

import pandas as pd
import pytest

from pipeline.clean import STANDARD_BANDS, tidy_city, tidy_name
from pipeline.identity import name_key

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "data" / "processed" / "nirf_master.parquet"
PARTICIPANTS = ROOT / "data" / "processed" / "nirf_participants.parquet"
MAPPINGS = ROOT / "data" / "mappings"


@pytest.fixture(scope="module")
def m() -> pd.DataFrame:
    if not MASTER.exists():
        pytest.skip("run `python -m pipeline.clean` first")
    return pd.read_parquet(MASTER)


def keys_of(m: pd.DataFrame, pattern: str, state: str) -> set:
    rows = m[m["institute_name"].str.fullmatch(pattern, case=False) & m["state"].eq(state)]
    return set(rows["institution_key"])


# ---------- shape and keys ----------

def test_covers_all_years_and_ranked_rows(m):
    assert sorted(m["year"].unique()) == list(range(2017, 2026))
    assert len(m) == 11647                      # 6,976 ranking-page rows + 4,671 band rows


def test_one_row_per_year_category_institution(m):
    assert not m.duplicated(["year", "category_std", "institution_key"]).any()
    assert m["institution_key"].notna().all()


def test_one_canonical_name_per_key(m):
    assert m.groupby("institution_key")["canonical_name"].nunique().eq(1).all()


# ---------- categories and states ----------

def test_categories_follow_mapping(m):
    cmap = pd.read_csv(MAPPINGS / "category_map.csv")
    pairs = set(zip(cmap["category_original"], cmap["year"], cmap["category_std"]))
    got = set(zip(m["category_original"], m["year"], m["category_std"]))
    assert got <= pairs
    assert "Special Mention" not in set(m["category_std"])
    assert m.groupby("year")["category_std"].nunique().to_dict() == {
        2017: 6, 2018: 9, 2019: 9, 2020: 10, 2021: 11, 2022: 11, 2023: 13, 2024: 16, 2025: 17}


def test_states_are_official(m):
    smap = pd.read_csv(MAPPINGS / "state_map.csv")
    assert set(m["state"]) <= set(smap["state_std"])
    assert set(m["region"]) == {"North", "South", "East", "West", "North-East", "Central"}
    assert not m["state"].isin(["Pondicherry", "Jammu & Kashmir", "TAMIL NADU"]).any()


# ---------- ranks ----------

def test_rank_columns_consistent(m):
    exact = m["rank_status"].isin(["exact", "lettered"])
    assert m.loc[exact, "rank"].notna().all() and (m.loc[exact, "rank"] >= 1).all()
    assert m.loc[m["is_banded"], "rank"].isna().all()
    assert m.loc[m["is_banded"], "rank_band_nirf"].notna().all()
    assert m["is_banded"].eq(m["rank_status"].eq("band")).all()
    known = m["rank_status"].ne("withdrawn")
    assert m.loc[known, "rank_band"].notna().all()
    assert (m.loc[known, "rank_band_low"] <= m.loc[known, "rank_band_high"]).all()
    with_rank = m["rank"].notna()
    assert m.loc[with_rank, "rank"].between(m.loc[with_rank, "rank_band_low"],
                                            m.loc[with_rank, "rank_band_high"]).all()
    standard = {f"{a}-{b}" for a, b in STANDARD_BANDS}
    assert set(m.loc[~m["is_banded"] & known, "rank_band"]) <= standard


def test_top_flags_nest(m):
    assert (~m["in_top10"] | m["in_top50"]).all()
    assert (~m["in_top50"] | m["in_top100"]).all()
    assert m.groupby(["year", "category_std"])["in_top10"].sum().max() <= 11   # ties can add one


def test_ties_share_score(m):
    ties = m[m["is_tie"] & m["score"].notna()]
    assert ties.groupby(["year", "category_std", "rank"])["score"].nunique().eq(1).all()


def test_special_ranks_kept_raw(m):
    lettered = m[m["rank_status"].eq("lettered")]
    assert sorted(lettered["rank_raw"]) == ["16A", "21A", "26A"]
    assert m["rank_status"].eq("withdrawn").sum() == 2


# ---------- numbers and missing values ----------

def test_scores_in_range_and_never_invented(m):
    for col in ["score", "tlr", "rpc", "go", "oi", "pr", "qnr", "qlr", "sfc"]:
        v = m[col].dropna()
        assert v.between(0, 100).all(), col
    assert m.loc[m["is_banded"], ["score", "tlr", "rpc", "go", "oi", "pr"]].isna().all().all()
    assert m["has_score"].eq(m["score"].notna()).all()


def test_better_rank_never_lower_score(m):
    exact = m[m["rank_status"].eq("exact") & m["score"].notna()].sort_values("rank")
    assert exact.groupby(["year", "category_std"])["score"].apply(lambda s: s.is_monotonic_decreasing).all()


# ---------- derived columns ----------

def test_new_entrants(m):
    assert not m.loc[m["year"].eq(2017), "is_new_entrant"].any()
    assert (m.loc[m["is_new_entrant"], "year"] == m.loc[m["is_new_entrant"], "first_year_seen"]).all()
    assert m["years_present"].between(1, 9).all()


# ---------- institution identity: known renames and traps ----------

def test_iisc_2017_name_linked(m):
    # 2017: 'Indian Institute of Science Bangalore'; 2018+: 'Indian Institute of Science'
    k = m[m["canonical_name"].eq("Indian Institute of Science") & m["category_std"].eq("Overall")]
    assert sorted(k["year"]) == list(range(2017, 2026))


def test_upes_rename_linked_by_id_code(m):
    a = keys_of(m, "University of Petroleum and Energy Studies", "Uttarakhand")
    b = keys_of(m, "UPES", "Uttarakhand")
    assert len(a) == 1 and a == b


def test_iit_delhi_one_key(m):
    assert len(keys_of(m, r"Indian Institute of Technology,? Delhi", "Delhi")) == 1


def test_same_name_different_city_kept_apart(m):
    jaipuria_up = m[m["institute_name"].str.startswith("Jaipuria") & m["state"].eq("Uttar Pradesh")]
    assert jaipuria_up.groupby("city")["institution_key"].nunique().eq(1).all()
    assert jaipuria_up[jaipuria_up["city"].isin(["Noida", "Lucknow"])]["institution_key"].nunique() == 2


def test_review_file_has_approve_column():
    r = pd.read_csv(MAPPINGS / "institution_review.csv", dtype=str, keep_default_na=False)
    assert {"approve", "node_a", "node_b", "score", "reason"} <= set(r.columns)


def test_participants_separate():
    if not PARTICIPANTS.exists():
        pytest.skip("run `python -m pipeline.clean` first")
    p = pd.read_parquet(PARTICIPANTS)
    assert set(p["list_type"]) == {"participant", "special_mention"}
    assert "rank" not in p.columns


# ---------- cleaning helpers ----------

@pytest.mark.parametrize("raw, clean", [
    ("St. Xavier`s College", "St. Xavier's College"),
    ("Bharati Vidyapeeth?s Institute of Management", "Bharati Vidyapeeth's Institute of Management"),
    ("Shri Shivaji Science College , Morshi Road , Amravati.", "Shri Shivaji Science College, Morshi Road, Amravati"),
    ("Birla Institute of Technology & Science -Pilani", "Birla Institute of Technology & Science - Pilani"),
    ("Government Arts College, Kumbakonam - 612 001.", "Government Arts College, Kumbakonam"),
    ("INDIAN INSTITUTE OF TECHNOLOGY KANPUR", "Indian Institute of Technology Kanpur"),
    ("UPES", "UPES"),
])
def test_tidy_name(raw, clean):
    assert tidy_name(raw) == clean


def test_tidy_city():
    assert tidy_city("Calcutta-16") == "Calcutta"
    assert tidy_city("DELHI") == "Delhi"


@pytest.mark.parametrize("a, b", [
    ("S.R.M. Institute of Science & Technology", "SRM Institute of Science and Technology"),
    ("Indian Institute of Technology, Kharagpur", "INDIAN INSTITUTE OF TECHNOLOGY KHARAGPUR"),
    ("Govt. Arts College", "Government Arts College"),
    ("St Berchmans College (Autonomous)", "St. Berchmans College"),
])
def test_name_key_equal(a, b):
    assert name_key(a) == name_key(b)
