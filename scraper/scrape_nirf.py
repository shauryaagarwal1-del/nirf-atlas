"""Full NIRF scraper (Phase 2): every category, every year 2017-2025, one CSV per page.

What it does:
  1. Finds every page NIRF published for each year, exactly as docs/source_map.md describes:
     year index page -> category pages -> rank-band pages and participant-list pages
     (and the 2018 "Special Mention" page).
  2. Gets the HTML of each page. A page already cached in data/raw/html/<year>/ is read from
     disk and NOT downloaded again; only missing pages are fetched (politely, one at a time).
  3. Reads the institution table of each page and writes it to
         data/raw/csv/<year>/<page>.csv
     where <page> is the same name as the cached HTML file, e.g. engineering.csv,
     engineering__band_101-150.csv, engineering__participants.csv.
  4. Writes data/raw/scrape_log.csv (one line per page: rows, status, notes) and prints a
     summary table of rows by year x category.

What goes into each CSV:
  - The table columns exactly as the site shows them (e.g. Institute ID, Name, City, State,
    Score, Rank) with the values kept as the original text (so "21A" or "Rank Withdrawn" are
    not lost). Cleaning happens later, in pipeline/.
  - The five parameter scores (tlr, rpc, go, oi, pr). On ranking pages they sit in a hidden
    table inside the Name cell ("More Details"). Research Institutions use different
    parameters (QNR, QLR, SFC, OI, PERCEPTION); those go to columns qnr, qlr, sfc, oi, pr and
    are never put into tlr/rpc/go.
  - Where the page also has the "By TLR / By RPC ..." tabs (all pages in 2017-2018, the
    University page in 2019-2025), the rank on each parameter (tlr_rank ... pr_rank) is merged
    in on the Institute ID, and the tab scores are cross-checked against the hidden table.
  - Page metadata: year, category_original (the label NIRF used in the page heading),
    category_slug, page_type (ranking / band / participants / special_mention), rank_band,
    row_note (anything unusual in that row), source_url and scraped_at (when the HTML was
    downloaded, in UTC).

Resilient: every page is processed inside its own try/except, so one bad page is logged as
"failed" and the run carries on. Re-runnable: cached HTML is reused and the CSVs are simply
rebuilt from it, so running it twice gives the same files.

Run from the project root:
    python -m scraper.scrape_nirf                  # all years
    python -m scraper.scrape_nirf --years 2024 2025
    python -m scraper.scrape_nirf --refresh        # re-download every page (rarely needed)
"""

from __future__ import annotations

import argparse
import re
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from scraper.explore_source import (
    BASE_URL,
    HTML_DIR,
    ROOT,
    YEARS,
    fallback_index_urls,
    fetch_cached,
    find_year_index_urls,
    header_cells,
    list_categories,
    list_subpages,
    make_session,
    own_rows,
    text_of,
)

CSV_DIR = ROOT / "data" / "raw" / "csv"
LOG_PATH = ROOT / "data" / "raw" / "scrape_log.csv"

# Parameter tabs on the page ("By TLR", "By RPC" ...): table id -> our column key.
TAB_TABLE_IDS = {"tbl_tlr": "tlr", "tbl_rpc": "rpc", "tbl_go": "go", "tbl_oi": "oi", "tbl_pr": "pr"}
STANDARD_PARAMS = ["tlr", "rpc", "go", "oi", "pr"]
HEADING_RE = re.compile(r"India Rankings\s*\d{4}\s*:\s*(.+)", re.I)
ID_HEADER = "Institute ID"

META_FRONT = ["year", "category_original", "category_slug", "page_type", "rank_band"]
META_BACK = ["row_note", "source_url", "scraped_at"]


# --------------------------------------------------------------------------- jobs


@dataclass
class PageJob:
    """One web page to scrape and the CSV it becomes."""

    year: int
    category_slug: str
    page_type: str  # ranking | band | participants | special_mention
    url: str
    file_stem: str  # e.g. "engineering__band_101-150" (same name for the .html and the .csv)
    rank_band: str = ""
    category_original: str = ""  # filled from the category's main page heading
    discovery_error: str = ""

    @property
    def html_path(self) -> Path:
        return HTML_DIR / str(self.year) / f"{self.file_stem}.html"

    @property
    def csv_path(self) -> Path:
        return CSV_DIR / str(self.year) / f"{self.file_stem}.csv"


