# Methods: how every chart is calculated

Viva study material. One entry per chart/analysis, added as each engine is built.
Conventions used everywhere: a smaller rank is better; improvement = old_rank − new_rank (positive = moved up);
scores are only compared within the same category unless a visible note says otherwise.

## Template

### Q<x.y>: <question>
- **Engine / function:** `core/engines/<engine>.py :: <function>()`
- **Definition used:** <what exactly "top 100", "improvement", "unusual" ... mean here>
- **Calculation (plain words):** <step by step>
- **Chart and why:** <chart type, and why it suits this question>
- **Filters the user can change:** <years, category, states, institutions, parameters, top_n>

## Data processing

### Step 1: scraping (`scraper/scrape_nirf.py`)
- **What:** every NIRF page for 2017–2025 (290 pages: ranking pages, rank-band pages, participant lists and
  the 2018 Special Mention page) becomes one CSV in `data/raw/csv/<year>/`.
- **How (plain words):** save each page's HTML once, read its institution table row by row, keep every value as
  the original text, and add the year, the category label NIRF used, the page URL and the download time.
  The five parameter scores are read from the hidden "More Details" table in each Name cell; where the page has
  "By TLR / By RPC ..." tabs, the per-parameter ranks are joined on the Institute ID.
- **Why this way:** keeping raw text means nothing is guessed or lost at this stage (e.g. `21A`,
  `Rank Withdrawn`); all cleaning happens in the next step, where it can be checked and explained.
- **Checks:** `data/raw/scrape_log.csv` lists rows, status and notes per page. Full explanation:
  `docs/explanations/scraper.md`.

### Step 2: data audit (`pipeline/audit.py` → `docs/data_audit.md`)
- **What:** a read-only check of all 290 raw CSVs before any cleaning. It counts rows per year × category,
  compares column names and category labels across years, lists every State spelling, every rank format
  (plain, tied, `21A`, `Rank Withdrawn`, bands), missing values, duplicates and name variants, and ends
  with a ranked list of cleaning problems and proposed fixes.
- **How (plain words):**
  - *Missing values* are counted only in files that have the column, so "not published" (Research has no
    TLR) is kept apart from "blank cell".
  - *Rank sequence:* NIRF uses competition ranking (1, 2, 2, 4), so a rank number may only be missing right
    after a tie. Any other missing number is reported.
  - *Name variants:* names are normalised (lower case, `&` → `and`, punctuation removed) and every pair is
    compared with rapidfuzz `token_sort_ratio`: sort the words of each name, then measure how many
    character edits turn one into the other, as a 0–100 similarity. Pairs ≥ 88, in the same state, in
    different years and never in the same list are candidates. The NIRF ID code (stable from 2018,
    e.g. `U-0456` = IIT Madras) is used as ground truth to confirm or reject them.
- **Why this way:** every cleaning rule must rest on evidence we can show. The ID-code check shows that fuzzy
  matching alone both misses real renames (UPES, Krea) and wrongly merges different campuses, which is why
  the alias table will be hand-checked.

_Cleaning and standardising: to be filled in during the cleaning phase._

## Analyses

_To be filled in as engines are built._
