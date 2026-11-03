"""Source reconnaissance for nirfindia.org (Phase 1).

What it does, for every year 2017-2025:
  1. Finds that year's ranking index page (from the links on the nirfindia.org home page)
     and lists every ranking category linked from it, with its URL.
  2. Downloads each category page ONCE into data/raw/html/<year>/<category_slug>.html.
     It also follows the two kinds of sub-pages linked from a category page:
       - "Rank-band: 101-150" style pages  -> <category_slug>__band_101-150.html
       - "List of Participating Institutions" -> <category_slug>__participants.html
     A file that is already cached is never downloaded again (delete it to force a refresh).
  3. Inspects every page and reports: institution rows, column headers, whether the five
     parameter scores (TLR, RPC, GO, OI, Perception) are present and how they are embedded,
     and which rank formats appear (plain numbers, bands such as "101-150", blanks ...).

Why: before writing the real scraper we need to know exactly how the site is laid out and
where the years differ. The findings are written to data/raw/source_inventory.json and are
summarised by hand in docs/source_map.md.

Politeness: one request at a time, a random 1-2 second pause between requests, a normal
browser User-Agent, a timeout on every request and retries with exponential backoff.

Run from the project root:
    python -m scraper.explore_source            # all years
    python -m scraper.explore_source --years 2024 2025
    python -m scraper.explore_source --markdown # also print the year x category table
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import re
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

BASE_URL = "https://www.nirfindia.org/"
YEARS = list(range(2017, 2026))

ROOT = Path(__file__).resolve().parents[1]
HTML_DIR = ROOT / "data" / "raw" / "html"
INVENTORY_PATH = ROOT / "data" / "raw" / "source_inventory.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
TIMEOUT_S = 60
MAX_RETRIES = 4
DELAY_RANGE_S = (1.0, 2.0)

# Index-page links look like "OverallRanking.html", "OPENUNIVERSITYRanking.html",
# "SDGInstitutionsRanking.html" or (2018 only) "SpecialRank.html".
CATEGORY_LINK_RE = re.compile(r"([A-Za-z]+?)Rank(?:ing)?\.html$")

# Readable slugs/labels for the file-name stems NIRF uses. Unknown stems fall back to a
# lower-cased stem so a new category can never be silently dropped.
KNOWN_CATEGORIES = {
    "Overall": ("overall", "Overall"),
    "University": ("university", "University"),
    "College": ("college", "College"),
    "Research": ("research", "Research Institutions"),
    "Engineering": ("engineering", "Engineering"),
    "Management": ("management", "Management"),
    "Pharmacy": ("pharmacy", "Pharmacy"),
    "Medical": ("medical", "Medical"),
    "Dental": ("dental", "Dental"),
    "Law": ("law", "Law"),
    "Architecture": ("architecture", "Architecture and Planning"),
    "Agriculture": ("agriculture", "Agriculture and Allied Sectors"),
    "Innovation": ("innovation", "Innovation"),
    "OPENUNIVERSITY": ("open_university", "Open University"),
    "SKILLUNIVERSITY": ("skill_university", "Skill University"),
    "STATEPUBLICUNIVERSITY": ("state_public_university", "State Public University"),
    "SDGInstitutions": ("sdg_institutions", "SDG Institutions"),
    "Special": ("special_mention", "Special Mention (2018, unranked)"),
}

PARAM_KEYS = ("TLR", "RPC", "GO", "OI", "PR")
BAND_RE = re.compile(r"^\d+\s*-\s*\d+$")
BAND_LINK_TEXT_RE = re.compile(r"Rank-?band\s*:?\s*(\d+)\s*-\s*(\d+)", re.I)
PARTICIPANTS_TEXT_RE = re.compile(r"participating institutions", re.I)
NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?$")

log = logging.getLogger("explore_source")


# --------------------------------------------------------------------------- HTTP


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-IN,en;q=0.9",
        }
    )
    return session


def polite_get(session: requests.Session, url: str) -> requests.Response:
    """GET with a 1-2 s pause before each request and exponential backoff on failure."""
    for attempt in range(1, MAX_RETRIES + 1):
        time.sleep(random.uniform(*DELAY_RANGE_S))
        try:
            response = session.get(url, timeout=TIMEOUT_S)
            if response.status_code == 404:
                return response  # a real "not found": retrying will not help
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            if attempt == MAX_RETRIES:
                raise
            wait = 2**attempt
            log.warning("  %s failed (%s); retry %d in %ds", url, exc, attempt, wait)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def fetch_cached(session: requests.Session, url: str, path: Path) -> tuple[bytes | None, str]:
    """Return (raw bytes, status). Uses the cache when present; never re-downloads."""
    if path.exists():
        return path.read_bytes(), "cached"
    log.info("  downloading %s", url)
    try:
        response = polite_get(session, url)
    except requests.RequestException as exc:
        return None, f"error: {exc}"
    if response.status_code != 200:
        return None, f"http {response.status_code}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)  # untouched bytes, exactly as served
    return response.content, "downloaded"


# --------------------------------------------------------------------------- discovery


def find_year_index_urls(home_html: bytes) -> dict[int, str]:
    """Map year -> index URL using the 'Rankings/<year>/...html' links on the home page."""
    soup = BeautifulSoup(home_html, "lxml")
    found: dict[int, str] = {}
    for a in soup.find_all("a", href=True):
        match = re.search(r"Rankings/(\d{4})/[^/]+\.html$", a["href"])
        if match:
            found.setdefault(int(match.group(1)), urljoin(BASE_URL, a["href"]))
    return found


def fallback_index_urls(year: int) -> list[str]:
    return [
        f"{BASE_URL}Rankings/{year}/Ranking{year}.html",
        f"{BASE_URL}Rankings/{year}/Ranking.html",
    ]


def category_from_stem(stem: str) -> tuple[str, str]:
    if stem in KNOWN_CATEGORIES:
        return KNOWN_CATEGORIES[stem]
    slug = re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")
    return slug, stem


def list_categories(index_html: bytes, index_url: str) -> list[dict]:
    """Every category page linked from a year's index page, in page order, de-duplicated."""
    soup = BeautifulSoup(index_html, "lxml")
    categories, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        match = CATEGORY_LINK_RE.search(href)
        if not match or re.search(r"Ranking\d{4}\.html$|/Ranking\.html$|^Ranking\.html$", href):
            continue  # skip links back to an index page itself
        url = urljoin(index_url, href)
        if url in seen:
            continue
        seen.add(url)
        slug, label = category_from_stem(match.group(1))
        categories.append({"slug": slug, "label": label, "url": url})
    return categories