@dataclass
class LogEntry:
    year: int
    category: str
    page: str
    url: str
    rows: int = 0
    status: str = "ok"
    notes: list[str] = field(default_factory=list)

    def as_row(self) -> dict:
        return {
            "year": self.year,
            "category": self.category,
            "page": self.page,
            "url": self.url,
            "rows": self.rows,
            "status": self.status,
            "notes": "; ".join(self.notes),
        }


def category_label_from_heading(soup: BeautifulSoup) -> str:
    """'India Rankings 2024: Research Institutions' -> 'Research Institutions'."""
    for h in soup.find_all(["h1", "h2", "h3", "h4"]):
        match = HEADING_RE.search(text_of(h))
        if match:
            return match.group(1).strip()
    return ""


def page_heading(soup: BeautifulSoup) -> str:
    for h in soup.find_all(["h1", "h2", "h3", "h4"]):
        text = text_of(h)
        if text:
            return text
    return ""


def discover_jobs(session: requests.Session, years: list[int], refresh: bool) -> list[PageJob]:
    """Walk home -> year index -> category pages -> band/participant pages, using the cache.

    Category pages are fetched here because their links tell us which sub-pages exist.
    A page that cannot be fetched still becomes a job, so it shows up as 'failed' in the log.
    """
    home_html, _ = get_html(session, BASE_URL, HTML_DIR / "_home.html", refresh)
    index_urls = find_year_index_urls(home_html) if home_html else {}
    jobs: list[PageJob] = []

    for year in years:
        candidates = [index_urls[year]] if year in index_urls else fallback_index_urls(year)
        index_html, index_url, status = None, None, "not found"
        for url in candidates:
            index_html, status = get_html(session, url, HTML_DIR / str(year) / "_index.html", refresh)
            if index_html:
                index_url = url
                break
        if not index_html:
            jobs.append(PageJob(year, "_index", "index", candidates[0], "_index", discovery_error=status))
            continue

        for cat in list_categories(index_html, index_url):
            page_type = "special_mention" if cat["slug"] == "special_mention" else "ranking"
            main = PageJob(year, cat["slug"], page_type, cat["url"], cat["slug"])
            jobs.append(main)
            html, status = get_html(session, main.url, main.html_path, refresh)
            if not html:
                main.discovery_error = status
                continue
            soup = BeautifulSoup(html, "lxml")
            main.category_original = category_label_from_heading(soup) or page_heading(soup)
            for sub in list_subpages(html, cat["url"], cat["slug"]):
                jobs.append(
                    PageJob(
                        year,
                        cat["slug"],
                        sub["kind"],
                        sub["url"],
                        sub["file_stem"],
                        rank_band=sub["band"] or "",
                        category_original=main.category_original,
                    )
                )
    return jobs


def get_html(session: requests.Session, url: str, path: Path, refresh: bool) -> tuple[bytes | None, str]:
    """Cached HTML if we have it (unless --refresh), otherwise one polite download."""
    if refresh and path.exists():
        path.unlink()
    return fetch_cached(session, url, path)


# --------------------------------------------------------------------------- parsing helpers


def is_hidden(tag: Tag) -> bool:
    return "display:none" in (tag.get("style") or "").replace(" ", "").lower()


def own_cell_text(td: Tag) -> str:
    """Text of a cell WITHOUT nested blocks (the 'More Details' links and hidden score table)."""
    parts: list[str] = []
    for child in td.children:
        if isinstance(child, Comment):
            continue
        if isinstance(child, NavigableString):
            parts.append(str(child))
        elif isinstance(child, Tag) and child.name not in {"div", "table", "script", "style"}:
            parts.append(child.get_text(" "))
    return " ".join(" ".join(parts).split())


def param_key(header: str) -> str:
    """'TLR (100)' -> 'tlr', 'PERCEPTION (100)' -> 'pr', 'QNR (100)' -> 'qnr', 'PR Score' -> 'pr'."""
    word = header.strip().split()[0].lower() if header.strip() else ""
    return "pr" if word in {"perception", "pr"} else re.sub(r"[^a-z0-9]", "", word)


