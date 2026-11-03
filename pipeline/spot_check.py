"""Spot check (Phase 5): compare random master-table rows with the original NIRF web pages.

The automatic tests prove the master table is internally consistent; this script lets a PERSON
confirm it still says what NIRF published. It picks 15 random rows from
data/processed/nirf_master.parquet, opens the cached HTML page each row came from
(data/raw/html/<year>/<page>.html, found through source_url in data/raw/scrape_log.csv), finds the
same institution on that page and prints both versions side by side.

The HTML is read here with its own small parser, NOT with the scraper's code, so a mistake in the
scraper would show up as a difference instead of being repeated.

Each line ends with a verdict:
  same     identical text / number
  cleaned  same once case, spacing, punctuation and PIN / district numbers are ignored (expected: the
           pipeline tidies names, cities and state spellings)
  standardised  a state spelling replaced by its official name (data/mappings/state_map.csv)
  DIFF     a real difference: look at it

Run from the project root:
    python -m pipeline.spot_check              # new random sample (the seed is printed)
    python -m pipeline.spot_check --seed 7     # repeat a sample
    python -m pipeline.spot_check --n 30
"""

from __future__ import annotations

import argparse
import random
import re
import sys
from functools import lru_cache
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "data" / "processed" / "nirf_master.parquet"
SCRAPE_LOG = ROOT / "data" / "raw" / "scrape_log.csv"
HTML_DIR = ROOT / "data" / "raw" / "html"

PARAM_HEADERS = {"TLR": "tlr", "RPC": "rpc", "GO": "go", "OI": "oi", "PERCEPTION": "pr",
                 "QNR": "qnr", "QLR": "qlr", "SFC": "sfc"}


# ------------------------------------------------------------------ reading the HTML page

def squash(s: str) -> str:
    return " ".join(s.split())


def hidden(tag: Tag) -> bool:
    return "display:none" in (tag.get("style") or "").replace(" ", "").lower()


def own_text(td: Tag) -> str:
    """The text written directly in a cell, without the 'More Details' block and hidden table."""
    return squash(" ".join(str(c) for c in td.children if type(c) is NavigableString))  # no comments


def cell_params(td: Tag) -> dict[str, str]:
    """Parameter scores from the hidden table inside a Name cell: {'tlr': '95.47', ...}."""
    table = td.find("table")
    if table is None:
        return {}
    heads = [squash(th.get_text(" ")).split(" ")[0].upper() for th in table.find_all("th")]
    tds = table.find("tbody").find_all("td") if table.find("tbody") else []
    return {PARAM_HEADERS.get(h, h.lower()): squash(td.get_text(" ")) for h, td in zip(heads, tds)}


@lru_cache(maxsize=None)  # each page is parsed once, however many sampled rows use it
def page_rows(path: Path) -> tuple[str, list[dict]]:
    """(page heading, rows of the institution table). Each row maps column header -> text."""
    soup = BeautifulSoup(path.read_bytes(), "lxml")
    heading = next((squash(h.get_text(" ")) for h in soup.find_all(["h1", "h2", "h3", "h4"])
                    if "India Rankings" in h.get_text()), "")
    table = soup.find("table", id="tbl_overall") or next(
        t for t in soup.find_all("table") if t.find_parent("table") is None
        and "Name" in [squash(th.get_text(" ")) for th in t.find_all("th")])
    heads = [squash(th.get_text(" ")) for th in table.find("tr").find_all("th")]
    rows = []
    for tr in table.find_all("tr"):
        if tr.find_parent("table") is not table:
            continue
        cells = [td for td in tr.find_all("td", recursive=False) if not hidden(td)]
        if not cells:
            continue
        row, col = {h: "" for h in heads}, 0
        for td in cells:
            span = int(td.get("colspan") or 1)
            head = heads[min(col + span, len(heads)) - 1]
            row[head] = own_text(td) if head == "Name" else squash(td.get_text(" "))
            if head == "Name":
                row.update(cell_params(td))
            col += span
        rows.append(row)
    return heading, rows


# ------------------------------------------------------------------ comparing

def loose(s) -> str:
    """Text for a forgiving comparison: lower case, letters and digits only, no PIN codes and no
    old postal-district numbers ('Calcutta-16'), which the pipeline removes on purpose."""
    s = re.sub(r"\b\d{3}\s?\d{3}\b|(?<=[A-Za-z])-\d{1,3}$", "", str(s)).lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]", "", s)