def list_subpages(category_html: bytes, category_url: str, slug: str) -> list[dict]:
    """Rank-band and participant-list pages linked from a category page.

    The band is read from the LINK TEXT, not the file name: e.g. in 2020 the file
    EngineeringRanking150.html holds the band "201-250".
    """
    soup = BeautifulSoup(category_html, "lxml")
    subpages, seen = [], set()
    for a in soup.find_all("a", href=True):
        label = " ".join(a.get_text(" ", strip=True).split())
        band = BAND_LINK_TEXT_RE.search(label)
        if band:
            kind, band_label = "band", f"{band.group(1)}-{band.group(2)}"
            file_stem = f"{slug}__band_{band_label}"
        elif PARTICIPANTS_TEXT_RE.search(label):
            kind, band_label, file_stem = "participants", None, f"{slug}__participants"
        else:
            continue
        url = urljoin(category_url, a["href"].strip())
        if url in seen:
            continue
        seen.add(url)
        subpages.append({"kind": kind, "band": band_label, "link_text": label, "url": url, "file_stem": file_stem})
    return subpages


# --------------------------------------------------------------------------- page analysis


def text_of(node: Tag) -> str:
    return " ".join(node.get_text(" ", strip=True).split())


def own_rows(table: Tag) -> list[Tag]:
    """Rows belonging to this table only (not to tables nested inside its cells)."""
    return [tr for tr in table.find_all("tr") if tr.find_parent("table") is table]


