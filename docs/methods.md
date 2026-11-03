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
- **`core/theme.py`:** one Plotly template `nirf` matching the dashboard's "National Observatory" look (navy ink,
  teal for data, marigold for highlights, Fraunces titles, Inter text; white card surface, hairline grid, 2 px lines,
  8 px markers), a colour-blind-safe 8-colour categorical palette in a fixed order (teal, marigold, indigo, coral, sky,
  olive, orchid, brown; checked with a colour-vision simulation; groups beyond 7–8 are folded into "Other"), one
  teal light→dark scale for amounts, teal (up / gained) vs coral (down / lost) for changes, and `add_source_note()`,
  which writes "Source: NIRF, Ministry of Education, Govt. of India" under every chart. `dark_variant()` swaps each
  colour for its own dark-mode step (chosen for the navy dark surface), so every chart also reads well in dark mode.
- **`core/result.py`:** every engine returns `ChartResult(fig, table, insight, method, chart_type)`.
- **`core/stats.py`:** summary statistics, Pearson/Spearman correlation, R², p-value and the least-squares line.
  Strength words: |r| < 0.2 very weak, < 0.4 weak, < 0.6 moderate, < 0.8 strong, otherwise very strong.

### Chart types used (all from `docs/allowed_charts.md`)
Every chart is one of the chart types taught in the course (`docs/allowed_charts.md`); `ChartResult.chart_type` holds
that exact name and `tests/test_engines.py` fails if an engine returns anything else.

| Function | Chart drawn | Allowed name (`chart_type`) |
|---|---|---|
| `trends.rank_trajectory` | one line with markers per institution, rank axis reversed; band-only years as a faint range bar | `multi-series line chart` (`line chart` for one institution) |
| `trends.biggest_movers` | horizontal bars of improvement, sorted, teal right of zero / coral left | `bar chart` (ranked, horizontal) |
| `trends.average_score_over_time` | one line with markers per category; `show_spread=True`: point + Q1-Q3 error bar | `multi-series line chart` (`line chart` for one category) / `point plot with error bars` |
| `trends.consistent_top_n` | institution × year grid of coloured cells, rank written in the cell | `matrix heatmap` |
| `geography.state_counts` | horizontal bars, most to fewest | `bar chart` (ranked, horizontal) |
| `geography.state_share_over_time` | one line per state (top 8 + "Other states") | `multi-series line chart` |
| `geography.state_representation_change` | horizontal bars of change, sorted, teal right of zero / coral left | `bar chart` (ranked, horizontal) |
| `geography.compare_states` | box per state and year, dots = institutions, thin line through the yearly medians | `box-and-whisker plot` |
| `geography.new_entrants_by_state` | one horizontal bar per state split by year | `stacked bar chart` |
| `univariate.score_distribution` | histogram + KDE curve + mean/median lines | `histogram with density curve` |
| `univariate.rank_distribution` | bar per rank band split into exact / band-only | `stacked bar chart` |
| `univariate.summary_stats` | horizontal box with every institution as a dot, mean ± SD diamond | `box-and-whisker plot` |
| `univariate.quartile_shares` | one 100% bar split into four score groups | `stacked bar chart` |
| `univariate.spread_by_category` | one horizontal box per category | `box-and-whisker plot` |
| `bivariate.scatter_relation` | one dot per institution (optionally coloured by group) + least-squares line | `scatterplot` |
| `bivariate.correlation_with_overall` | correlation heatmap with r in each cell; `view="bar"`: ranked bars of r | `correlogram` / `bar chart` |
| `bivariate.correlation_over_time` | two lines (Pearson r, Spearman ρ) by year | `multi-series line chart` |
| `multivariate.parameter_profile` | parameters on x, one bar per institution; `view="heatmap"`: institution × parameter grid | `grouped bar chart` / `matrix heatmap` |
| `multivariate.gap_finder` | dots with dashed median lines (four quadrants), one quadrant highlighted and labelled | `scatterplot` |
| `multivariate.improved_despite_decline` | one small bar chart of parameter changes per institution, shared y-axis | `small-multiple bar charts` |
| `multivariate.strongest_weakest_gap` | sorted stems with a dot (gap = strongest − weakest parameter) | `lollipop chart` |
| `multivariate.parameter_pca` | PC1 vs PC2 per institution, coloured by rank band | `PCA scatterplot` |
| `distribution.top10_vs_rest` | two violins with a box inside and every institution as a dot; `view="histogram"` | `violin plot` / `overlapping histogram` |
| `distribution.dispersion_by_year` | one box per year; `view="sd"`: SD per year as a line | `box-and-whisker plot` / `line chart` |
| `distribution.parameter_variability` | ranked horizontal bars of CV; `view="box"`: one box per parameter | `bar chart` / `box-and-whisker plot` |
| `distribution.median_iqr_over_time` | point = median, error bar = Q1 to Q3, per year | `point plot with error bars` |
| `distribution.score_by_state` | one horizontal box per state, sorted by median, dots = institutions | `box-and-whisker plot` |
| `mobility.band_transitions` | band in year A × band in year B grid with counts (confusion-matrix style) | `matrix heatmap` |
| `mobility.top10_entries_exits` | one row per institution, dot per top-10 year, entry/exit markers | `time-series dot plot` |
| `mobility.band_retention` | % staying in the same band per year pair; `by_band=True`: one line per band | `line chart` / `multi-series line chart` |
| `mobility.biggest_rank_moves` | stems from zero, teal right (up) / coral left (down) | `lollipop chart` |
| `mobility.up_down_same_counts` | one bar per year pair split into up / same / down | `stacked bar chart` |
| `outliers.research_vs_overall_outliers` | dots + least-squares line, residual z > 2 highlighted and labelled | `scatterplot` |
| `outliers.research_over_teaching` | ranked horizontal bars of RPC − TLR | `bar chart` |
| `outliers.unusual_score_jumps` | jittered dots over a box per year pair, abs(z) > 2 coloured and labelled | `jittered strip chart` |
| `outliers.strong_param_poor_rank` | parameter vs rank (reversed) with Q3 and median-rank lines | `scatterplot` |
| `outliers.volatility_vs_peers` | box of rank SD per peer band with jittered dots, outliers labelled | `box-and-whisker plot` |