def nested_params(td: Tag) -> dict[str, str]:
    """The five parameter scores from the hidden table inside a Name cell, keyed by param_key."""
    nested = td.find("table")
    if nested is None:
        return {}
    headers = header_cells(nested)
    body_rows = [tr for tr in own_rows(nested) if tr.find("td", recursive=False)]
    if not headers or not body_rows:
        return {}
    values = [text_of(c) for c in body_rows[0].find_all("td", recursive=False)]
    return {param_key(h): v for h, v in zip(headers, values)}


def find_main_table(soup: BeautifulSoup) -> Tag | None:
    """The page's institution table: tbl_overall (ranking pages), tblAllInstitutes
    (participant lists) or, on band and special pages, the first table with a Name column."""
    for table_id in ("tbl_overall", "tblAllInstitutes"):
        table = soup.find("table", id=table_id)
        if table is not None:
            return table
    for table in soup.find_all("table"):
        if table.find_parent("table") is None and "Name" in header_cells(table):
            return table
    return None


def read_table(table: Tag, with_params: bool) -> tuple[list[str], list[dict], list[str]]:
    """Return (site headers, rows, page notes). Each row maps header -> original text.

    Handles the two layout quirks seen on the site:
      - merged cells (colspan): the text goes to the LAST column it covers, the others stay
        blank, and the row gets a row_note (e.g. 2025 Dental "Rank Withdrawn*" over Score+Rank);
      - hidden cells (display:none): not shown on the site, so not put in a column; their text
        is kept in row_note so nothing is thrown away.
    """
    headers = header_cells(table)
    rows: list[dict] = []
    notes: list[str] = []
    for tr in own_rows(table):
        cells = tr.find_all("td", recursive=False)
        if not cells:
            continue
        row: dict = {h: "" for h in headers}
        row_notes: list[str] = []
        col = 0
        for td in cells:
            if is_hidden(td):
                row_notes.append(f"hidden cell text '{text_of(td)}'")
                continue
            span = int(td.get("colspan") or 1)
            if col + span > len(headers):
                row_notes.append(f"extra cell '{own_cell_text(td)}' beyond the header")
                col += span
                continue
            target = headers[col + span - 1]
            row[target] = own_cell_text(td)
            if span > 1:
                row_notes.append(f"'{row[target]}' is one merged cell over {', '.join(headers[col:col + span])}")
            if with_params and headers[col] == "Name":
                row.update({f"__param_{k}": v for k, v in nested_params(td).items()})
            col += span
        if col < len(headers):
            row_notes.append(f"only {col} of {len(headers)} columns filled")
        row["row_note"] = "; ".join(row_notes)
        rows.append(row)
    flagged = sum(1 for r in rows if r["row_note"])
    if flagged:
        notes.append(f"{flagged} row(s) with a row_note")
    return headers, rows, notes


def read_param_tabs(soup: BeautifulSoup) -> dict[str, dict[str, tuple[str, str]]]:
    """{param: {Institute ID: (param score, param rank)}} from the 'By TLR / By RPC ...' tabs."""
    tabs: dict[str, dict[str, tuple[str, str]]] = {}
    for table_id, key in TAB_TABLE_IDS.items():
        table = soup.find("table", id=table_id)
        if table is None:
            continue
        headers = header_cells(table)
        score_col = next((i for i, h in enumerate(headers) if h.lower().endswith("score") and h.lower() != "score"), None)
        rank_col = next((i for i, h in enumerate(headers) if h.lower().endswith("rank") and h.lower() != "rank"), None)
        id_col = headers.index(ID_HEADER) if ID_HEADER in headers else None
        if None in (score_col, rank_col, id_col):
            continue
        entries: dict[str, tuple[str, str]] = {}
        for tr in own_rows(table):
            cells = [text_of(td) for td in tr.find_all("td", recursive=False) if not is_hidden(td)]
            if len(cells) > max(score_col, rank_col, id_col):
                entries.setdefault(cells[id_col], (cells[score_col], cells[rank_col]))
        tabs[key] = entries
    return tabs


