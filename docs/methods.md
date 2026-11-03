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

### Step 3: cleaning and integration (`pipeline/clean.py` → `data/processed/nirf_master.parquet`)
- **What:** all 290 raw CSVs become one master table with one row per (year, category, institution):
  11,647 ranked rows (6,976 with an exact rank, 4,671 known only by rank band), 2017–2025, 17 categories.
  Participant lists (63,975 rows) and the 2018 Special Mention page go to a separate
  `nirf_participants.parquet`, so they are never counted as ranked. Full numbers and examples per step:
  `docs/cleaning_report.md`.
- **How (plain words), in order:**
  1. *Combine* every CSV; 2. *rename* columns to snake_case (`Institute ID` → `institute_id`, the 2023
     Innovation `Band` column → `rank_raw`); 3. *year* to integer.
  4. *Category:* `data/mappings/category_map.csv` maps each (label, year) to one standard name
     ("Research" 2021–23 and "Research Institutions" 2024–25 → Research Institutions). The published
     label stays in `category_original`.
  5. *State:* `data/mappings/state_map.csv` maps all 49 raw spellings to the 34 official states/UTs
     (Pondicherry → Puducherry) and adds a region (MHA zonal councils + North-East).
  6. *Text tidy:* spaces, commas, hyphens, broken apostrophes (`` ` `` → '), PIN codes, UPPER CASE.
  7. *Institution identity* (`pipeline/identity.py`): a matching key per name (lower case, & → and,
     no punctuation, "Govt" → "government", "Bangalore" → "bengaluru"); same key + same state = same
     institution (+ city when one name means two colleges in one state). Then links by NIRF ID code
     (stable from 2018), hand alias rules, "name = other name + its own city", and rapidfuzz
     `token_sort_ratio` ≥ 92 in the same state. Pairs scoring 80–92, or ≥ 92 with something against
     them (each name has its own different word, different cities, different ID codes), go to
     `data/mappings/institution_review.csv` for a human `approve = yes/no`, read back on the next run.
     Two rows of the same ranking list are never merged. `canonical_name` = the most recent name.
  8. *Rank:* `rank_raw` kept; `rank` = exact integer (ties share it, `is_tie`); `21A`-style ranks keep
     their number and are flagged `lettered`; withdrawn ranks stay empty. Every row gets a standard
     `rank_band` (1-10, 11-25, 26-50, 51-100, 101-150, 151-200, 201-300) and `in_top10/50/100`.
  9. *Numbers:* scores to decimals; anything outside 0–100 would become NaN (0 found).
  10. *Missing values:* never filled in; `has_score` / `has_parameter_scores` flags + a reason table.
  11. *Duplicates:* exact copies and repeated (year, category, institution) dropped (0 found).
  12. *Derived:* `first_year_seen`, `is_new_entrant`, `years_present` (per institution per category).
- **Why this way:** each rule fixes a problem the audit proved exists, can be explained in one sentence,
  and never invents data. Hand-checked tables (`data/mappings/`) are inputs, so a new spelling in a future
  scrape stops the pipeline instead of being guessed. Banded institutions get no exact rank (no
  mid-points), and only certain facts are derived from bands (a 76-100 row is surely in the top 100).
- **Checks:** `tests/test_master.py` (one row per key, ranges, ties, known renames such as UPES and IISc,
  same-name colleges kept apart).

## Analyses

_To be filled in as engines are built._
