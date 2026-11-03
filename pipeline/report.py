"""Writes docs/cleaning_report.md from the step records of pipeline/clean.py.

For every cleaning step: rows before and after, what changed, why (in simple words) and real
examples taken from the data. It ends with a data dictionary of the master table (every column,
its meaning, type and an example value) and of the participants table. Kept apart from clean.py so
the cleaning rules and the report layout can be read separately.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from pipeline.audit import md_table

# Meaning of every master-table column (the data dictionary). Order = column order in the table.
MASTER_DICTIONARY = {
    "institution_key": "Our stable ID for one real institution, the same across all years and categories "
                       "(built in step 7). Use this, not the name, to follow an institution over time.",
    "canonical_name": "One display name per institution: the name NIRF used in the most recent year it appears.",
    "institute_name": "The name as published on this row's page, tidied (spacing, punctuation, case).",
    "institute_id": "NIRF's Institute ID as published (blank on rank-band pages). From 2018 its last part "
                    "(e.g. U-0456) is stable per institution; 2017 used another scheme.",
    "city": "City as published, tidied (blank on the 2023 Innovation page, which has no City).",
    "state": "Official current state / union territory name (step 5).",
    "state_original": "State exactly as published.",
    "region": "North, South, East, West, North-East or Central (MHA zonal councils; see state_map.csv).",
    "year": "NIRF ranking year.",
    "category_std": "Standard category name, the same across years (step 4).",
    "category_original": "Category label exactly as NIRF published it that year.",
    "rank_raw": "Rank exactly as published: a number, '21A', 'Rank Withdrawn', or the band heading "
                "('101-150') for rank-band rows.",
    "rank": "Exact rank as an integer (smaller = better). Empty for rank-band and withdrawn rows.",
    "rank_status": "exact, lettered (NIRF printed e.g. '21A'), band (only a band is published) or withdrawn.",
    "is_tie": "True when another institution in the same list has the same exact rank.",
    "is_banded": "True when NIRF published only a rank band, not an exact rank.",
    "rank_band": "Standard rank band (1-10, 11-25, 26-50, 51-100, 101-150, 151-200, 201-300); NIRF's own "
                 "band when it spans two standard bands (11-50).",
    "rank_band_low": "Best (smallest) rank in rank_band.",
    "rank_band_high": "Worst (largest) rank in rank_band.",
    "rank_band_nirf": "The band exactly as NIRF published it, for rank-band rows (e.g. 76-100, 102-125).",
    "in_top10": "True when the institution is certainly within the top 10 of its list.",
    "in_top50": "True when certainly within the top 50.",
    "in_top100": "True when certainly within the top 100 (a 76-100 band row counts; a 101-150 row does not).",
    "score": "Overall NIRF score out of 100 (weighted sum of the parameters; weights differ by category).",
    "tlr": "Teaching, Learning & Resources score (0-100).",
    "rpc": "Research and Professional Practice score (0-100).",
    "go": "Graduation Outcomes score (0-100).",
    "oi": "Outreach and Inclusivity score (0-100).",
    "pr": "Perception score (0-100).",
    "qnr": "Research Institutions only: Quantitative Research score (0-100).",
    "qlr": "Research Institutions only: Qualitative Research score (0-100).",
    "sfc": "Research Institutions only: Student, Faculty and Collaboration score (0-100).",
    "tlr_rank": "Rank on TLR alone among all evaluated institutions (only where NIRF published it: "
                "2017-2018 all pages, University 2019+).",
    "rpc_rank": "Rank on RPC alone (same availability as tlr_rank).",
    "go_rank": "Rank on GO alone (same availability as tlr_rank).",
    "oi_rank": "Rank on OI alone (same availability as tlr_rank).",
    "pr_rank": "Rank on PR alone (same availability as tlr_rank).",
    "has_score": "True when the overall score is present.",
    "has_parameter_scores": "True when all of the category's parameter scores are present.",
    "first_year_seen": "First year this institution appears in this category's ranked list.",
    "is_new_entrant": "True on its first appearance in the category, if the category existed the year before.",
    "years_present": "Number of different years the institution appears in this category.",
    "institute_name_raw": "Name exactly as published, before tidying (links to institution_aliases.csv).",
    "source_url": "The NIRF page the row was read from.",
    "source_note": "Scraper note about this row (e.g. a merged 'Rank Withdrawn*' cell); usually empty.",
}

PARTICIPANT_DICTIONARY = {
    "institution_key": "Key of the same institution in the master table, when its cleaned name + state "
                       "match a ranked institution exactly; empty otherwise (never ranked, or no sure match).",
    "canonical_name": "canonical_name of that ranked institution (empty when not linked).",
    "list_type": "participant (List of Participating Institutions) or special_mention (2018 page).",
}


def _type_name(s: pd.Series) -> str:
    d = str(s.dtype)
    return {"object": "text", "str": "text", "string": "text", "int64": "integer", "Int64": "integer (nullable)",
            "float64": "decimal", "bool": "true/false"}.get(d, d)


def _example(s: pd.Series, row: pd.Series) -> str:
    v, note = row[s.name], ""
    if pd.isna(v) or v == "":
        non_blank = s.dropna()
        non_blank = non_blank[non_blank.astype(str).ne("")]
        v, note = (non_blank.iloc[0], " (other row)") if len(non_blank) else ("", "")
    if isinstance(v, float):
        v = f"{v:g}"
    return f"`{v}`{note}"


def _dictionary(df: pd.DataFrame, meanings: dict, example_row: pd.Series) -> str:
    rows = []
    for c in df.columns:
        rows.append({"column": f"`{c}`", "meaning": meanings.get(c, MASTER_DICTIONARY.get(c, "")),
                     "type": _type_name(df[c]), "example": _example(df[c], example_row)})
    return md_table(pd.DataFrame(rows))


def write_report(path: Path, records: list, master: pd.DataFrame, participants: pd.DataFrame,
                 ident) -> None:
    s = ident.stats
    parts = [
        "# NIRF cleaning report",
        "",
        f"Generated by `python -m pipeline.clean` on {date.today():%d %B %Y} from the raw CSVs in "
        "`data/raw/csv/` (the raw files are never changed). Re-run after any change to the raw data, "
        "the mapping tables or the review decisions; this file is rewritten every run.",
        "",
        "Inputs (hand-checked): `data/mappings/category_map.csv`, `data/mappings/state_map.csv`, "
        "`data/mappings/institution_alias_rules.csv`, and the `approve` column of "
        "`data/mappings/institution_review.csv`. Outputs: `data/processed/nirf_master.parquet` (+ `.csv`), "
        "`data/processed/nirf_participants.parquet`, `data/mappings/institution_aliases.csv`, "
        "`data/mappings/institution_review.csv`.",
        "",
        "## Summary",
        "",
        f"- **Master table:** {len(master):,} rows x {master.shape[1]} columns: every institution NIRF "
        f"ranked, {master['year'].min()}-{master['year'].max()}, {master['category_std'].nunique()} "
        f"categories, one row per (year, category, institution).",
        f"- **Institutions:** {master['institution_key'].nunique():,} distinct `institution_key`s from "
        f"{s['raw_names']:,} raw name spellings.",
        f"- **Exact ranks:** {int(master['rank'].notna().sum()):,} rows; **rank-band only:** "
        f"{int(master['is_banded'].sum()):,} rows; rows with an overall score: "
        f"{int(master['has_score'].sum()):,}.",
        f"- **Participants table:** {len(participants):,} rows (participant lists + 2018 Special Mention), "
        f"kept apart from the rankings.",
        f"- **Waiting for a human:** {s['review_waiting']} uncertain name pairs in "
        "`data/mappings/institution_review.csv` (fill `approve` with yes or no, then re-run).",
        "",
        md_table(pd.DataFrame([{"step": r.number, "what": r.title, "rows before": f"{r.rows_before:,}",
                                "rows after": f"{r.rows_after:,}"} for r in records])),
        "",
        "Contents: " + " · ".join(f"[{r.number} {r.title}](#step-{r.number}-"
                                   + "-".join(r.title.lower().replace("+", "").replace(",", "")
                                              .replace("(", "").replace(")", "").replace("/", "").split())
                                   + ")" for r in records) + " · [Data dictionary](#data-dictionary)",
        "",
    ]
    for r in records:
        parts += [f"## Step {r.number}: {r.title}", "",
                  f"**Rows:** {r.rows_before:,} -> {r.rows_after:,}", "",
                  f"**What changed:** {r.changed}", "",
                  f"**Why:** {r.why}", ""]
        if r.examples is not None and len(r.examples):
            parts += ["**Examples (real rows):**", "", md_table(r.examples), ""]
        for d in r.details:
            parts += [md_table(d) if isinstance(d, pd.DataFrame) else d, ""]

    ex_row = master[(master["canonical_name"].str.contains("Technology Madras"))
                    & master["category_std"].eq("Overall")].sort_values("year").iloc[-1]
    p_row = participants[participants["institution_key"].notna()].iloc[0]
    parts += [
        "## Data dictionary",
        "",
        "### `data/processed/nirf_master.parquet`",
        "",
        "One row per (year, category_std, institution_key). Examples come from IIT Madras, Overall "
        f"{ex_row['year']}; '(other row)' marks a column that is blank for IIT Madras, shown from another row.",
        "",
        _dictionary(master, MASTER_DICTIONARY, ex_row),
        "",
        "### `data/processed/nirf_participants.parquet`",
        "",
        "One row per name on a participant list (or the 2018 Special Mention page). Columns with the "
        "same name as in the master table mean the same thing.",
        "",
        _dictionary(participants, PARTICIPANT_DICTIONARY, p_row),
        "",
    ]
    path.write_text("\n".join(parts), encoding="utf-8")
