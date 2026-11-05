"""List institutions that may have been renamed, so a person can check them (nothing is merged here).

A rename splits one college into two institution keys: the old name stops being listed and the new
name starts, and every "2017 -> 2025" comparison, "new entrant" count and "years present" count is then
wrong for it. This script finds pairs that look like that, using four plain rules on the master table:

  1. timing: institution A is last listed in year Y and institution B is first listed in Y+1
     (or after a gap of at most MAX_GAP years, e.g. a college that skipped one year);
  2. place: same state and the same city (city spellings compared with the pipeline's city key, so
     Bangalore = Bengaluru);
  3. name: the cleaned names are similar (rapidfuzz token_set_ratio >= MIN_SIMILARITY, which also gives
     100 when one name is the other plus a few words, e.g. 'NITTE' / 'NITTE University');
  4. never together: A and B never appear in the same ranking list (same year and category), because
     one list never contains the same institution twice. At least one category must be shared.

The candidates are written to data/mappings/rename_review.csv, best first. A pair we confirm goes into
data/mappings/institution_alias_rules.csv (with the evidence in the note), then `python -m pipeline.clean`.
A pair already decided in data/mappings/institution_review.csv shows that decision.

    python -m scripts.find_renames
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pipeline.audit import fmt_years  # noqa: E402
from pipeline.identity import city_key, name_key  # noqa: E402

MASTER = ROOT / "data" / "processed" / "nirf_master.parquet"
REVIEW = ROOT / "data" / "mappings" / "institution_review.csv"
OUT = ROOT / "data" / "mappings" / "rename_review.csv"

MAX_GAP = 2            # B may start at most this many years after A's last year (1 = the very next year)
MIN_SIMILARITY = 75    # token_set_ratio of the cleaned names
CITY_SAME = 85         # same threshold as the pipeline uses for two city spellings


def institutions(df: pd.DataFrame) -> pd.DataFrame:
    """One row per institution key: names, city, state, years, categories and the lists it is in."""
    df = df.assign(name_key=df["institute_name"].map(name_key), city_key=df["city"].fillna("").map(city_key))
    g = df.groupby("institution_key")
    return pd.DataFrame({
        "name": g["canonical_name"].first(),
        "name_keys": g["name_key"].agg(set),
        "state": g["state"].first(),
        "cities": g["city_key"].agg(lambda c: {x for x in c if x}),
        "city": g["city"].agg(lambda c: " / ".join(sorted({x for x in c.dropna() if x}))),
        "first": g["year"].min(), "last": g["year"].max(),
        "years": g["year"].agg(lambda y: sorted(set(y))),
        "categories": g["category_std"].agg(set),
        "lists": g.apply(lambda x: set(zip(x["year"], x["category_std"])), include_groups=False),
    })


def same_city(a: set, b: set) -> bool:
    return not a or not b or max(fuzz.token_set_ratio(x, y) for x in a for y in b) >= CITY_SAME


def decisions() -> dict[frozenset, str]:
    """{canonical name pair: 'yes'/'no'} from the institution review file (names, as the file shows them)."""
    if not REVIEW.exists():
        return {}
    r = pd.read_csv(REVIEW, dtype=str, keep_default_na=False)
    return {frozenset((a, b)): v for a, b, v in zip(r["name_a"], r["name_b"], r["approve"]) if v}


def candidates(inst: pd.DataFrame) -> pd.DataFrame:
    decided = decisions()
    rows = []
    for state, grp in inst.groupby("state"):
        for ka, a in grp.iterrows():
            later = grp[(grp["first"] > a["last"]) & (grp["first"] <= a["last"] + MAX_GAP)]
            for kb, b in later.iterrows():
                if not (a["categories"] & b["categories"]) or (a["lists"] & b["lists"]):
                    continue
                if not same_city(a["cities"], b["cities"]):
                    continue
                score = max(fuzz.token_set_ratio(x, y) for x in a["name_keys"] for y in b["name_keys"])
                if score < MIN_SIMILARITY:
                    continue
                rows.append({
                    "approve": "", "similarity": round(score), "gap_years": int(b["first"] - a["last"]),
                    "old_name": a["name"], "old_years": fmt_years(a["years"]),
                    "new_name": b["name"], "new_years": fmt_years(b["years"]),
                    "state": state, "old_city": a["city"], "new_city": b["city"],
                    "shared_categories": ", ".join(sorted(a["categories"] & b["categories"])),
                    "review_file_decision": decided.get(frozenset((a["name"], b["name"])), ""),
                    "old_key": ka, "new_key": kb,
                })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["gap_years", "similarity", "old_name"], ascending=[True, False, True]).reset_index(drop=True)


def main() -> int:
    inst = institutions(pd.read_parquet(MASTER))
    out = candidates(inst)
    out.to_csv(OUT, index=False)
    print(f"{len(out)} possible renames -> {OUT.relative_to(ROOT)} "
          f"(same state and city, similarity >= {MIN_SIMILARITY}, B starts within {MAX_GAP} years of A's last year, "
          f"never in the same list)")
    if not out.empty:
        print(out[["similarity", "gap_years", "old_name", "old_years", "new_name", "new_years"]].head(40).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