def scores_equal(a: str, b: str) -> bool:
    try:
        return abs(float(a) - float(b)) < 0.005
    except ValueError:
        return a == b


# --------------------------------------------------------------------------- one page -> one CSV


def scrape_page(job: PageJob, html: bytes, scraped_at: str, entry: LogEntry) -> pd.DataFrame:
    soup = BeautifulSoup(html, "lxml")
    table = find_main_table(soup)
    if table is None:
        raise ValueError("no institution table found on the page")

    is_ranking = job.page_type == "ranking"
    headers, rows, notes = read_table(table, with_params=is_ranking)
    entry.notes.extend(notes)

    # Heading wording that differs from the main page label (kept for transparency).
    heading = page_heading(soup)
    if job.page_type == "band" and job.category_original and job.category_original not in heading:
        entry.notes.append(f"page heading says '{heading}'")

    param_cols: list[str] = []
    rank_cols: list[str] = []
    if is_ranking:
        found = []
        for row in rows:
            for key in [k[len("__param_"):] for k in row if k.startswith("__param_")]:
                if key not in found:
                    found.append(key)
        # Always the five standard columns (blank if not published); extra ones such as
        # Research's qnr/qlr/sfc are added in the order the site shows them.
        param_cols = STANDARD_PARAMS + [k for k in found if k not in STANDARD_PARAMS]
        for row in rows:
            for key in param_cols:
                row[key] = row.pop(f"__param_{key}", "")
        with_params = sum(1 for r in rows if any(r[k] for k in found))
        if found:
            labels = ", ".join(k.upper() for k in found)
            entry.notes.append(f"parameters {labels} on {with_params}/{len(rows)} rows")
        else:
            entry.notes.append("no parameter scores published on this page")

        tabs = read_param_tabs(soup)
        if tabs and ID_HEADER in headers:
            merged, mismatches, filled = 0, 0, 0
            for row in rows:
                hit = False
                for key, entries in tabs.items():
                    score, rank = entries.get(row[ID_HEADER], ("", ""))
                    row[f"{key}_rank"] = rank
                    if rank or score:
                        hit = True
                    if score and not row.get(key):
                        row[key] = score
                        filled += 1
                    elif score and not scores_equal(score, row[key]):
                        mismatches += 1
                        row["row_note"] = "; ".join(
                            filter(None, [row["row_note"], f"{key} tab score {score} vs hidden table {row[key]}"])
                        )
                merged += hit
            rank_cols = [f"{k}_rank" for k in tabs]
            entry.notes.append(f"parameter tabs {', '.join(tabs)} merged on Institute ID for {merged}/{len(rows)} rows")
            if filled:
                entry.notes.append(f"{filled} parameter value(s) filled from the tabs")
            if mismatches:
                entry.notes.append(f"{mismatches} tab score(s) differ from the hidden table")

        if ID_HEADER in headers:
            ids = pd.Series([r[ID_HEADER] for r in rows])
            dupes = ids[ids.duplicated() & ids.ne("")].unique()
            if len(dupes):
                entry.notes.append(f"duplicate Institute IDs: {', '.join(dupes)}")

        rank_header = next((h for h in headers if h in {"Rank", "Band"}), None)
        if rank_header:
            odd = sorted({r[rank_header] for r in rows if not r[rank_header].isdigit()})
            if odd:
                entry.notes.append(f"non-numeric {rank_header} values: {', '.join(odd)}")

    footnotes = sorted(
        {text_of(el) for el in soup.find_all(["h4", "h5", "p", "span"])
         if text_of(el).startswith("*") and len(text_of(el)) > 10 and not el.find_parent("table")}
    )
    entry.notes.extend(f"footnote: {f}" for f in footnotes)

    df = pd.DataFrame(rows)
    for col, value in {
        "year": job.year,
        "category_original": job.category_original,
        "category_slug": job.category_slug,
        "page_type": job.page_type,
        "rank_band": job.rank_band,
        "source_url": job.url,
        "scraped_at": scraped_at,
    }.items():
        df[col] = value
    if df.empty:
        df = pd.DataFrame(columns=META_FRONT + headers + param_cols + rank_cols + META_BACK)
    return df[META_FRONT + headers + param_cols + rank_cols + META_BACK]


