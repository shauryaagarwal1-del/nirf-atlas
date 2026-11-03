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

### Step 4: validation (`tests/test_data.py`, `pipeline/spot_check.py`)
- **What:** automatic tests that compare the master table with things *outside* the cleaning code, plus a
  side-by-side check against the original web pages for a person to read.
- **How (plain words):**
  1. *No duplicates:* no (year, category, institution) appears twice.
  2. *States:* every state is one of India's 28 states + 8 UTs, typed into the test from the official list
     (not read from our own `state_map.csv`, so a wrong mapping would be caught).
  3. *Ranges:* score and the five parameters are between 0 and 100 wherever they exist.
  4. *Rank agrees with score:* inside each category-year, nobody has a score more than 0.01 (rounding) above
     someone ranked better. Institutions sharing a rank number (ties, `21A`) are not compared with each other.
  5. *Coverage:* every year 2017–2025 is present, and the categories of each year are exactly the ticks in
     the year × category table of `docs/source_map.md` (Special Mention 2018 excluded: it is not a ranking).
  6. *Nothing silently lost:* for every (year, category), master rows = rows on the raw ranking and band
     pages − rows logged in `data/processed/dropped_duplicates.csv`. A second test checks that the raw CSVs
     still hold the row counts `data/raw/scrape_log.csv` recorded.
  7. *Spot check:* `python -m pipeline.spot_check` picks 15 random master rows, re-reads the same institution
     from the saved HTML page with its own small parser (not the scraper's code) and prints both versions
     with a verdict per field: `same`, `cleaned` (only case/spacing/punctuation/PIN codes differ),
     `standardised` (state spelling → official name) or `DIFF`.
- **Result (3 Nov 2026):** all tests pass. The spot check run on *all* 11,647 rows found 0 real differences (116,470 fields compared)
  and 0 institutions missing from their page: every difference was an intended cleaning (487 tidied names
  and cities, 104 states renamed, e.g. Pondicherry → Puducherry).
- **Why:** the examiner sees numbers only through our charts, so we must be able to show that every number
  in the master table is the number NIRF printed, and that no row was dropped without a record.

## Analyses

### Shared building blocks (`core/`)
- **`core/data.py`:** `load_master()` reads the master table once and adds `rank_upper` = the worst rank a row can
  have (the exact rank, or the upper end of NIRF's own band). `filter_df()` narrows it by years, categories, states,
  institutions, `rank_max` and `exact_ranks_only`. Names typed by a person ("IIT Madras", "iisc", small typos) are
  matched to one `institution_key`: exact name → all typed words appear in the name → close spelling (rapidfuzz
  WRatio ≥ 90 and clearly ahead of the next candidate). If several institutions fit, the message lists them.
- **"In the top N" (used everywhere):** the rank is *certainly* N or better: exact rank ≤ N, or a NIRF band whose
  worst rank ≤ N. A 76-100 row is in the top 100; a 101-150 row is not; a 51-75 row is in the top 75.
- **Exact ranks only:** whenever a rank must be used as a number (subtracting, averaging, box plots of ranks), rows
  with only a band are left out and the method text says how many.
- **`core/theme.py`:** one Plotly template `nirf` (light surface, hairline grid, 2 px lines, 8 px markers), a
  colour-blind-safe 8-colour categorical palette in a fixed order (groups beyond 7–8 are folded into "Other"), one
  blue light→dark scale for amounts, blue (up / gained) vs red (down / lost) for changes, and `add_source_note()`,
  which writes "Source: NIRF, Ministry of Education, Govt. of India" under every chart.
- **`core/result.py`:** every engine returns `ChartResult(fig, table, insight, method, chart_type)`.
- **`core/stats.py`:** summary statistics, Pearson/Spearman correlation, R², p-value and the least-squares line.
  Strength words: |r| < 0.2 very weak, < 0.4 weak, < 0.6 moderate, < 0.8 strong, otherwise very strong.

### Q1.1: How has the overall NIRF ranking of a selected institution changed from 2017 to 2025?
- **Engine / function:** `core/engines/trends.py :: rank_trajectory()`
- **Definition used:** the rank NIRF published for the institution in the chosen category, each year.
- **Calculation (plain words):** look up the institution's row for every year. Exact ranks are joined by a line; a
  year with only a band (e.g. 101-150) is drawn as a faint bar covering the band (no invented mid-point); a year
  without a rank is a gap. Change = first exact rank − last exact rank (positive = moved up).
- **Chart and why:** line chart, because the question is change over time; the rank axis is reversed so "up = better".
- **Filters the user can change:** institutions (up to 8, default the top 5 of the latest year), category, years.

### Q1.2 / Q1.3 / Q7.4: Which institutions improved / declined the most in rank?
- **Engine / function:** `trends.py :: biggest_movers(category, start_year, end_year, direction, n)`
- **Definition used:** improvement = rank in start year − rank in end year (positive = moved up).
- **Calculation (plain words):** keep institutions with an exact rank in both years (a band cannot be subtracted;
  the method text says how many were left out), subtract, sort, keep the n largest climbs (`up`), falls (`down`)
  or both.
- **Chart and why:** diverging horizontal bar (blue = up, red = down) around zero, labelled "old → new rank"; bars
  compare amounts and the zero line separates climbers from fallers.
- **Filters the user can change:** category, start and end year (default: the category's first and last year),
  direction, n.
- **Caveat:** the length of the exact-rank list changes (Engineering ranked 200 exactly in 2019–2022, 100 otherwise).

### Q1.4 / Q6.4: How has the average score (and its median and IQR) changed over time?
- **Engine / function:** `trends.py :: average_score_over_time(categories, stat, top_n)`
- **Definition used:** per category and year, the mean or median of the published overall scores, and Q1 to Q3.
- **Calculation (plain words):** mean = sum / count, median = middle value; Q1 and Q3 = 25th and 75th percentiles.
  `top_n=100` keeps only exact ranks 1–100, so years with longer lists (Engineering 2019–22: 200) are comparable;
  the insight warns when the number of scored institutions changes.
- **Chart and why:** line for the mean/median with a shaded band from Q1 to Q3: the line shows the level, the band the
  spread of the middle half. With several categories a visible "not comparable across categories" note is added.
- **Filters the user can change:** one or more categories, mean/median, top_n.

### Q1.5: Which institutions have remained consistently in the top 10 across multiple years?
- **Engine / function:** `trends.py :: consistent_top_n(category, n, min_years)`
- **Definition used:** "in the top n" as defined above; consistent = at least `min_years` such years.
- **Calculation (plain words):** count the years each institution was in the top n, keep those with ≥ min_years, sort
  by that count, then by average rank in those years.
- **Chart and why:** heatmap institution × year: dark cell (with the rank written in it) = in the top n, light grey =
  ranked but outside, blank = not ranked. It shows "how often" and "which years" at a glance.
- **Filters the user can change:** category, n, min_years.

### Q2.1: Which states have the highest number of institutions in the top 100?
- **Engine / function:** `core/engines/geography.py :: state_counts(year, category, top_n)`
- **Definition used:** institutions of each state certainly in the top N of that category-year.
- **Calculation (plain words):** filter to the top N, count per state, sort; share = count / all top-N × 100. If NIRF
  ranks fewer than N (e.g. Law), a note says every ranked institution is counted.
- **Chart and why:** horizontal bar sorted from most to fewest: easy to compare, and long state names fit.
- **Filters the user can change:** year, category, top_n.

### Q2.2: How is the geographical distribution of top-ranked institutions changing from 2017 to 2025?
- **Engine / function:** `geography.py :: state_share_over_time(category, top_n)`
- **Definition used:** a state's share = its top-N institutions / all top-N institutions that year × 100.
- **Calculation (plain words):** shares per state and year (each year adds up to 100%); the 7 states with the most
  top-N places overall get their own colour, the rest are added together as "Other states".
- **Chart and why:** 100% stacked area: shows each state's share and how the whole mix shifts over time.
- **Filters the user can change:** category, top_n.

### Q2.3: Which states have improved their representation in the top 100 over time?
- **Engine / function:** `geography.py :: state_representation_change(category, start_year, end_year, top_n)`
- **Definition used:** change = top-N count in the end year − top-N count in the start year (positive = gained).
- **Calculation (plain words):** count per state in both years, subtract, sort; tied states are named together.
- **Chart and why:** diverging bar (blue gained, red lost) labelled "old → new count"; states with no change appear
  only in the table.
- **Filters the user can change:** category, start and end year, top_n.

### Q2.4: How do the rankings of institutions in Karnataka compare with those in Tamil Nadu?
- **Engine / function:** `geography.py :: compare_states(states, category, years)`
- **Definition used:** the exact ranks of all ranked institutions located in each state.
- **Calculation (plain words):** per year and state, the median, quartiles and spread of the ranks; pooled over all
  years, the median rank and the average number of ranked institutions per year. Both are reported because a state
  with many institutions naturally also has more of them lower down the list. Band-only rows are left out.
- **Chart and why:** grouped box plot per year (rank axis reversed), every institution as a dot, plus a thin line
  joining each state's yearly median: level, spread and trend in one picture.
- **Filters the user can change:** states (up to 8), category, years.

### Q2.5: Which states have produced the largest number of newly appearing institutions?
- **Engine / function:** `geography.py :: new_entrants_by_state(category, years)`
- **Definition used:** `is_new_entrant` from the pipeline: first appearance in the category's ranked list (exact rank
  or band), in a year when the category already existed the year before.
- **Calculation (plain words):** count new entrants per state and year; sort states by their total.
- **Chart and why:** horizontal stacked bar, one bar per state split by year (darker blue = later), total at the bar
  end: shows who produced the most and when.
- **Filters the user can change:** category, years. Years in which NIRF lengthened a list bring more entrants (noted
  on the chart).

### Q3.1: What is the distribution of NIRF scores for a selected year?
- **Engine / function:** `core/engines/univariate.py :: score_distribution(year, category)`
- **Definition used:** all published overall scores of that category-year (NIRF publishes no scores for band-only
  positions, nor for Innovation, SDG, Open University and Skill University).
- **Calculation (plain words):** count institutions per 2.5-point score interval (5 points for lists under 50); mark
  the mean and the median; skewness says whether a long tail pulls the mean away from the median.
- **Chart and why:** histogram with mean and median lines: the classic picture of one variable's shape.
- **Filters the user can change:** year, category.

### Q3.2: What is the distribution of overall ranks across all institutions?
- **Engine / function:** `univariate.py :: rank_distribution(year, category)`
- **Definition used:** number of ranked institutions per standard rank band (1-10, 11-25, 26-50, 51-100, 101-150,
  151-200, 201-300), split into "exact rank published" and "only rank band published".
- **Calculation (plain words):** count rows per band; the hover also gives institutions per 10 positions because bands
  have different widths. The insight reports ties.
- **Chart and why:** stacked bar in band order: shows how much of the list has exact ranks and how much only bands.
- **Filters the user can change:** year, category.

### Q3.3: What is the average, median, minimum and maximum score in a given year?
- **Engine / function:** `univariate.py :: summary_stats(year, category)`
- **Definition used / calculation:** n, mean, median, min and max (with the institution), range, standard deviation
  (sample, divide by n−1), Q1, Q3, IQR, coefficient of variation (SD / mean).
- **Chart and why:** the table, plus a horizontal box plot with every institution as a dot and the mean ± 1 SD
  diamond, so the numbers in the table can be seen.
- **Filters the user can change:** year, category.

### Q3.4: What percentage of ranked institutions fall into each score quartile?
- **Engine / function:** `univariate.py :: quartile_shares(year, category, mode)`
- **Two definitions:**
  - `score_range`: fixed quarters of the 0-100 scale (0-25, 25-50, 50-75, 75-100). The shares show where institutions
    sit on the absolute scale and can be very uneven (NIRF scores rarely fall below 25).
  - `statistical`: the data's own Q1, median and Q3. Each group holds about 25% *by definition* (ties can shift it
    slightly), so the useful answer is the cut-point scores.
- **Calculation (plain words):** put each scored institution in its group; share = group count / all × 100.
- **Chart and why:** one 100% stacked bar in ordered shades of blue: parts of a whole.
- **Filters the user can change:** year, category, mode.

### Q3.5: How does the spread of scores differ across NIRF categories?
- **Engine / function:** `univariate.py :: spread_by_category(year)`
- **Definition used:** spread = IQR (Q3 − Q1) and standard deviation of each category's scores.
- **Calculation (plain words):** per category: n, mean, median, SD, Q1, Q3, IQR, min, max, CV.
- **Chart and why:** horizontal box plots, one per category, sorted by median; dots beyond the whiskers are outliers
  by the 1.5 × IQR rule. A visible note says scores are comparable only within a category.
- **Filters the user can change:** year.

### Q4.1 / Q4.2 / Q4.4: How are two numbers related (RPC vs score, PR vs score, TLR vs RPC)?
- **Engine / function:** `core/engines/bivariate.py :: scatter_relation(x, y, year, category, color_by, trendline)`
- **Definition used:** association across the institutions of one category-year that have both values.
- **Calculation (plain words):** Pearson r (straight-line strength, −1 to +1); Spearman ρ (Pearson on ranks: any steady
  rise or fall, robust to outliers); R² = r² (share of y's variation explained by the line); p-value (chance of a
  correlation this strong if there were none); least-squares line y = a + b·x. The insight also says how many y-points
  10 more x-points go with on average. If ρ and r differ by 0.15 or more, the insight says the pattern is not a
  straight line or a few outliers matter.
- **Chart and why:** scatter plot with the trend line, the standard picture of a relationship between two numbers.
  Optional colouring by region, state (top 7 + Other) or rank band. This is also the statement's
  "select two variables" feature.
- **Caveats shown on the chart:** the overall score is a weighted sum of the parameters, so part of a parameter-vs-score
  association is built in; only ranked institutions with scores (the top of each list) are included.
- **Filters the user can change:** x and y (score, TLR, RPC, GO, OI, PR, QnR, QlR, SFC, rank), year, category, colour,
  trend line on/off.

### Q4.3: Which NIRF parameter has the strongest correlation with the overall score?
- **Engine / function:** `bivariate.py :: correlation_with_overall(year, category)`
- **Calculation (plain words):** Pearson r of each published parameter with the overall score (Spearman ρ, R² and the
  p-value in the table), sorted from strongest to weakest.
- **Chart and why:** sorted horizontal bar of r (blue positive, red negative): ranking a handful of numbers. A high r
  means the parameter has a large weight and/or institutions differ a lot on it.
- **Filters the user can change:** year, category (Research Institutions use QnR, QlR, SFC, OI, PR).

### Q4.5: Has the correlation between research scores and overall scores changed from 2017 to 2025?
- **Engine / function:** `bivariate.py :: correlation_over_time(param, category)`
- **Calculation (plain words):** for every year, Pearson r and Spearman ρ between the parameter and the overall score.
  "Strengthened" / "weakened" is used only for a change larger than 0.05; a note warns when the number of scored
  institutions changes between years.
- **Chart and why:** line chart with two lines (Pearson, Spearman), one point per year: change over time.
- **Filters the user can change:** parameter, category.
