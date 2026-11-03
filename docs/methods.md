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

_Cleaning and standardising: to be filled in during the cleaning phase._

## Analyses

_To be filled in as engines are built._