def verdict(master_value, raw_value) -> str:
    if pd.isna(master_value) or master_value == "":
        return "same" if raw_value in ("", None) else "DIFF"
    try:
        if abs(float(master_value) - float(raw_value)) < 0.005:
            return "same"
    except (TypeError, ValueError):
        pass
    if str(master_value) == str(raw_value):
        return "same"
    return "cleaned" if loose(master_value) == loose(raw_value) else "DIFF"


def find_row(rows: list[dict], rec: pd.Series) -> dict | None:
    """The page row for this institution: by Institute ID where the page has one, else by name."""
    if pd.notna(rec["institute_id"]):
        hit = [r for r in rows if r.get("Institute ID") == rec["institute_id"]]
        if len(hit) == 1:
            return hit[0]
    hit = [r for r in rows if squash(r.get("Name", "")) == squash(rec["institute_name_raw"])]
    if len(hit) > 1 and pd.notna(rec["city"]):
        hit = [r for r in hit if loose(r.get("City", "")) == loose(rec["city"])] or hit
    return hit[0] if hit else None


def compare(rec: pd.Series, heading: str, raw: dict | None) -> pd.DataFrame:
    raw = raw or {}
    if rec["rank_status"] == "band":
        band = re.search(r"Rank\s*-\s*band:\s*(\d+-\d+)", heading)
        raw_rank = band.group(1) if band else ""
    else:
        raw_rank = raw.get("Rank", raw.get("Band", ""))
    fields = [
        ("name", rec["institute_name"], raw.get("Name", "")),
        ("city", rec["city"], raw.get("City", "")),
        ("state", rec["state"], raw.get("State", "")),        # official name; see below
        ("rank", rec["rank_raw"], raw_rank),
        ("score", rec["score"], raw.get("Score", "")),
    ]
    params = ["qnr", "qlr", "sfc", "oi", "pr"] if rec["category_std"] == "Research Institutions" \
        else ["tlr", "rpc", "go", "oi", "pr"]
    fields += [(p, rec[p], raw.get(p, "")) for p in params]
    out = pd.DataFrame(fields, columns=["field", "master table", "NIRF page (cached HTML)"])
    out["check"] = [verdict(a, b) for a, b in zip(out["master table"], out["NIRF page (cached HTML)"])]
    # A state renamed by data/mappings/state_map.csv (e.g. Pondicherry -> Puducherry) is expected.
    is_state = out["field"].eq("state") & out["check"].eq("DIFF")
    if is_state.any() and verdict(rec["state_original"], raw.get("State", "")) == "same":
        out.loc[is_state, "check"] = "standardised"
    out["master table"] = out["master table"].map(lambda v: "" if pd.isna(v) else v)
    return out


# ------------------------------------------------------------------ main

def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--n", type=int, default=15, help="how many rows to check (default 15)")
    ap.add_argument("--seed", type=int, default=None, help="repeat an earlier sample")
    args = ap.parse_args()
    seed = args.seed if args.seed is not None else random.randrange(10_000)

    master = pd.read_parquet(MASTER)
    log = pd.read_csv(SCRAPE_LOG)
    page_of = dict(zip(log["url"], log["page"]))
    sample = master.sample(args.n, random_state=seed)
    print(f"Spot check of {args.n} random master rows (seed {seed}; repeat with --seed {seed})\n")

    pd.set_option("display.width", 200)
    pd.set_option("display.max_colwidth", 70)
    totals = {"same": 0, "cleaned": 0, "standardised": 0, "DIFF": 0}
    not_found = 0
    for i, (_, rec) in enumerate(sample.iterrows(), 1):
        path = HTML_DIR / str(rec["year"]) / f"{page_of[rec['source_url']]}.html"
        heading, rows = page_rows(path)
        raw = find_row(rows, rec)
        print(f"[{i:>2}] {rec['year']} {rec['category_std']} | {rec['canonical_name']} | "
              f"{path.relative_to(ROOT).as_posix()}")
        if raw is None:
            not_found += 1
            print("     NOT FOUND on the page: look at it by hand\n")
            continue
        table = compare(rec, heading, raw)
        print(table.to_string(index=False), "\n")
        for k, v in table["check"].value_counts().items():
            totals[k] += v

    print(f"Summary: {totals['same']} fields identical, {totals['cleaned']} equal after cleaning, "
          f"{totals['standardised']} state names standardised, {totals['DIFF']} different, {not_found} institutions not found on their page.")
    if totals["DIFF"] or not_found:
        print("Look at every DIFF / NOT FOUND above before trusting the master table.")


if __name__ == "__main__":
    main()