def header_cells(table: Tag) -> list[str]:
    for tr in own_rows(table):
        ths = tr.find_all("th", recursive=False)
        if ths:
            return [text_of(th) for th in ths]
    return []


def classify_value(value: str, kind: str) -> str:
    if value == "":
        return "blank"
    if kind == "rank":
        if value.isdigit():
            return "integer"
        if BAND_RE.match(value):
            return "band"
    if kind == "score" and NUMBER_RE.match(value):
        return "number"
    if value in {"-", "--", "NA", "N/A"}:
        return f"placeholder '{value}'"
    return "other"


def find_col(headers: list[str], *names: str) -> int | None:
    lowered = [h.lower() for h in headers]
    for name in names:
        if name.lower() in lowered:
            return lowered.index(name.lower())
    return None


def param_key(header: str) -> str | None:
    h = header.upper()
    if h.startswith("PERCEPTION") or h.startswith("PR"):
        return "PR"
    for key in PARAM_KEYS:
        if h.startswith(key):
            return key
    return None


@dataclass
class TableReport:
    table_id: str | None
    heading: str
    headers: list[str]
    rows: int
    rank_formats: dict[str, int] = field(default_factory=dict)
    rank_examples: list[str] = field(default_factory=list)
    score_formats: dict[str, int] = field(default_factory=dict)
    nested_param_headers: list[str] = field(default_factory=list)
    rows_with_nested_params: int = 0
    nested_param_value_formats: dict[str, int] = field(default_factory=dict)
    nested_in_hidden_div: bool = False
    score_examples: list[str] = field(default_factory=list)
    id_patterns: dict[str, int] = field(default_factory=dict)
    special_rows: list[list[str]] = field(default_factory=list)
    hidden_cells: int = 0
    rows_with_pdf_link: int = 0
    first_row: list[str] = field(default_factory=list)


def analyse_table(table: Tag) -> TableReport:
    headers = header_cells(table)
    heading_tag = table.find_previous(["h1", "h2", "h3", "h4", "h5"])
    report = TableReport(
        table_id=table.get("id"),
        heading=text_of(heading_tag) if heading_tag else "",
        headers=headers,
        rows=0,
    )
    rank_col = find_col(headers, "Rank", "Band")
    score_col = find_col(headers, "Score")
    id_col = find_col(headers, "Institute ID")
    rank_fmt, score_fmt, nested_fmt, id_fmt = Counter(), Counter(), Counter(), Counter()
    rank_examples: list[str] = []

    for tr in own_rows(table):
        cells = tr.find_all("td", recursive=False)
        if not cells:
            continue  # header row
        report.rows += 1
        # A cell's "own" text excludes any nested parameter table inside it.
        own_text = []
        for td in cells:
            clone = BeautifulSoup(str(td), "lxml").td
            for inner in clone.find_all(["table", "div"]):
                inner.decompose()
            own_text.append(text_of(clone))
        if report.rows == 1:
            report.first_row = own_text

        if id_col is not None and id_col < len(own_text):
            # Shape of the ID with digits replaced by "9", e.g. IR-O-U-0456 -> IR-O-U-9999.
            id_fmt[re.sub(r"\d", "9", own_text[id_col])] += 1
        if rank_col is not None and rank_col < len(own_text):
            value = own_text[rank_col]
            fmt = classify_value(value, "rank")
            rank_fmt[fmt] += 1
            if fmt != "integer" and value not in rank_examples and len(rank_examples) < 8:
                rank_examples.append(value)
        if score_col is not None and score_col < len(own_text):
            value = own_text[score_col]
            fmt = classify_value(value, "score")
            score_fmt[fmt] += 1
            if fmt != "number" and value not in report.score_examples:
                report.score_examples.append(value)
        # Rows that do not follow the normal layout (merged cells, e.g. "Rank Withdrawn*").
        if any(td.get("colspan") for td in cells) or len(cells) != len(headers):
            report.special_rows.append(own_text)
        report.hidden_cells += sum("display:none" in (td.get("style") or "").replace(" ", "") for td in cells)

        nested = tr.find("table")
        if nested is not None:
            report.rows_with_nested_params += 1
            if not report.nested_param_headers:
                report.nested_param_headers = header_cells(nested)
            if nested.find_parent("div", class_="tbl_hidden") is not None:
                report.nested_in_hidden_div = True
            for td in nested.find_all("td"):
                nested_fmt[classify_value(text_of(td), "score")] += 1
        if tr.find("a", href=re.compile(r"\.pdf$", re.I)):
            report.rows_with_pdf_link += 1

    report.rank_formats = dict(rank_fmt)
    report.rank_examples = rank_examples
    report.score_formats = dict(score_fmt)
    report.nested_param_value_formats = dict(nested_fmt)
    report.id_patterns = dict(id_fmt.most_common(6))
    return report


