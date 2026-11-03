# How our scraper works

Script: `scraper/scrape_nirf.py` · Run it with `python -m scraper.scrape_nirf`

## The idea in one sentence

The NIRF website shows its rankings as tables on web pages; our scraper saves each page, reads the table on it
and writes that table into a CSV file, without changing any values.

```
  nirfindia.org                 data/raw/html/                    (in memory)                data/raw/csv/
 +---------------+  download   +----------------+   read the    +----------------+   save   +------------------+
 |  web page     | ----------> |  HTML file     | ------------> |  table         | -------> |  CSV file        |
 |  (one per     |  only if    |  (saved copy,  |   <table>     |  rows x        |          |  one per page    |
 |  category,    |  not saved  |   never        |   + hidden    |  columns       |          |  + year, label,  |
 |  band, list)  |  already    |   changed)     |   parameters  |                |          |  url, time       |
 +---------------+             +----------------+               +----------------+          +------------------+
                                                                                                    |
                                                                                                    v
                                                                              data/raw/scrape_log.csv (one line per page)
```

## Step by step

1. **Find the pages.** We start at the NIRF home page, which links one index page per year. Each year's index
   page links its categories (Overall, Engineering, Medical ...). Each category page links two kinds of extra
   pages: rank-band pages ("Rank-band: 101-150") and the "List of Participating Institutions". We follow all of
   them. For 2017–2025 that is **290 pages**.
2. **Get the HTML (with a cache).** Every page we download is saved untouched in `data/raw/html/<year>/`. When
   the scraper runs again it reads the saved copy instead of downloading again. So the website is only asked
   once, and re-running is fast (seconds) and gives exactly the same files. New downloads are made politely:
   one at a time, with a 1–2 second pause and retries if the site is slow.
3. **Read the table.** On each page we find the institution table and read every row. The values are kept as
   the original text, so special ranks such as `21A` or `Rank Withdrawn` are not lost. Cleaning them is a
   later step (`pipeline/`), not the scraper's job.
4. **Pick up the five parameter scores.** On ranking pages the scores for TLR, RPC, GO, OI and Perception are
   hidden inside the Name cell (the site shows them when you click "More Details"). We read that hidden
   mini-table and put the numbers into the columns `tlr, rpc, go, oi, pr`.
   In 2017 and 2018 (and on the University page every year) the page also has tabs "By TLR", "By RPC" ...
   which add each institution's **rank on that parameter**. We read those tabs too and join them to the main
   table using the Institute ID (columns `tlr_rank ... pr_rank`). The tab scores are checked against the
   hidden scores: they matched on every row.
5. **Save one CSV per page** in `data/raw/csv/<year>/`, using the same name as the saved HTML page, e.g.
   `engineering.csv`, `engineering__band_101-150.csv`, `engineering__participants.csv`.
6. **Write the log and a summary.** `data/raw/scrape_log.csv` has one line per page with the number of rows,
   a status (`ok`, `empty` or `failed`) and notes about anything unusual. At the end the script prints the
   number of rows for every year × category.

## What is inside each CSV

| Column | Meaning |
|---|---|
| `year` | Ranking year (2017–2025). |
| `category_original` | The category name exactly as NIRF wrote it in that year's page heading, e.g. "Research" (2021–2023) but "Research Institutions" (2024–2025). We keep it so history stays honest. |
| `category_slug` | Our short, fixed name for the category (`research`, `architecture` ...), the same in every year. |
| `page_type` | `ranking` (main page with exact ranks), `band` (rank-band page), `participants` (list of participating institutions) or `special_mention` (2018 only). |
| `rank_band` | For band pages, the band from the link text, e.g. `101-150`. |
| *site columns* | The table's own columns with their own names: usually `Institute ID, Name, City, State, Score, Rank`; band and participant pages only have `Name, City, State`. |
| `tlr, rpc, go, oi, pr` | The five parameter scores (out of 100) on ranking pages; blank where NIRF did not publish them. |
| `qnr, qlr, sfc` | Research Institutions only: NIRF uses different parameters there, so they get their own columns and are never mixed with TLR/RPC/GO. |
| `tlr_rank ... pr_rank` | Rank on each parameter, only where the page has the parameter tabs. |
| `row_note` | Anything odd about that row (see below). Usually empty. |
| `source_url` | The exact page the row came from. |
| `scraped_at` | When that page was downloaded (UTC). |

## Odd cases it handles

- **Ties.** Two institutions with the same rank (e.g. two at 100 in Overall 2020) are kept as they are.
- **Ranks like `21A`, `26A`, `16A`** (2018) and **`Rank Withdrawn`** (2018 College) are kept as text.
- **Merged cells.** 2025 Dental shows "Rank Withdrawn*" stretched across the Score and Rank columns. We put the
  text in `Rank`, leave `Score` blank and write a `row_note`. That row also has an invisible cell holding `18`;
  it is not shown on the site, so it does not go into a column, but it is kept in the `row_note`.
- **Footnotes** on a page (like the one explaining the Dental withdrawal) are copied into the log notes.
- **Different names for the same category** (e.g. "State Public University" vs "State Public Universities")
  stay visible in `category_original` and the log.

## Safety: it does not break

Each page is handled on its own. If one page cannot be downloaded or read, it is written to the log as
`failed` with the reason, and the scraper moves on to the next page. We tested this with a fake missing page
and a fake page without a table: both were logged as `failed` and the run continued.

## Result of our run (3 November 2026)

- 290 pages, all `ok`, nothing failed, 75,626 rows in total.
- 6,980 rows with an exact rank (main pages), 4,671 rows inside rank bands, 63,975 rows in participant lists.
- Parameter scores on every scored row (one exception: the withdrawn 2025 Dental row, which has none on the site).
- Categories with no parameter scores on the site: Innovation, Open University, Skill University,
  SDG Institutions (rank only).

## How to run and check it

```bash
python -m scraper.scrape_nirf                   # all years, uses the saved HTML
python -m scraper.scrape_nirf --years 2025      # one year
python -m scraper.scrape_nirf --refresh         # download everything again (only if the site changed)
```

Then open `data/raw/scrape_log.csv` (every status should be `ok`) and any CSV in `data/raw/csv/<year>/`.