def download_time(path: Path) -> str:
    """When the cached HTML was saved (UTC); this is when the data was actually scraped."""
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_job(session: requests.Session, job: PageJob, refresh: bool) -> LogEntry:
    entry = LogEntry(job.year, job.category_original or job.category_slug, job.file_stem, job.url)
    try:
        if job.discovery_error:
            raise RuntimeError(f"could not fetch page ({job.discovery_error})")
        # Category pages were already fetched (or refreshed) during discovery.
        html, fetch_status = get_html(session, job.url, job.html_path, refresh and job.page_type in {"band", "participants"})
        if html is None:
            raise RuntimeError(f"could not fetch page ({fetch_status})")
        entry.notes.append("html from cache" if fetch_status == "cached" else "html downloaded")
        df = scrape_page(job, html, download_time(job.html_path), entry)
        job.csv_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(job.csv_path, index=False, encoding="utf-8")
        entry.rows = len(df)
        entry.status = "ok" if len(df) else "empty"
    except Exception as exc:  # one bad page must never stop the run
        entry.status = "failed"
        where = traceback.extract_tb(exc.__traceback__)[-1]
        entry.notes.append(f"{type(exc).__name__}: {exc} (in {where.name}, line {where.lineno})")
    return entry


# --------------------------------------------------------------------------- summary


def print_summary(log: pd.DataFrame) -> None:
    ok = log[log["status"] == "ok"].copy()
    ok["kind"] = ok["page"].map(
        lambda p: "band" if "__band_" in p else "participants" if p.endswith("__participants") else "ranking"
    )
    years = sorted(log["year"].unique())
    labels = {"ranking": "Exact-rank rows (main page)", "band": "Rank-band rows", "participants": "Participant-list rows"}
    for kind, title in labels.items():
        part = ok[ok["kind"] == kind]
        if part.empty:
            continue
        part = part.assign(cat=part["page"].str.split("__").str[0])
        table = part.pivot_table(index="cat", columns="year", values="rows", aggfunc="sum").reindex(columns=years)
        table["total"] = table.sum(axis=1)
        table.loc["TOTAL"] = table.sum()
        print(f"\n{title}  (category x year)")
        print(table.fillna(0).astype(int).replace(0, "-").to_string())

    print("\nPages by status:", log["status"].value_counts().to_dict())
    print(f"Total rows written: {int(log['rows'].sum())}")
    bad = log[log["status"] != "ok"]
    if bad.empty:
        print("Nothing failed.")
    else:
        print("\nProblems:")
        print(bad[["year", "page", "status", "notes"]].to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--years", type=int, nargs="+", default=YEARS)
    parser.add_argument("--refresh", action="store_true", help="re-download pages even if cached")
    args = parser.parse_args()

    session = make_session()
    print("Finding pages (cached HTML is reused) ...")
    jobs = discover_jobs(session, args.years, args.refresh)
    print(f"{len(jobs)} pages to scrape.\n")

    entries: list[LogEntry] = []
    for i, job in enumerate(jobs, start=1):
        entry = run_job(session, job, args.refresh)
        entries.append(entry)
        flag = "" if entry.status == "ok" else f"  <-- {entry.status.upper()}: {entry.notes[-1] if entry.notes else ''}"
        print(f"[{i:3d}/{len(jobs)}] {job.year} {job.file_stem:<40} rows={entry.rows:5d}  {entry.status}{flag}")

    log = pd.DataFrame([e.as_row() for e in entries], columns=["year", "category", "page", "url", "rows", "status", "notes"])
    # Re-running for a subset of years keeps the other years' log lines.
    if LOG_PATH.exists() and set(args.years) != set(YEARS):
        old = pd.read_csv(LOG_PATH)
        log = pd.concat([old[~old["year"].isin(args.years)], log]).sort_values(["year"], kind="stable")
    log.to_csv(LOG_PATH, index=False, encoding="utf-8")
    print(f"\nLog written to {LOG_PATH.relative_to(ROOT)}")
    print_summary(log)


if __name__ == "__main__":
    main()