def describe_param_embedding(tables: list[TableReport]) -> tuple[bool, str]:
    """Plain-English description of where the five parameter scores live on a page."""
    nested = [t for t in tables if t.rows_with_nested_params]
    separate = [t for t in tables if t.table_id and t.table_id.lower() in {f"tbl_{k.lower()}" for k in PARAM_KEYS}]
    in_columns = [t for t in tables if sum(param_key(h) is not None for h in t.headers) >= 3 and t not in separate]
    parts = []
    if nested:
        t = nested[0]
        where = "inside a hidden <div class='tbl_hidden'>" if t.nested_in_hidden_div else "inside the row"
        parts.append(
            f"nested <table> in the Name cell {where} (opened by 'More Details'), "
            f"headers {t.nested_param_headers}, present on "
            f"{sum(x.rows_with_nested_params for x in nested)} rows"
        )
    if separate:
        ids = ", ".join(t.table_id for t in separate)
        parts.append(f"separate per-parameter tables ({ids}), each with '<P> Score' and '<P> Rank' columns")
    if in_columns:
        parts.append(f"parameter columns directly in the main table: {in_columns[0].headers}")
    return bool(parts), "; ".join(parts) if parts else "no parameter scores on the page"


def analyse_page(html: bytes) -> dict:
    soup = BeautifulSoup(html, "lxml")
    top_tables = [t for t in soup.find_all("table") if t.find_parent("table") is None]
    reports = [analyse_table(t) for t in top_tables]
    # Institution tables are the ones with a Name column. Rank-band and participant pages
    # have only Name / City / State, so "Institute ID" cannot be used as the marker.
    ranking = [r for r in reports if find_col(r.headers, "Name") is not None]
    main = [r for r in ranking if not (r.table_id or "").lower().startswith(("tbl_tlr", "tbl_rpc", "tbl_go", "tbl_oi", "tbl_pr"))]
    has_params, how = describe_param_embedding(ranking)
    rank_formats: Counter = Counter()
    id_patterns: Counter = Counter()
    for r in main:
        rank_formats.update(r.rank_formats)
        id_patterns.update(r.id_patterns)
    title = soup.find("title")
    # Footnotes such as "*The Faculty of Dental Sciences ... submitted the data independently".
    footnotes = sorted(
        {text_of(el) for el in soup.find_all(["h4", "h5", "p", "span", "div"])
         if text_of(el).startswith("*") and not el.find_parent("table") and len(text_of(el)) > 10}
    )
    headings = [text_of(h) for h in soup.find_all(["h2", "h3"]) if text_of(h)]
    return {
        "page_title": text_of(title) if title else "",
        "headings": headings[:10],
        "footnotes": footnotes,
        "special_rows": [row for r in main for row in r.special_rows],
        "institution_rows": sum(r.rows for r in main),
        "main_tables": len(main),
        "headers": main[0].headers if main else [],
        "params_present": has_params,
        "params_embedding": how,
        "rank_formats": dict(rank_formats),
        "rank_examples": sorted({e for r in main for e in r.rank_examples}),
        "score_examples": sorted({e for r in main for e in r.score_examples}),
        "id_patterns": dict(id_patterns.most_common(6)),
        "tables": [asdict(r) for r in reports],
    }