Notes on closest-allowed choices: the "diverging" bars of `biggest_movers` and `state_representation_change` are
ordinary ranked horizontal bar charts whose values can be negative (bars left of zero), so no separate chart type is
needed. The faint vertical bars in `rank_trajectory` (years where NIRF published only a band such as 101-150) are
range marks inside the line chart, read like an error bar ("the rank is somewhere in here"). The lollipop chart is a bar chart drawn
with a thin stem and a dot (less ink for long sorted lists). Box plots with jittered dots (`unusual_score_jumps`,
`volatility_vs_peers`) are named after the layer that answers the question: the dots in Q8.3 (each change), the box
rule in Q8.5 (beyond the whisker = unusual). Shared drawing helpers: `core/theme.py :: add_lollipops()` and `jitter()`
(fixed random seed, so the same data always gives the same picture); `core/data.py :: category_year()` returns the rows
of one category-year (default: its latest year).

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
- **Chart and why:** diverging horizontal bar (teal = up, coral = down) around zero, labelled "old → new rank"; bars
  compare amounts and the zero line separates climbers from fallers.
- **Filters the user can change:** category, start and end year (default: the category's first and last year),
  direction, n.
- **Caveat:** the length of the exact-rank list changes (Engineering ranked 200 exactly in 2019–2022, 100 otherwise).

### Q1.4 / Q6.4: How has the average score (and its median and IQR) changed over time?
- **Engine / function:** `trends.py :: average_score_over_time(categories, stat, top_n, show_spread)`
- **Definition used:** per category and year, the mean or median of the published overall scores, and Q1 to Q3.
- **Calculation (plain words):** mean = sum / count, median = middle value; Q1 and Q3 = 25th and 75th percentiles.
  `top_n=100` keeps only exact ranks 1–100, so years with longer lists (Engineering 2019–22: 200) are comparable;
  the insight warns when the number of scored institutions changes.
- **Chart and why:** **multi-series line chart with markers**, one line per category through the yearly mean/median
  (a single line when one category is chosen): the question is change over time, and a line is the taught chart for
  that. Q1, Q3 and the number of institutions are in the hover. With `show_spread=True` it becomes a **point plot with
  error bars**: the point is the mean/median and the error bar runs from Q1 to Q3 (the middle 50% of institutions),
  so a longer bar = scores more spread out. When several categories are drawn their points are shifted slightly
  sideways so the bars do not overlap. (Earlier version: a line with a shaded Q1-Q3 band, replaced because a shaded
  band is not one of the taught chart types; the error bar shows the same Q1-Q3 range.) With several categories a
  visible "not comparable across categories" note is added.
- **Filters the user can change:** one or more categories, mean/median, top_n, show_spread.

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
- **Calculation (plain words):** shares per state and year (each year adds up to 100%); the 8 states with the most
  top-N places overall get their own line, the rest are added together as one "Other states" line (dotted grey). If
  the state with the biggest gain or loss is inside "Other states", the title/insight says so.
- **Chart and why:** **multi-series line chart** (one line with markers per state): the question is how each state's
  share changes over time, and with every line starting from the same 0% baseline each state's rise or fall can be
  read and compared directly. (Earlier version: a 100% stacked area, replaced because in a stacked area only the
  bottom layer has a flat baseline, so the middle states' changes are hard to read, and we want a chart taught by
  name.)
- **Filters the user can change:** category, top_n.

### Q2.3: Which states have improved their representation in the top 100 over time?
- **Engine / function:** `geography.py :: state_representation_change(category, start_year, end_year, top_n)`
- **Definition used:** change = top-N count in the end year − top-N count in the start year (positive = gained).
- **Calculation (plain words):** count per state in both years, subtract, sort; tied states are named together.
- **Chart and why:** diverging bar (teal gained, coral lost) labelled "old → new count"; states with no change appear
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
- **Chart and why:** horizontal stacked bar, one bar per state split by year (darker teal = later), total at the bar
  end: shows who produced the most and when.
- **Filters the user can change:** category, years. Years in which NIRF lengthened a list bring more entrants (noted
  on the chart).

### Q3.1: What is the distribution of NIRF scores for a selected year?
- **Engine / function:** `core/engines/univariate.py :: score_distribution(year, category)`
- **Definition used:** all published overall scores of that category-year (NIRF publishes no scores for band-only
  positions, nor for Innovation, SDG, Open University and Skill University).
- **Calculation (plain words):** count institutions per 2.5-point score interval (5 points for lists under 50); mark
  the mean and the median; skewness says whether a long tail pulls the mean away from the median.
  **Density curve (KDE, kernel density estimate):** put a small bell curve (normal curve) on every institution's
  score and add them all up; the result is a smooth outline of the histogram. The bell width (bandwidth) follows
  Scott's rule (≈ SD × n^(−1/5)), a standard automatic choice. The curve is multiplied by n × bar width so it is in
  the same "institutions per interval" units as the bars (its area equals the bars' area). It runs a little beyond
  the lowest/highest score because each bell has a width.
- **Chart and why:** **histogram with density curve**, plus mean and median lines. The histogram is the classic picture
  of one variable's shape; its look depends on where the bar edges fall, so the KDE curve adds the smooth shape
  (here: one peak in the low 50s and a long right tail = right-skewed).
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
- **Chart and why:** one 100% stacked bar in ordered shades of teal: parts of a whole.
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
- **Engine / function:** `bivariate.py :: correlation_with_overall(year, category, view)`
- **Calculation (plain words):** Pearson r for every pair of the overall score and the published parameters (score,
  TLR, RPC, GO, OI, PR), each pair using the institutions that have both values. For the ranked view: Pearson r of each
  parameter with the overall score (Spearman ρ, R² and the p-value in the table), sorted from strongest to weakest.
  The insight also names the two parameters that move together the most.
- **Chart and why:** main view (`view="correlogram"`): **correlogram** (correlation heatmap), one cell per pair with r
  printed in it, teal = positive, coral = negative, darker = stronger, diagonal = 1, mirror image across the diagonal.
  The "Overall score" row answers the question, and the rest of the grid adds what a bar chart cannot show: which
  parameters rise and fall together (e.g. RPC and PR, r = 0.78 in Overall 2025). Alternative view (`view="bar"`):
  **ranked horizontal bar chart** of r with the overall score: the quickest way to rank a handful of numbers. A high r
  means the parameter has a large weight and/or institutions differ a lot on it.
- **Filters the user can change:** year, category (Research Institutions use QnR, QlR, SFC, OI, PR), view.

### Q4.5: Has the correlation between research scores and overall scores changed from 2017 to 2025?
- **Engine / function:** `bivariate.py :: correlation_over_time(param, category)`
- **Calculation (plain words):** for every year, Pearson r and Spearman ρ between the parameter and the overall score.
  "Strengthened" / "weakened" is used only for a change larger than 0.05; a note warns when the number of scored
  institutions changes between years.
- **Chart and why:** line chart with two lines (Pearson, Spearman), one point per year: change over time.
- **Filters the user can change:** parameter, category.

### Q5.1: How do the top five institutions compare across all five NIRF parameters?
- **Engine / function:** `core/engines/multivariate.py :: parameter_profile(institutions, year, category, view)`
- **Definition used:** each institution's five parameter scores (TLR, RPC, GO, OI, PR; each out of 100) in one
  category-year. Default institutions: the top 5 of the year.
- **Calculation (plain words):** look up the five values; for each parameter, "difference" = highest − lowest value
  among the chosen institutions. The hover gives each value's position among all institutions that year (1st = highest).
- **Chart and why:** **grouped bar chart**: parameters on the x-axis, one bar per institution inside each group, so the
  institutions are compared one parameter at a time. Alternative (`view="heatmap"`): **matrix heatmap** institution ×
  parameter with the value in each cell. (A radar chart is the usual picture for this question but is not on our
  allowed list; grouped bars show the same profile and are easier to read exactly.)
- **Filters the user can change:** institutions (up to 8), year, category (Research Institutions: QnR, QlR, SFC, OI, PR).

### Q5.2 / Q5.3: Which institutions are high on one parameter but relatively low on another?
- **Engine / function:** `multivariate.py :: gap_finder(param_high, param_low, year, category, n_labels)`;
  Q5.2 = RPC high / TLR low, Q5.3 = TLR high / PR low.
- **Definition used:** "high on A, relatively low on B" = A above the median of A **and** B below the median of B, in
  the same category-year. Medians, because they are not moved by a few extreme values.
- **Calculation (plain words):** compute both medians; keep institutions in the "high A, low B" quadrant; sort them by
  the gap in z-scores z(A) − z(B), where z = (value − mean) / SD ("how many SDs above average on A minus on B"). z-scores
  put both parameters on one scale even though, e.g., RPC is usually much lower than TLR.
- **Chart and why:** **scatterplot** with B on x, A on y and a dashed line at each median, which splits it into four
  quadrants; the top-left quadrant is highlighted and the largest gaps are labelled. A scatterplot shows both
  parameters for every institution at once, so "high on one, low on the other" is a region of the picture.
- **Filters the user can change:** both parameters, year, category, number of labels.

### Q5.4: Which institutions improved their overall scores despite declining scores in one or more parameters?
- **Engine / function:** `multivariate.py :: improved_despite_decline(category, start_year, end_year, n)`
- **Definition used:** change = end-year value − start-year value. Qualifies if the overall score change > 0 and at
  least one parameter change < 0.
- **Calculation (plain words):** institutions with published scores in both years; compute all six changes; keep those
  that qualify, sorted by overall gain. This is possible because the overall score is a weighted sum: a gain on a heavy
  parameter can outweigh a loss on another.
- **Chart and why:** **small-multiple bar charts**: the same small bar chart repeated for each of the first n
  institutions (teal = parameter rose, coral = fell, dark bar = overall change), all on one shared y-axis so panels can be
  compared. One chart per institution keeps each "which parameter fell" story readable.
- **Filters the user can change:** category, start and end year (default 2017 → 2025), n. Note: NIRF adjusted some
  sub-metrics over the years, so part of a long-range change can come from the method.

### Q5.5: Which institutions have the largest difference between their strongest and weakest parameters?
- **Engine / function:** `multivariate.py :: strongest_weakest_gap(year, category, n)`
- **Definition used:** gap = highest parameter score − lowest parameter score of the same institution (all out of 100).
- **Calculation (plain words):** find each institution's max and min parameter, subtract, sort, keep the n largest.
- **Chart and why:** **lollipop chart** (a bar chart drawn as a thin stem with a dot), sorted, with "strongest −
  weakest" as the label; the hover names both parameters and values. A lollipop keeps a long sorted list calm.
- **Caveat on the chart:** parameters differ in typical level (PR is usually far below GO), so part of every gap shows
  how hard each parameter is; the most common pattern (GO strongest, PR weakest) is reported in the insight.
- **Filters the user can change:** year, category, n.

### Extra: PCA of the five parameters
- **Engine / function:** `multivariate.py :: parameter_pca(year, category)`
- **Definition used:** principal component analysis. PC1 = the direction along which institutions differ the most;
  PC2 = the next-most-varied direction at right angles to PC1. % of variance = share of the institutions' differences an
  axis keeps.
- **Calculation (plain words):** turn every parameter into a z-score (so each counts equally), run numpy's singular
  value decomposition, and give every institution a PC1 and PC2 value = a weighted sum of its z-scores (the weights are
  the loadings, listed in the method text). Signs are chosen so PC1 grows with the parameters.
- **Chart and why:** **PCA scatterplot**, PC1 vs PC2, coloured by rank band (darker = better). In Overall 2025 PC1
  keeps 44% of the variation and correlates r = 0.99 with the overall score (a general "strength" axis); PC2 (22%)
  contrasts OI against RPC.
- **Filters the user can change:** year, category.

### Q6.1: How does the score distribution differ between the top 10 and the remaining institutions?
- **Engine / function:** `core/engines/distribution.py :: top10_vs_rest(year, category, top, view)`
- **Definition used:** "Top 10" = exact rank ≤ 10; "Rest" = every other institution with a published score.
- **Calculation (plain words):** n, mean, median, SD, Q1, Q3, IQR, min, max per group; the insight also checks whether
  the two groups overlap at all (lowest top-10 score vs highest score of the rest) and reports skewness.
- **Chart and why:** **violin plot** with a box inside: the outline is a smoothed density (KDE) mirrored on both sides
  (wide = many institutions at that score), the white box runs from Q1 to Q3 with the median line, and every
  institution is a dot. It compares shape, centre and spread of two groups of very different sizes (10 vs 90).
  Alternative (`view="histogram"`): **overlapping histogram**, both groups on the same 2.5-point bins, half-transparent.
- **Filters the user can change:** year, category, top (e.g. 20), view.

### Q6.2: Are NIRF scores more dispersed in one year than another?
- **Engine / function:** `distribution.py :: dispersion_by_year(category, top_n, view)`
- **Definition used:** dispersion = standard deviation (typical distance from the mean) and IQR (width of the middle 50%).
- **Calculation (plain words):** per year: n, mean, median, SD, Q1, Q3, IQR, min, max, range and CV = SD / mean. A
  warning is added when the number of scored institutions changes between years; `top_n=100` fixes that.
- **Chart and why:** **box-and-whisker plot** per year: a taller box / longer whiskers = more dispersed, and outliers
  appear as dots. Alternative (`view="sd"`): **line chart** of the yearly SD.
- **Filters the user can change:** category, top_n, view.

### Q6.3: Which NIRF parameter exhibits the greatest variability across institutions?
- **Engine / function:** `distribution.py :: parameter_variability(year, category, view)`
- **Definition used:** coefficient of variation CV = SD / mean, i.e. spread relative to the parameter's own average.
  CV is used (not SD) because parameters sit at very different levels (PR mean ≈ 24, GO mean ≈ 75 in Overall 2025).
- **Calculation (plain words):** mean, SD, IQR and CV per parameter, sorted by CV. The insight says when ranking by SD
  alone would give a different answer.
- **Chart and why:** **bar chart** (ranked, horizontal) of CV, most variable first. Alternative (`view="box"`):
  **box-and-whisker plot** per parameter in the same order, to see the full spread.
- **Filters the user can change:** year, category, view.

### Q6.4: How do the median and interquartile range of scores change over time?
- **Engine / function:** `distribution.py :: median_iqr_over_time(category, top_n)` (draws with
  `trends.average_score_over_time(stat="median", show_spread=True)`, so both questions share one calculation).
- **Definition used:** per year, the median score and IQR = Q3 − Q1.
- **Calculation (plain words):** median and quartiles per year; the insight compares the first and last year and names
  the years with the widest and narrowest IQR (a change below 0.5 points is called "about the same").
- **Chart and why:** **point plot with error bars**: point = median, error bar = Q1 to Q3, so the bar's length *is*
  the IQR. Exactly the two quantities the question asks about, in one picture.
- **Filters the user can change:** category, top_n.

### Q6.5: How does the score distribution differ across states?
- **Engine / function:** `distribution.py :: score_by_state(year, category, min_institutions)`
- **Definition used:** the published overall scores of each state's institutions in one category-year.
- **Calculation (plain words):** per state: n, median, Q1, Q3, IQR, mean, min, max; states with fewer than
  `min_institutions` (default 3) are kept in the table but not drawn (a box of one or two values shows no spread).
- **Chart and why:** **box-and-whisker plot**, one horizontal box per state sorted by median, every institution as a
  dot: compares level and spread across many groups. Sorted by median because one very high scorer cannot move it.
- **Filters the user can change:** year, category, min_institutions.

### Mobility bands (used by Q7.1 and Q7.3)
Every row gets one band: **1-10, 11-50, 51-100, 101+**, or **Not ranked** (absent from that year's list). The band
comes from `rank_upper`: the exact rank, or the end of NIRF's own band. Every NIRF band (51-75, 76-100, 101-150 ...)
lies wholly inside one of these four, so institutions known only by band can be followed too and nothing is guessed.

### Q7.1: How many institutions moved from the 51–100 band into the top 50 between two selected years?
- **Engine / function:** `core/engines/mobility.py :: band_transitions(category, year_a, year_b)`
- **Definition used:** "moved from 51-100 into the top 50" = band 51-100 in year A and band 1-10 or 11-50 in year B.
- **Calculation (plain words):** every institution listed in year A or year B gets a band in both years; count
  institutions for each (band in A, band in B) pair.
- **Chart and why:** **matrix heatmap** read like a confusion matrix: rows = band in year A, columns = band in year B,
  cell = number of institutions (darker = more), names in the hover. The diagonal (dotted) = stayed in the same band;
  left of it = moved to a better band, right = worse. The orange box (51-100 → 1-10 and 11-50) answers Q7.1. A
  transition matrix shows every movement at once, including drop-outs and newcomers (a Sankey diagram would be the
  other usual choice but is not on the allowed list).
- **Filters the user can change:** category, year A, year B (default 2017 → 2025).

### Q7.2: Which institutions entered or exited the top 10 between consecutive years?
- **Engine / function:** `mobility.py :: top10_entries_exits(category, top)`
- **Definition used:** in the top 10 = rank certainly ≤ 10. Entered in Y = in the top 10 in Y, not in the previous
  published year; exited in Y = in the top 10 the previous year, not in Y.
- **Calculation (plain words):** compare each year with the previous one; list every entry and exit with the rank
  before and after (table).
- **Chart and why:** **time-series dot plot**: one row per institution ever in the top 10, a faint dot in every year it
  was there, a teal triangle where it entered and a coral cross in the first year outside. Each institution's whole
  history and every change are visible in one picture.
- **Filters the user can change:** category, top (e.g. 5 or 20).

### Q7.3: What percentage of institutions remained in the same rank band from one year to the next?
- **Engine / function:** `mobility.py :: band_retention(category, by_band)`
- **Definition used:** retention (Y−1 → Y) = institutions in the same band in both years / institutions ranked in
  both years × 100. Institutions that join or leave the list are counted separately in the table.
- **Calculation (plain words):** for every pair of consecutive published years: ranked in both, stayed, retention %,
  joined, left, and the retention of each starting band.
- **Chart and why:** **line chart** with markers, one point per year pair (change over time); `by_band=True` gives a
  **multi-series line chart** with one line per band. Note on the chart: a wide band keeps institutions more easily
  than a narrow one.
- **Filters the user can change:** category, by_band.

### Q7.4: Which institutions experienced the largest upward and downward rank movements?
- **Engine / function:** `mobility.py :: biggest_rank_moves(category, year_a, year_b, n)` (same calculation as
  `trends.biggest_movers(direction="both")`).
- **Definition used:** improvement = rank in year A − rank in year B (positive = moved up), exact ranks in both years.
- **Calculation (plain words):** subtract, sort, keep the n largest climbs and the n largest falls.
- **Chart and why:** **lollipop chart**: stems from zero, teal dots right of zero for climbs and coral dots left of zero
  for falls, labelled "old → new rank". Both directions in one sorted picture.
- **Filters the user can change:** category, year A, year B (default 2017 → 2025), n.

### Q7.5: How many institutions moved up, moved down, or retained their positions each year?
- **Engine / function:** `mobility.py :: up_down_same_counts(category)`
- **Definition used:** for consecutive published years, among institutions with an exact rank in both: up =
  improvement > 0, down = improvement < 0, same = 0.
- **Calculation (plain words):** count the three groups per year pair; institutions listed only by band in either year
  are counted as `not_comparable` in the table.
- **Chart and why:** **stacked bar chart**, one bar per year pair split into up / same / down (teal / grey / coral), so
  both the counts and the mix can be read. Up and down tend to balance: when one institution climbs past another, the
  other moves down.
- **Filters the user can change:** category.

### Q8.1: Which institutions have unusually high research scores relative to their overall scores?
- **Engine / function:** `core/engines/outliers.py :: research_vs_overall_outliers(year, category, param, z_threshold)`
- **Definition used:** expected RPC = the value on the least-squares line of RPC against the overall score. Residual =
  actual − expected. Residual z-score = residual / SD of all residuals. Unusual = residual z > 2.
- **Calculation (plain words):** fit the line, compute every residual and its z-score; with roughly normal residuals
  only about 2.5% would be above +2 by chance.
- **Chart and why:** **scatterplot** of overall score (x) vs RPC (y) with the least-squares line; the unusual points
  (far above the line) are highlighted and labelled. "Relative to the overall score" is exactly the distance from the
  line.
- **Filters the user can change:** year, category, parameter, threshold.

### Q8.2: Which institutions perform substantially better in research than in teaching?
- **Engine / function:** `outliers.py :: research_over_teaching(year, category, n)`
- **Definition used:** research advantage = RPC − TLR (both out of 100).
- **Calculation (plain words):** subtract for every institution, sort, show the n largest. The table also has the gap
  in z-scores, z(RPC) − z(TLR), which measures research strength relative to other institutions (RPC is typically far
  below TLR: medians 41.5 vs 70.4 in Overall 2025, so only 3 institutions have RPC > TLR).
- **Chart and why:** **bar chart** (ranked, horizontal): teal = RPC higher, coral = TLR still higher, labelled with both
  scores.
- **Filters the user can change:** year, category, n.

### Q8.3: Which institutions experienced an unusually large year-to-year score change?
- **Engine / function:** `outliers.py :: unusual_score_jumps(category, z_threshold, max_labels)`
- **Definition used:** change = score in year Y − score in the previous published year. z = (change − mean change that
  year) / SD of that year's changes. Unusual = |z| > 2. z is computed per year pair so that a year in which NIRF's method
  moved everyone (e.g. +4 on average in 2017 → 2018) does not make every institution look unusual.
- **Calculation (plain words):** all changes, their z-scores, keep |z| > 2; the insight names institutions with more
  than one unusual change.
- **Chart and why:** **jittered strip chart** over a box plot per year pair: every change is a dot, spread sideways at
  random (fixed seed) so dots do not hide each other; the box shows the year's typical change. Unusual jumps are teal,
  unusual drops coral, and the 12 largest are labelled.
- **Filters the user can change:** category, threshold, number of labels.

### Q8.4: Which institutions have a strong parameter score but a relatively poor overall rank?
- **Engine / function:** `outliers.py :: strong_param_poor_rank(param, year, category)` (default parameter GO)
- **Definition used:** strong = parameter at or above Q3 (top quarter) of the category-year; relatively poor rank =
  exact rank worse than the median exact rank (bottom half).
- **Calculation (plain words):** compute Q3 of the parameter and the median rank; flag institutions meeting both.
- **Chart and why:** **scatterplot** of the parameter (x) against rank (y, reversed so rank 1 is at the top) with dashed
  lines at Q3 and the median rank; the strong-parameter, poor-rank corner is highlighted and labelled.
- **Filters the user can change:** parameter (TLR, RPC, GO, OI, PR), year, category.

### Q8.5: Which institutions have unusually high ranking volatility compared with similar institutions?
- **Engine / function:** `outliers.py :: volatility_vs_peers(category, min_years)`
- **Definition used:** volatility = SD of an institution's exact ranks over the years (at least `min_years`, default 4).
  Peers = institutions whose median rank is in the same band (1-10, 11-25, 26-50, 51-100 ...). Unusual = SD above
  Q3 + 1.5 × IQR of its peer band's SDs (the box-plot outlier rule).
- **Calculation (plain words):** rank SD per institution; group by peer band; flag those beyond the upper whisker.
  Peers matter because ranks naturally move more lower down (median SD 0.8 in 1-10 vs 11.7 in 51-100).
- **Chart and why:** **box-and-whisker plot** of rank SD per peer band, every institution as a jittered dot; the dots
  beyond the whisker are the unusual ones and are labelled.
- **Caveat:** years with only a band (e.g. 101-150) have no exact rank and are left out, which can understate the
  volatility of institutions that drop out of the exact-rank list.
- **Filters the user can change:** category, min_years.

## Question registry and the 40-question run

- **`core/questions.py`:** `QUESTION_REGISTRY` holds the 40 Annexure A questions (Q1.1–Q8.5): ID, section, the question
  text word for word, the engine and function that answer it, the default parameters, the chart type (a name from
  `docs/allowed_charts.md`) and one sentence on why that chart fits. Defaults: category Overall; years = the full range
  (2017–2025), or 2025 for single-year questions. `run_question("Q2.1", year=2019, top_n=50)` reruns a question with
  changed filters (Level 2).
- **`scripts/run_all_questions.py`:** runs all 40 with their defaults, saves each chart to `docs/previews/<id>.html`
  and prints a pass/fail table with each insight. Pass = complete ChartResult (figure with data and title, source note,
  non-empty table, insight, method) whose chart type is allowed and matches the registry.
- **Tests:** `tests/test_questions.py` checks the 40 IDs, the word-for-word text, that every registered chart type is in
  `docs/allowed_charts.md`, that every call's parameters exist, and that every question runs and draws its registered
  chart type.