# --------------------------------------------------------------------------- driver


def explore(years: list[int]) -> dict:
    session = make_session()
    HTML_DIR.mkdir(parents=True, exist_ok=True)

    home_html, status = fetch_cached(session, BASE_URL, HTML_DIR / "_home.html")
    log.info("home page: %s", status)
    index_urls = find_year_index_urls(home_html) if home_html else {}

    inventory: dict = {"source": BASE_URL, "years_linked_from_home": sorted(index_urls), "years": {}}
    for year in years:
        log.info("== %d", year)
        candidates = [index_urls[year]] if year in index_urls else fallback_index_urls(year)
        index_html, index_url, index_status = None, None, "not found"
        for url in candidates:
            index_html, index_status = fetch_cached(session, url, HTML_DIR / str(year) / "_index.html")
            if index_html:
                index_url = url
                break
        year_entry: dict = {"index_url": index_url, "index_status": index_status, "categories": []}
        inventory["years"][str(year)] = year_entry
        if not index_html:
            log.warning("  no index page for %d (%s)", year, index_status)
            continue

        for cat in list_categories(index_html, index_url):
            html, status = fetch_cached(session, cat["url"], HTML_DIR / str(year) / f"{cat['slug']}.html")
            entry = {**cat, "status": status, "subpages": []}
            year_entry["categories"].append(entry)
            if not html:
                log.warning("  %-24s %s", cat["slug"], status)
                continue
            entry.update(analyse_page(html))
            log.info(
                "  %-24s rows=%4d params=%s ranks=%s",
                cat["slug"], entry["institution_rows"], entry["params_present"], entry["rank_formats"],
            )
            for sub in list_subpages(html, cat["url"], cat["slug"]):
                sub_html, sub_status = fetch_cached(session, sub["url"], HTML_DIR / str(year) / f"{sub['file_stem']}.html")
                sub_entry = {**sub, "status": sub_status}
                if sub_html:
                    sub_entry.update(analyse_page(sub_html))
                    log.info(
                        "      %-34s rows=%4d params=%s ranks=%s",
                        sub["file_stem"], sub_entry["institution_rows"], sub_entry["params_present"],
                        sub_entry["rank_formats"],
                    )
                else:
                    log.warning("      %-34s %s", sub["file_stem"], sub_status)
                entry["subpages"].append(sub_entry)

    INVENTORY_PATH.write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("inventory written to %s", INVENTORY_PATH.relative_to(ROOT))
    return inventory


def markdown_matrix(inventory: dict) -> str:
    """Year x category table: a tick + row count + link where the page exists, a cross otherwise."""
    years = sorted(inventory["years"])
    labels: dict[str, str] = {}
    for y in years:
        for c in inventory["years"][y]["categories"]:
            labels.setdefault(c["slug"], c["label"])
    lines = ["| Category | " + " | ".join(years) + " |", "|---|" + "---|" * len(years)]
    for slug, label in labels.items():
        cells = []
        for y in years:
            match = next((c for c in inventory["years"][y]["categories"] if c["slug"] == slug), None)
            if match and match.get("status") in {"cached", "downloaded"}:
                bands = [s for s in match["subpages"] if s["kind"] == "band" and s.get("institution_rows")]
                extra = f" +{sum(s['institution_rows'] for s in bands)} banded" if bands else ""
                cells.append(f"[✓ {match['institution_rows']}{extra}]({match['url']})")
            elif match:
                cells.append(f"⚠ {match['status']}")
            else:
                cells.append("✗")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--years", type=int, nargs="+", default=YEARS)
    parser.add_argument("--markdown", action="store_true", help="print the year x category table")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    inventory = explore(args.years)
    if args.markdown:
        print()
        print(markdown_matrix(inventory))


if __name__ == "__main__":
    main()
