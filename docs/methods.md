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
  11,647 ranked rows (6,974 with an exact rank, 4,671 known only by rank band, 2 withdrawn), 2017–2025, 17 categories.
  Participant lists (63,979 rows) and the 2018 Special Mention page go to a separate
  `nirf_participants.parquet`, so they are never counted as ranked. Full numbers and examples per step:
  `docs/cleaning_report.md`.
- **How (plain words), in order:**
  1. *Combine* every CSV; 2. *rename* columns to snake_case (`Institute ID` → `institute_id`, the 2023
     Innovation `Band` column → `rank_raw`); 3. *year* to integer.
  4. *Category:* `data/mappings/category_map.csv` maps each (label, year) to one standard name
     ("Research" 2021–23 and "Research Institutions" 2024–25 → Research Institutions). The published
     label stays in `category_original`.
  5. *State:* `data/mappings/state_map.csv` maps all 49 raw spellings to the 34 official states/UTs
     (Pondicherry → Puducherry) and adds a region (MHA zonal councils + North-East). Its `geo_name` column
     names the map polygon of each state (e.g. Jammu and Kashmir → "Jammu & Kashmir"), so maps match names
     through this table and the GeoJSON is never edited (`tests/test_geo.py` checks every state has a polygon).
  6. *Text tidy:* spaces, commas, hyphens, broken apostrophes (`` ` `` → ', so "Siksha `O` Anusandhan" is shown as
     "Siksha 'O' Anusandhan"), PIN codes, UPPER CASE, and one typo in NIRF's own pages ("St. Stephens's College",
     2021-2025, is shown as "St. Stephen's College"). The name exactly as published always stays in
     `institute_name_raw`.
  7. *Institution identity* (`pipeline/identity.py`): a matching key per name (lower case, & → and,
     no punctuation, "Govt" → "government", "Bangalore" → "bengaluru"); same key + same state = same
     institution (+ city when one name means two colleges in one state). Then links by NIRF ID code
     (stable from 2018), hand alias rules, "name = other name + its own city", and rapidfuzz
     `token_sort_ratio` ≥ 92 in the same state. Pairs scoring 80–92, or ≥ 92 with something against
     them (each name has its own different word, different cities, different ID codes), go to
     `data/mappings/institution_review.csv` for a human `approve = yes/no`, read back on the next run.
     Two rows of the same ranking list are never merged. `canonical_name` = the most recent name.
     *Renamed institutions (Phase 15e):* NIRF gave most institutions an ID code only from 2018, so a college whose
     name changed after 2017 (Thapar University → Thapar Institute of Engineering and Technology, Symbiosis
     International University → Symbiosis International ...) became two institutions: the 2017 rows were counted as
     a different institution, so it was missing from "2017 → 2025" comparisons and was a false "new entrant" in 2018.
     We checked 12 such pairs in the raw lists (same city; the old name stops the year the new one starts; never both
     in one list) and wrote each into `data/mappings/institution_alias_rules.csv` with that evidence; JNTU Anantapur
     was split by a new spelling of its city (Anantapur → Ananthapuramu, 2023). `python -m scripts.find_renames` lists
     other candidates for a person to check (`data/mappings/rename_review.csv`, 77 pairs): an institution last listed
     in year Y and one first listed in Y+1 or Y+2, in the same state and city, with similar names (token_set_ratio ≥
     75), never in the same list and sharing a category. Nothing in that file is merged until a person confirms it.
     The 208 pairs in `institution_review.csv` were decided with a pre-sorted suggestion file
     (`institution_review_suggested.csv`: yes / no / check with a reason); we corrected 4 "yes" suggestions that
     would have merged two different institutions (Thiagarajar College of Engineering and Thiagarajar College; the
     Landran and Jhanjeri campuses of Chandigarh Engineering College; the Kalkaji and Vasant Kunj campuses of
     Jagannath International Management School; the two Government Post Graduate Colleges for Girls in Chandigarh,
     both listed in 2018-2020). Result: 1,692 → 1,647 institutions; Q1.2/Q1.3 now compare 65 institutions ranked in
     both 2017 and 2025 (was 62); 2018 new entrants 362 → 340 rows (301 → 288 institutions).
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
  7. *Score = NIRF's formula:* every published score equals the weighted sum of its five parameters with NIRF's
     published weights for that category and year (typed into the test, e.g. 30/30/20/10/10 for Overall,
     40/15/25/10/10 for College from 2018 and for Law), within 0.05 for rounding. A least-squares fit of score on the
     parameters per category-year gives exactly these weights (largest gap 0.02).
  8. *Spot check:* `python -m pipeline.spot_check` picks 15 random master rows, re-reads the same institution
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
  matched to one `institution_key` by `match_institution()` (rules below, under "Institution names").
- **Institution names (`core/data.py` `match_institution()`, used by every page and by the chat):**
  - *Question answered:* which institution did the person mean by what they typed?
  - *Normalising (both the typed text and every name NIRF ever printed):* lower case, "&" = "and", punctuation
    removed, short forms written out (IIT = Indian Institute of Technology, IIIT, NIT, IIM, IISER, IISc, AIIMS, NLU,
    IIEST), and one spelling per place (Bengaluru = Bangalore, Mumbai = Bombay, Chennai = Madras, Kolkata =
    Calcutta, Trichy = Tiruchirappalli, Gurugram = Gurgaon ...).
  - *Order, the first rule that gives exactly one institution wins:* (1) an institution key typed directly;
    (2) the exact normalised name; (3) word matching: every typed word is in the name ("IIT Madras"), or the name
    words are in the name and the rest are its city or state ("Christian Medical College Vellore", "IIT Kerala" =
    the only IIT in Kerala); (4) close spelling, **last** (rapidfuzz WRatio ≥ 90 on the whole name, or ≥ 80 on the
    part after the family, e.g. "kharagpr" vs "kharagpur", and at least 3 points ahead of the next candidate;
    each name is also scored with its city added, so "Christian Medical Colege Vellore" is compared with
    "christian medical college vellore"). An unknown short form under 6 letters ("LPU") is never matched by spelling.
    In the chat, the known short forms ("iitb", "LPU", "IIIT Bangalore", "iiitb") are looked up before all of this.
  - *Family guard:* if the typed text names a family (IIT, IIIT, NIT, IIM, IISER, IISc, AIIMS, NLU, IIEST), every
    rule may only return an institute of that same family. IIIT covers the Indian, International and Indraprastha
    Institutes of Information Technology and IIITDM. So "IIIT Bangalore" can never become "Bangalore Institute of
    Technology" (no family), which is the bug this rule fixed.
  - *Place guard (spelling step):* every place word typed (a city or state; a misspelt place such as "banglore"
    counts as the place it is closest to, ratio ≥ 88) must be the candidate's city or state, or be in its name.
    Otherwise there is no automatic match.
  - *If nothing matches, in this order:* (5) the never-ranked participants (`data/processed/nirf_participants.parquet`,
    same normalising and guards): "IIIT Dharwad (Indian Institute of Information Technology, Dharwad) took part in
    NIRF (Engineering and Overall, 2022-2025) but was not in the published ranked list in any year, so there is no
    rank or score to chart", plus two similar ranked institutions from the same state and category (same family
    first, then same city, then the best recent rank); (6) the family swap, when the named institute does not exist:
    other families in the same city (or, if none, the same state or the state of that city), in the order IIT →
    IIIT, NIT, IIEST, IISc, IISER, IIM; NIT → IIIT, IIT; IIIT → IIT, NIT; IIM → IIT, IIIT. The first is chosen and
    the others are offered ("IIT Bangalore" → IIIT Bangalore, with IISc and IIM Bangalore). The dashboard pages do
    not swap silently; they show "There's no IIT Bangalore in the NIRF rankings. Did you mean IIIT Bangalore, IISc
    or IIM Bangalore?"; (7) otherwise "No institution called X in the NIRF data" with at most 3 suggestions that
    pass both guards and are also similar as a whole name (token_sort_ratio ≥ 70; an unknown short form under 6
    letters gets no suggestions), so "JIPMER" or "JU" can never suggest an unrelated college that merely shares a
    few letters. If several institutions fit equally well, the message lists them so the person can be more
    specific.
  - *A family alone always asks:* "IISER", "IIM", "NIT", "NIPER" typed alone fit several institutes, so the person
    gets the 4 best known to choose from: ranked by the family's own main list (Management for the IIMs: IIM
    Ahmedabad, Bangalore, Kozhikode, Lucknow, the 2025 top 4), even though one IISER was listed in 2017 under the
    bare name "Indian Institute of Science Education & Research". NIPER (the National Institutes of
    Pharmaceutical Education and Research) is a family too, so "NIPER Mohali" finds the Mohali institute.
  - *Why:* a spelling score alone rewards shared letters, not meaning ("indian institute of information technology
    bengaluru" looked close to "bangalore institute of technology"). Trying the precise rules first and checking
    family and place before accepting a spelling match keeps every guess explainable.
- **Year checks with a state filter:** when the chosen states have no institution in a year that NIRF did publish,
  the message says so ("No institution in Goa is in the Overall ranking of 2025 (they appear in 2017-2022)") instead
  of claiming that NIRF has no ranking that year (the same with an institute-type filter: "No IIM is ...").
  A real state or UT with no ranked institution at all says that plainly: "No institution from Ladakh appears in any
  NIRF ranking." (Ladakh and Lakshadweep; `INDIA_STATES` holds the 36 official names), instead of a list of states.
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
- **Light and dark theme (Phase 17):** the viewer can switch Light / Dark / System in Streamlit's ⋮ menu at any
  moment, and only the browser knows the result for sure. So the browser decides: a small invisible component
  (`app/components.py :: sync_theme()`) reads the app's real background colour, computes its brightness (relative
  luminance; below 0.5 = dark) and marks the page `data-nirf-theme="dark"` or `"light"`. The stylesheet holds both
  colour sets (`assets/style.css` light, `assets/style-dark.css` dark under that mark), so text, cards and chips
  change in the same instant, without a reload. When the charts on screen were drawn for the other theme, the
  component tells Python, and one quick rerun redraws them with that theme's colours. `core/theme.py :: themed()`
  draws every chart on a transparent background (the card's colour shows through) and prints each label on a
  coloured mark (heatmap cell, inside a bar or pie slice) in deep navy or white, whichever has the higher contrast on
  that mark (black or white on the few mid tones where neither reaches 4.5:1).
- **Readable text, measured (`scripts/check_contrast.py`):** contrast ratio = (L1 + 0.05) / (L2 + 0.05), where L1 is
  the relative luminance of the lighter colour and L2 that of the darker (WCAG 2). Normal text needs at least 4.5:1,
  large headings (24 px, or 18.66 px bold) at least 3:1. The script opens every page in both browser colour schemes ×
  the three menu choices, switches the theme without reloading, and measures every visible piece of text against
  what is really behind it, including chart labels against the bar, map state or heatmap cell under them.
- **Readable titles and labels (`core/theme.py`):** Plotly never wraps a title, so a title longer than 90 characters
  is split into two balanced lines (subtitles at 130), with extra top margin per line. Point labels on scatterplots
  and strip charts (Q5.2, Q5.3, Q8.1, Q8.3, Q8.4, Q8.5) are placed by `label_points()`: each label, most important
  first, tries spots around its point (right, left, above, below, diagonals, then further out) and takes the first
  one that stays inside the plot, does not cover another label and covers as few points as possible; a thin leader
  line joins it to its point. This changes only where a name is printed, never the data.
- **Chart rules checked on every chart (Phase 13 polish):** a title that states the answer; axis titles with units
  (also on name axes: "Institution", "State / UT", "NIRF parameter"); a legend title whenever a legend lists two or
  more entries (`finish()` adds "Key" if an engine gives none); rank axes reversed so rank 1 is at the top; the source
  note. Institution names on an axis are cut to 36 characters (`core/data.py :: chart_labels()`, e.g. "IIT Madras",
  "Sri Ramachandra Institute of Higher…") and every cut name shows in full in the hover text. Highlighted points never
  rely on colour alone: "unusually high" points are marigold **diamonds**, jumps up teal **triangles up**, drops coral
  **triangles down**, context points grey circles (`core/theme.py :: highlight_marker()`). `with_surface()` sets the
  white chart surface on every figure an engine returns (so a saved chart is white); on the page, `themed()` makes it
  transparent so the chart takes its card's colour in either theme.
- **`core/result.py`:** every engine returns `ChartResult(fig, table, insight, method, chart_type)`.
- **State filter for any analysis (`core/data.py :: only_states()`, `core/runner.py :: run()`):** inside
  `only_states(["Kerala"])` every `load_master()` returns only the rows of institutions located in Kerala, so every
  engine function can be asked "for Kerala only" without its own state parameter. `run(engine, function, params,
  states)` runs one analysis this way and labels the answer: the subtitle starts "Only institutions in Kerala", the
  insight starts "Among institutions in Kerala:" and the method adds that ranks stay the national NIRF ranks while
  counts, averages, quartiles, z-scores and correlations are calculated within the chosen states. A state with no
  institution in the category gives a plain message instead of an empty chart. `run()` only calls public functions
  of the 8 engines (nothing else), so the dashboard and the Ask NIRF chat run analyses the same safe way.
- **Institute-type filter for any analysis (`core/data.py :: only_types()`, `run(..., types=["IIT"])`):** works like
  the state filter, for one kind of institute: IIT, NIT, IIIT, IIM, IISER, AIIMS, NLU, NIPER. *Definition:* the type
  is read from the cleaned name with the same family patterns the name search uses ("Indian Institute of Technology
  ..." = IIT, "Visvesvaraya National Institute of Technology" = NIT, IIIT covers the Indian, International and
  Indraprastha IIITs and IIITDM, NLU covers the national law universities and law schools such as NLSIU and
  NALSAR). Counts: 23 IITs, 31 NITs, 21 IIMs, 10 IIITs, 5 IISERs, 7 AIIMS, 18 NLUs, 7 NIPERs. Central / state
  universities are not offered: NIRF does not publish that status, and it cannot be read reliably from a name.
  *Shown:* the chart title and the answer start "Among IITs only" (with states: "Among NITs in Tamil Nadu only"),
  and the method lists what the type covers. Ranks stay national; averages, z-scores and correlations are within
  the group. *Why:* "Which IITs improved the most since 2019?" needs the analysis limited to IITs, not a chart of
  all institutions.
- **Change over time in a category ranked once:** every analysis of change (movers, transitions, retention,
  volatility, unusual changes, state shares over time, consistent top N) first checks the category's years
  (`core/data.py :: change_years()`). SDG was ranked only in 2025, so these say "SDG was ranked only in 2025, so
  there is no change over time to show." instead of "the start year (2025) must be before the end year (2025)".
  Year counts are written "1 year" / "3 years" (`n_years()`).
- **"Top N" larger than the list:** NIRF's list has a fixed number of places (Overall 200, Law 40 in 2025;
  `list_sizes()`, always the national list, also under a filter). Asking for the top 500 uses the top 200 and the
  answer says "Overall lists 200 institutions in 2025, so the top 200 is used." (Q2.1, Q2.2, Q2.3).
- **`core/stats.py`:** summary statistics, Pearson/Spearman correlation, R², p-value and the least-squares line.
  Strength words: |r| < 0.2 very weak, < 0.4 weak, < 0.6 moderate, < 0.8 strong, otherwise very strong.

### Chart types used (all from `docs/allowed_charts.md`)
Every chart is one of the chart types taught in the course (`docs/allowed_charts.md`); `ChartResult.chart_type` holds
that exact name and `tests/test_engines.py` fails if an engine returns anything else.

| Function | Chart drawn | Allowed name (`chart_type`) |
|---|---|---|
| `trends.rank_trajectory` | one line with markers per institution, rank axis reversed; band-only years as a faint range bar | `multi-series line chart` (`line chart` for one institution) |
| `trends.parameter_trends` | one line per parameter of one institution by year, dashed line = overall score | `multi-series line chart` |
| `trends.band_history` | per institution and year: a bar from the band's best to worst rank (band-only years) or a dot (exact rank); rank axis reversed, no lines | `point plot with error bars` |
| `trends.biggest_movers` | horizontal bars of improvement, sorted, teal right of zero / coral left | `bar chart` (ranked, horizontal) |
| `trends.average_score_over_time` | one line with markers per category; `show_spread=True`: point + Q1-Q3 error bar | `multi-series line chart` (`line chart` for one category) / `point plot with error bars` |
| `trends.consistent_top_n` | institution × year grid of coloured cells, rank written in the cell | `matrix heatmap` |
| `geography.state_counts` | horizontal bars, most to fewest | `bar chart` (ranked, horizontal) |
| `geography.state_share_over_time` | one line per state (top 8 + "Other states") | `multi-series line chart` |
| `geography.state_representation_change` | horizontal bars of change, sorted, teal right of zero / coral left | `bar chart` (ranked, horizontal) |
| `geography.compare_states` | box per state and year, dots = institutions, thin line through the yearly medians | `box-and-whisker plot` |
| `geography.new_entrants_by_state` | one horizontal bar per state split by year; `by_year=False`: one plain bar per state | `stacked bar chart` / `bar chart` |
| `geography.state_map` | map of India, each state coloured by its top-N count (grey = none), year slider + play button | `choropleth map` |
| `geography.state_vs_state` | two panels on one year axis: institutions per year (top), median exact rank per year (bottom, reversed) | `vertically aligned time-series charts` |
| `geography.state_rank_boxes` | one box per state, all chosen years pooled, every institution-year as a dot | `box-and-whisker plot` |
| `univariate.score_distribution` | histogram + KDE curve + mean/median lines | `histogram with density curve` |
| `univariate.rank_distribution` | bar per rank band split into exact / band-only | `stacked bar chart` |
| `univariate.summary_stats` | horizontal box with every institution as a dot, mean ± SD diamond | `box-and-whisker plot` |
| `univariate.quartile_shares` | one 100% bar split into four score groups | `stacked bar chart` |
| `univariate.spread_by_category` | one horizontal box per category | `box-and-whisker plot` |
| `bivariate.scatter_relation` | one dot per institution (optionally coloured by region, state, rank band or category) + least-squares line | `scatterplot` |
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
- **Gaps and bands in the answer:** for one institution the insight names the years it was not in the list (e.g. IIM
  Calcutta, Overall: ranked 2017-2019 and 2023 only) and lists each band-only year with its band ("In 2024 it was
  placed only in the 101-150 band." for IIT Dharwad, Engineering). With several institutions the band-only years are
  listed per institution ("Years placed only in a NIRF band: IIT Dharwad 2024 (101-150)"). With a single exact rank no
  change is claimed ("had an exact rank only in 2018").
- **Who is ahead:** with two institutions the insight also says who was ahead in the latest year both had an exact rank
  and by how many places, and the gap in the first such year ("In 2025, IIT Mandi (rank 26) was ahead of IIT Jodhpur
  (rank 27) by 1 place; in 2017 ... IIT Mandi was ahead by 37 places"). With three or more: who had the best rank in
  the latest year. This is the plain fact the chat gives for "Will X overtake Y?" (no forecast).
- **Filters the user can change:** institutions (up to 8, default the top 5 of the latest year that has a ranked
  institution, by exact rank and then by band, so a state whose only institution is band-only, such as Mizoram, still
  gets a chart), category, years.

### Q1.2 / Q1.3 / Q7.4: Which institutions improved / declined the most in rank?
- **Engine / function:** `trends.py :: biggest_movers(category, start_year, end_year, direction, n)`
- **Definition used:** improvement = rank in start year − rank in end year (positive = moved up).
- **Calculation (plain words):** keep institutions with an exact rank in both years (a band cannot be subtracted;
  the method text says how many were left out), subtract, sort, keep the n largest climbs (`up`), falls (`down`)
  or both.
- **Chart and why:** diverging horizontal bar (teal = up, coral = down) around zero, labelled "old → new rank"; bars
  compare amounts and the zero line separates climbers from fallers. The largest climb (Q1.2) or the largest fall
  (Q1.3) is always the top bar, so the bar the title names is the first one read.
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
- **Categories with few years:** when a category was ranked in fewer years than `min_years` (Agriculture & Allied
  Sectors: 2023-2025), "at least 5 years" becomes "every year it has" (3) and the answer says so.
- **Filters the user can change:** category, n, min_years.

### Phase 20: Section 2 on the map, and every chart readable at a glance
- **Section 2 draws the map of India** (`core/geo.py`, `assets/india_states.geojson`, unchanged): Q2.1, Q2.3 and Q2.5
  are **choropleth maps** (darker = more; grey = none; a two-direction teal/coral scale for the change in Q2.3), Q2.2
  shows the first and the last year side by side on one colour scale, and Q2.4 is a small map of the compared states
  beside a **jittered strip chart** (one dot per institution on a rank axis, 1 at the top, for one year; institutions
  NIRF lists only in a band sit as squares in a separate grey strip, counted but never placed). Numbers are printed on
  the leading states; Delhi, Chandigarh, Puducherry and Goa are written beside the map with a leader line. Every
  function keeps its old chart behind `view` ("ranked", "lines", "boxes"), offered as a switch in the Question Bank
  and on the Geography page. Map labels take the ink that reads on each state in both themes (`core/theme.py ::
  inks_on_scale`, applied again after the dark-mode swap in `themed()`).
- **Every sample chart (Q1.1-Q8.5)** now has a title that states the answer in plain words, a one-line "how to read it"
  subtitle, plain names first with the term in brackets (`core/data.py :: PLAIN`, `WORD`: "Teaching score (TLR)",
  "Smoothed shape (KDE)", "Middle half (IQR)", "Straight-line link (Pearson r)"), the answer in colour and the rest
  grey, values printed on bars and points, "better / worse" on rank axes, a number in every heatmap cell, labelled
  box plots (lowest, middle value, typical range), shaded and named answer corners on the quadrant scatterplots, and
  "showing N of M" wherever a chart shows fewer items than its table. Q5.4 shows the 6 institutions with the biggest
  overall gain (the table keeps all). The correlation words follow fixed thresholds on |r| (below 0.2 very weak, 0.2-0.4
  weak, 0.4-0.6 moderate, 0.6-0.8 strong, 0.8 and above very strong). No calculation, table or insight changed:
  `scripts/compare_tables.py` saved the 40 tables before the work and reports 0 differences after it.

### Q2.1: Which states have the highest number of institutions in the top 100?
- **Engine / function:** `core/engines/geography.py :: state_counts(year, category, top_n)`
- **Definition used:** institutions of each state certainly in the top N of that category-year.
- **Calculation (plain words):** filter to the top N, count per state, sort; share = count / all top-N × 100. If N is
  larger than NIRF's list (top 500 of Overall's 200 places, top 100 of Law's 40), the list size is used and the answer
  says so ("Overall lists 200 institutions in 2025, so the top 200 is used."). A tie at the last place makes the
  top N hold more than N institutions (Overall 2020: two institutions share rank 100, so the top 100 holds 101); the
  answer names them, and shares are of the institutions actually in the list.
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
- **Filters the user can change:** category, years, split by year on/off (`by_year`), state filter. Years in which
  NIRF lengthened a list bring more entrants (noted on the chart). The category's first year is left out of the span
  because nobody can be "new" in it.
- **Geography page, "New entrants" tab:** `by_year=False` by default: one plain **bar chart** of totals (ranked,
  horizontal), with the split by year and the best-placed new institutions in the hover text; the toggle switches to
  the stacked version.

### Geography page: the map of India (Q2.1 / Q2.2 on a map)
- **Engine / function:** `geography.py :: state_map(year, category, top_n)`
- **Definition used:** per state/UT, the number of institutions certainly in the top N of that category-year (same
  rule as Q2.1). Hover also shows the share of the list (count / all top-N places × 100), the best-ranked institution
  and the **median** of the state's exact ranks (middle value when sorted; band-only rows have no exact rank).
- **Calculation (plain words):** count per state for every year of the category. Colour = count: grey = 0, light to
  dark teal = few to many (in dark mode: dark to light teal, so "more" always stands out). The colour scale runs from
  0 to the highest count of ANY year and stays fixed while the map plays, so a colour means the same number in every
  year.
- **Chart and why:** **choropleth map** (allowed list, "Maps"): where the top institutions are concentrated is a
  geographic question, and a map shows it at a glance. A year slider and a ▶ Play button step through every year of
  the category (2017 → 2025 for Overall); the title changes with the year. Small UTs (Delhi, Chandigarh, Puducherry)
  are tiny on any map, so the table and the Q2.1 bar chart give the same numbers as a ranked list.
- **Boundaries:** `assets/india_states.geojson` (source and licence in `docs/sources.md`). State names are matched
  through the `geo_name` column of `state_map.csv`. Dadra and Nagar Haveli and Daman and Diu (one UT since 2020) is
  drawn by its two old polygons, both painted with the merged UT's value.
- **Filters the user can change:** category, year (the map opens on it), top N.

### Geography page: State vs State (Q2.4 head to head)
- **Engine / functions:** `geography.py :: state_vs_state(states, category, years, top_n)` and
  `state_rank_boxes(states, category, years, top_n)`. Default: Karnataka vs Tamil Nadu (up to 4 states).
- **Definition used:** per state and year, (1) the number of its institutions in the ranked list (exact rank or band;
  with top N, only those certainly in the top N) and (2) the median of their exact ranks (lower = better).
- **Calculation (plain words):** counts and medians per year; the answer counts in how many years each state had
  more institutions and in how many it had the lower median, and pools all years (mean institutions per year, median
  of all exact ranks). Both are shown because a state with many institutions naturally also has more of them further
  down the list. The box plot pools all chosen years: one rank per institution per year (institution-years); median,
  Q1–Q3 box, whiskers to 1.5 × IQR, every rank as a dot. One card per state (in its chart colour) shows institutions
  per year, the pooled median rank and the best institution.
- **Charts and why:** **vertically aligned time-series charts** (counts on top, median rank below, one shared year
  axis, rank axis reversed so up = better) to read quantity and quality year by year; **box-and-whisker plot** to
  compare whole rank distributions. (`compare_states`, Q2.4 in the Question Bank, keeps the per-year boxes for up to 8
  states under "More views".)
- **Filters the user can change:** State A, State B, category, years, "count only the top …".

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
- **Engine / function:** `core/engines/bivariate.py :: scatter_relation(x, y, year, category, color_by, trendline, top_n)`
- **Definition used:** association across the institutions of one category-year that have both values.
- **Calculation (plain words):** Pearson r (straight-line strength, −1 to +1); Spearman ρ (Pearson on ranks: any steady
  rise or fall, robust to outliers); R² = r² (share of y's variation explained by the line); p-value (chance of a
  correlation this strong if there were none); least-squares line y = a + b·x. The insight also says how many y-points
  10 more x-points go with on average. If ρ and r differ by 0.15 or more, the insight says the pattern is not a
  straight line or a few outliers matter.
- **Chart and why:** scatter plot with the trend line, the standard picture of a relationship between two numbers.
  Optional colouring by region, state (top 7 + Other), rank band or category. This is also the statement's
  "select two variables" feature (see "Relationships page" below).
- **Several categories (colour by category):** the institutions of the chosen categories in that year are pooled
  into one set of dots (an institution ranked in two categories is two dots); a visible note says that scores of
  different categories are not on the same scale, and categories not ranked that year are listed as left out.
- **Rank on an axis:** the rank axis is reversed (1 = best); a negative r then means "higher value, better rank",
  and the insight says so. `top_n=50` keeps only institutions certainly ranked 1-50 ("among the top 50").
- **Caveats shown on the chart:** the overall score is a weighted sum of the parameters, so part of a parameter-vs-score
  association is built in; only ranked institutions with scores (the top of each list) are included.
- **Filters the user can change:** x and y (score, TLR, RPC, GO, OI, PR, QnR, QlR, SFC, rank), year, category (or
  several, with colour by category), colour, trend line on/off, only ranks 1 to N, only states.

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
- **Band-only ranks:** below 100 NIRF publishes mostly bands (101-150, 151-200 ...). Every such band lies wholly in
  101+, so these institutions are still placed with certainty; the answer also counts how many climbed from 101+ into
  the top 100.
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
  than one unusual change. When no change passes the threshold (e.g. Dental with |z| > 3), the answer says so and names
  the largest change: "None of the 154 year-to-year score changes in Dental (2020-2025) is beyond |z| > 3; the largest
  is ... (z = −2.6). Try a lower threshold."
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

## Question Bank page (Level 1 and Level 2 live)

- **Where:** `app/views/question_bank.py` (page) and `app/question_controls.py` (the per-question controls).
- **Layout:** the 8 sections are tabs (Trends, Geospatial, Univariate, Bivariate, Multivariate, Distribution, Mobility,
  Outliers); each lists its 5 questions with their IDs. Picking one shows the question, a "Why this chart?" note
  (`why_this_chart` from the registry), the controls for that question, then its chart card (chart, one-line answer,
  "How we calculated this" and "See the data" with a CSV download). Only the open tab is computed.
- **Controls = the question's own parameters:** one widget per parameter in the registry's `default_params`, starting
  at the registered default. Examples: Q1.1 category + institution picker + year range; Q7.1 category + "From year" +
  "To year"; Q5.2 category + year + "High parameter" + "Low parameter"; Q8.1/Q8.3 the |z| cut-off for "unusual".
  Year and parameter lists follow the chosen category (e.g. Research Institutions offers QnR, QlR, SFC, OI, PR; a
  default missing there falls back to that category's first parameter). Parameters that define the chart itself
  (direction of Q1.2/Q1.3, the chart view, the quartile mode) are not offered, so the chart always matches its
  "Why this chart?" note. "Reset" restores the registered defaults. This is how a new examiner question (Level 2)
  is answered live: the same, already explained method with different years, category, institutions or parameters.
- **Selections that cannot be answered** (e.g. a parameter question for Innovation, which publishes no parameter
  scores, or "From year" after "To year") show a friendly message from the engine instead of an empty or wrong chart.
- **Deep links:** `?q=Q4.3` in the address opens that question; the address always shows the open question, so a
  link can be copied. An unknown ID falls back to Q1.1 with a short notice.
- **"Run all 40":** runs every question with its defaults and shows a grid with a tick (or cross and the reason) per
  question, its run time and a mini preview; "Open" jumps to the full question. A tick means the same checks as
  `scripts/run_all_questions.py` (`core.questions.check_result`).
- **Tests:** `tests/test_question_bank.py` runs the real app headless (Streamlit AppTest): all 40 deep links open with
  one chart, the right controls and no error; changing a control redraws and enables Reset; picking a question
  updates the link; Run all 40 shows 40 ticks and 40 previews; an unknown ID does not crash. In addition every
  question was run for every category (and several years) to check that each combination gives a chart or a
  friendly message, never a crash.

## Explore pages (Level 2: every knob of every analysis)

- **Where:** `app/explorer.py` (the shared control system) and the seven topic pages in `app/views/` (Trends,
  Geography, Distributions, Relationships, Multi-Parameter, Mobility, Outliers).
- **Layout:** "What do you want to see?" lists that page's analyses in plain English (one entry per engine function;
  Trends lists climbers and fallers separately). Under it, a card holds ONLY the controls of the chosen analysis, with
  one control for EVERY one of its parameters; then the chart card (chart, one-line answer, "How we calculated this",
  "See the data"). Every public engine function is offered somewhere: 38 as views, the two-variable scatterplot on
  Relationships, the coverage heatmap on Data & Method.
- **Two kinds of control:** (1) shared with the sidebar: category, year range, states and institutions. The control
  above the chart and the sidebar filter are one value: changing either updates both, and the choice follows the user
  to the next page. (2) local to the analysis: a single year (starts at the end of the sidebar's year range), the
  parameters to compare, how many institutions (starts at the sidebar's top N), rank cut-offs, the |z| threshold,
  "at least N years" (bounded by the category's number of years), chart variants (e.g. violin or overlapping
  histogram) and how many names are printed on the chart. A local choice is kept when the category changes, as long
  as the new category offers it (e.g. the year 2019); otherwise it starts again from its default.
- **Where the sidebar filters are drawn:** on Home, the seven Explore pages and Data & Method, the pages that use
  them. Question Bank, Chart Builder and Ask NIRF have their own controls, so their sidebar shows a short note instead
  ("This page uses its own controls. The sidebar filters apply to the Explore pages."); Ask NIRF keeps its Gemini
  status box. The five filter values live in session state, not in the sidebar widgets, so they wait while such a
  page is open: Trends -> Ask NIRF -> Trends shows the same choices. Every control that edits a filter (in the
  sidebar or above a chart) starts from the stored value and writes changes back (`app/filters.py :: synced()`).
- **Institution lists follow the category:** every institution picker (sidebar, Explore views, Question Bank, Chart
  Builder) offers only the institutions listed in the chosen category at least once, with an exact rank or in a rank
  band (`app/filters.py :: institution_options(category)`): Engineering offers 460, Medical 66, instead of all 1,647.
  For several categories (Chart Builder) it is the union of their lists. The label is "Short name · City, State",
  plus "· band only" when NIRF never gave the institution an exact rank in that category. When the category changes,
  chosen institutions not listed in the new one are removed and a caption says so, e.g. "IIT Dharwad is not ranked in
  Medical, so it was removed." Why: choosing an institution that has no rows in the category could only give an empty
  chart.
- **"Only states":** on every analysis without its own state parameter, the state filter limits the whole analysis to
  institutions in those states (see "State filter for any analysis" above), and the chart says so. Compare states has
  its own state picker instead (empty = Karnataka and Tamil Nadu).
- **"Only institute type":** drawn next to "Only states" on the same views: IITs, NITs, IIITs, IIMs, IISERs, AIIMS,
  NLUs, NIPERs (see "Institute-type filter" above). The chart title and the answer then start "Among IITs only".
- **Tests:** `tests/test_explorer.py` checks that each view's controls cover exactly its function's parameters, that
  every view of every page draws a chart in the real app (Streamlit AppTest), that page and sidebar stay in sync, that
  local choices survive a category change, and that the state filter is applied and shown. `tests/test_filters.py`
  checks the per-category institution lists, where the sidebar filters are drawn, that they survive a page without
  them, and that a category change removes unlisted institutions with a caption.

### Extra: How have one institution's parameter scores changed over the years?
- **Engine / function:** `core/engines/trends.py :: parameter_trends(institution, category, years)` (Trends page,
  "Parameter scores of one institution, year by year").
- **Definition used:** the published score of each parameter (TLR, RPC, GO, OI, PR; Research Institutions: QnR, QlR,
  SFC, OI, PR) and the overall score of one institution in one category, year by year.
- **Calculation (plain words):** look up the institution's row in each year; change = last published value - first
  published value; the insight names the parameter that gained the most and the one that fell the most.
- **Chart and why:** multi-series line chart: change over time for several numbers on the same 0-100 scale (all
  from one category), so the lines can share one axis; the overall score is the dashed dark line. Years without a
  score are gaps, never filled in.
- **Filters the user can change:** category, institution, year range.

### Extra: Where was a college placed when NIRF published only a rank band?
- **Engine / function:** `core/engines/trends.py :: band_history(institutions, category, years)` (Trends page, "Rank
  bands of colleges without an exact rank"; the chat uses it automatically for band-only institutions).
- **Why it exists:** below its exact-rank list NIRF publishes only a rank band (e.g. 201-250) and no score. In our data
  1,225 of the 2,768 institution-category pairs only ever have a band, so a rank line cannot be drawn for them.
- **Definition used:** the band NIRF published for each institution in the chosen category, year by year (a band = a
  range of ranks inside which NIRF does not say the exact position), and the exact rank in years that have one.
- **Calculation (plain words):** read the band text ("201-250") and split it into its best rank (201) and worst rank
  (250). Nothing is averaged or estimated: the band is drawn as it was published.
- **Chart and why:** point plot with error bars (an allowed chart). For a band year the bar runs from the band's best
  to its worst rank, with no visible point inside, because NIRF gives no number there; an exact rank is a plain dot.
  Nothing is joined by a line, since a line through the middle of a band would invent a rank. Rank axis reversed
  (rank 1 at the top); several institutions are shifted slightly sideways so their bars do not overlap. A box plot
  or a line chart would both suggest a number we do not have; an error bar is exactly "somewhere in this range".
- **Insight:** lists the bands in time order, e.g. "Bangalore Institute of Technology, Bangalore was placed in
  Engineering band 201-250 in 2020 and 251-300 in 2021. NIRF publishes only a rank range and no score beyond the top
  list, so an exact rank line cannot be drawn."
- **Filters the user can change:** institutions (default: up to 5 from the best band of the latest year, those with no
  exact rank first, then alphabetical),
  category, years, states. Several institutions are shifted sideways so their bars stand side by side.

### Extra: Home page overview, today's top N followed back in time
- **Engine / function:** `core/engines/trends.py :: top_n_race(category, years, n, highlight, depth)` (Home page and
  Trends page, "Today's top N, followed back in time").
- **Definition used:** the N institutions with the best exact ranks in the last chosen year, and their exact rank in
  every earlier year.
- **Calculation (plain words):** look up each institution's exact rank per year; change = first exact rank - last
  exact rank (positive = moved up). Years with only a band or no rank are gaps, never filled in.
- **Chart and why:** multi-series line chart with the rank axis reversed (rank 1 at the top). Every line is named at
  its end as "rank · institution" instead of a legend: neighbouring ranks are only a few pixels apart, so the labels
  are pushed apart to one text line each and joined to their line end by a thin leader. Direct labels mean no colour
  matching is needed (the best three lines are coloured, the rest grey context).
- **With a filter or one year:** with a state or institute-type filter the N are the best N *of that group* (their
  national ranks are kept), and "stayed in the top N every year" is counted inside the group: each year the cut-off is
  the N-th best exact rank among those institutions. A year without an exact rank never counts as "in the top N".
  If fewer than N have an exact rank (Karnataka has 7 in Engineering 2025), the title says how many instead of "top
  10". With only one year chosen ("Bangalore colleges in engineering 2025") the answer lists every institution with
  its rank.

### Data & Method page
- **Pipeline diagram:** the four layers (scrape → clean → master table → 8 engines → dashboard and Ask NIRF) with the
  real counts of the last pipeline run (files, raw rows, ranked rows, institutions, categories).
- **Cleaning steps:** read from `docs/cleaning_report.md` by `core/cleaning_report.py` (no number is typed into the
  page): every step with rows before, rows after and the change, a bar of the rows after each step, and for a chosen
  step "What changed" and "Why". Summary cards: raw rows, ranked rows kept, institutions (from name spellings), states
  (from spellings), duplicates dropped.
- **Data dictionary:** every column of the master table (meaning, type, example), searchable.
- **Limitations (counts from the master table):** banded ranks have no score (left out of every score chart, never
  given a mid-point); scores are not comparable across categories (own weights; Research Institutions use different
  parameters); the NIRF method changed over the years (new and renamed lists, different band ranges, revised
  parameter definitions); ranks are relative to who took part that year.

### Relationships page: the "select any two variables" interface
- **Controls:** X and Y (overall score, every parameter the category publishes, rank), colour by (nothing, state,
  region, category, rank band), category (several categories when colouring by category), year, only ranks 1 to N,
  only states, trend line on/off.
- **Metric cards above the chart:** Pearson r, Spearman rho, R², p-value and n, from `scatter_relation()`
  (`core/stats.py :: correlate()`).
- **One-line interpretation:** "<strength> <direction> relationship: institutions with a higher X tend to have a
  higher/lower Y; statistically significant (p < 0.05) / not statistically significant, so it could be chance."
  Strength words use the same scale as everywhere (|r| < 0.2 very weak ... >= 0.8 very strong). With rank on an axis
  the sentence is turned round: "a better (smaller) rank". X = Y gives a hint to pick two different numbers.

## Chart Builder (the safety net for unusual questions)

- **Where:** `core/builder.py :: build_chart()` (logic) and `app/views/chart_builder.py` (controls). The Ask NIRF chat
  can call the same function for questions no ready-made analysis covers.
- **Filters:** categories (empty = all), from year, to year, rank cut-off (top 10 ... top 200: rows certainly ranked
  within it), states, regions, institutions. They start from the global filters when the page opens; the
  institution list offers only institutions listed in the chosen categories (all, when none is chosen).
- **Variables:** groups = year, category, state, region, rank band, institution, new entrant (first year in that
  category's list; the list's own first year is shown separately, because nobody can be "new" in it); numbers =
  overall score, the parameters (TLR, RPC, GO, OI, PR, QnR, QlR, SFC) and the exact rank.
- **Aggregations (plain words):** count = the number of distinct institutions in a group (an institution is counted
  once per group even if it appears in several years); mean = sum / count; median = the middle value; min / max = the
  smallest / largest value. Each institution-year-category row is one value.
- **Chart types (all in `docs/allowed_charts.md`):** bar, grouped bar, stacked bar (`bar chart`, `grouped bar chart`,
  `stacked bar chart`; with a facet `small-multiple bar charts`), line (`line chart`, `multi-series line chart` with
  a colour), scatter (`scatterplot`), bubble (`bubble chart`: bubble area = a third number), box
  (`box-and-whisker plot`), violin (`violin plot`), histogram (`histogram`; `overlapping histogram` with a colour),
  strip (`jittered strip chart`), heatmap (`matrix heatmap`: X = columns, second group = rows, cell = the
  aggregated value), pie (`pie chart`: share = group count / total x 100).
- **Which controls each chart uses:** bar, line, heatmap and pie summarise groups (X = a group, aggregation used);
  scatter, bubble and histogram need a number on X; box, violin and strip need groups on X and a number on Y. Controls
  a chart does not use are greyed out.
- **Friendly hints instead of errors:** a pie needs Count (parts of a whole); stacked bars need Count (adding means
  makes no sense, use grouped bars); a line chart needs Year on X; grouped/stacked bars and heatmaps need a second
  group; scatter needs two different numbers; X, colour and facet must be different groups; a number the category
  does not publish (e.g. TLR for Innovation) or filters with no rows explain what to change.
- **Handled automatically, and written in the chart note:** more than 8 colour groups -> the 7 largest + "Other";
  institutions as bars -> the 30 largest (or the chosen "Show groups" top N; for rank, the best); more than 12 facets
  -> the 12 largest; several categories with a score -> the cross-category note; several years pooled -> a note on
  how institutions are counted. The title states the answer (largest bar, highest median, share of the largest
  slice, r for a scatter, the middle half for a histogram, the year with most new entrants).
- **Tests:** `tests/test_builder.py` (every chart type, numbers against pandas, every hint, the page's quick starts).

## Level 2 rehearsal: 15 new examiner questions

`docs/level2_questions.md` lists 15 questions that are not in Annexure A, the page and controls that answer each, and
the answer the dashboard gives. `tests/test_level2.py` sets exactly those controls in the real app for each question
and checks that the chart drawn is the same answer as the analysis those settings stand for.

## Ask NIRF (Level 3: a typed question becomes a chart)

- **Where:** `nlq/` (logic) and `app/views/ask_nirf.py` (chat page). Tests: `tests/test_nlq.py` with the 33 questions in
  `tests/nlq_questions.py`, and `tests/test_edge_cases.py`; live accuracy report: `python -m scripts.nlq_accuracy`
  (needs a Gemini key).
- **Question answered:** any question about the NIRF data that one of our analyses (or a simple group-and-summarise
  chart) can answer, typed in plain English or Hinglish, with typos and short forms.
- **Who does what (the key point for the viva):** the language model (Google Gemini, temperature 0) only *reads* the
  question and writes a small JSON plan saying which analysis to run with which settings. It never sees the data
  and never calculates a number. Our code checks the plan, translates the names and runs the same engine functions as
  the rest of the dashboard, so every number comes from the cleaned master table.
- **Step 1, the catalog (`nlq/catalog.py`):** the model is given a text description generated from our code: the
  columns and their meanings, the years, the categories with the years each one exists, the states, regions and
  parameter codes, and every engine function with its parameters, its docstring (definition and method) and the
  Annexure A questions that use it. A new engine function appears in the chat automatically.
- **Step 2, the plan (`nlq/planner.py`):** the model must answer with ONE JSON object of four allowed shapes:
  `engine` (engine, function, params, title, assumptions, follow-ups), `custom` (filters, group_by, metric,
  aggregation, chart: for questions no analysis covers), `clarify` (a question back, with options as buttons) or
  `out_of_scope` (e.g. "what's the weather", fees, salaries; a prediction is not out of scope, see below). The shape and types are checked with
  pydantic, then the names are checked against the code (does `trends.rank_trajectory` exist? is `region` a group?).
  If the JSON is invalid or a name does not exist, the model is asked once more with the error message.
- **Step 3, name resolution (`nlq/resolve.py`, fixed rules):** institutions: known short forms first (iitb, iitkgp,
  iima, nitt, LPU, KIIT, IIIT Bangalore, iiitb, MAHE, ISM Dhanbad, SRMIST, JU, CMC Ludhiana, JIPMER, PGI, NLU Delhi,
  RVCE, MIT Manipal, LSR, SOA, TIFR, ICT Mumbai, NIPER Mohali ...), then the dashboard's institution matcher (see
  "Institution names" above: exact name, word match, close spelling last, the family and place guards, never-ranked
  participants, the family swap). A name two institutions share is shown with its city ("National Law University
  (New Delhi)" vs "(Cuttack)"). Well-known institutions NIRF does not rank are said plainly: "The Indian School of
  Business (ISB) does not appear in any NIRF ranking"; "BITS Pilani's Goa campus is not ranked on its own in NIRF:
  only BITS Pilani ... appears", with a button for BITS Pilani;
  states: codes and old names (TN, KA, UP, Orissa), one-letter slips ("Telengana" = Telangana: similarity ≥ 87 and
  clearly ahead of the next state; Andhra and Madhya Pradesh are 86 apart, so they never mix), cities as their state
  (Mumbai, Bangalore, Chennai, Kolkata, Hyderabad, Pune ...), and regions ("South India", "the north-east", "north
  India") as the states of that region in the data's region column, with a note listing them;
  parameters: everyday words (research -> RPC, teaching -> TLR, placements -> GO, reputation -> PR), also with
  "score" ("research score"); a NIRF sub-parameter maps to its parameter with the note "NIRF publishes only the 5
  parameter scores, not the sub-parameters" (patents -> RPC, student strength and faculty ratio -> TLR, median
  salary -> GO, women / regional diversity -> OI); in Research Institutions, which has no RPC, research -> QnR
  (Quantitative Research) and teaching -> SFC, with a note;
  categories: engg / B.Tech -> Engineering, B-schools / MBA colleges -> Management, pharmacy colleges -> Pharmacy,
  MBBS colleges -> Medical, architecture colleges / planning -> Architecture & Planning, law universities -> Law, agri
  colleges -> Agriculture, arts (and science) colleges -> College, sustainability -> SDG; nursing and polytechnics
  get "NIRF has no Nursing ranking ...";
  years: numbers, ranges and phrases ("last 3 years" = the latest 3 years in which that category was published,
  "since 2020" = "2020 se", "latest", "pichhle 5 saal", "recent years" = the latest 3, "over the years" / "last
  decade" = every year, "2020s", "'21" = "2k21" = 2021, "FY2024" = 2024, "2024-25" = NIRF 2025 because NIRF names a
  ranking by the year it is published, "three years ago" = the calendar year three years back). A year with no
  ranking is not returned as an empty year: "There is no NIRF ranking for 2026 in the data: the latest NIRF ranking
  is 2025", "Dental starts in 2020 ..."; in an engine plan the chat instead moves it to the nearest year and says so
  ("Dental rankings exist only for 2020-2025, so 2020 is shown (the nearest to 2018)"). Every translation is written as a plain sentence ("I read 'TN' as Tamil Nadu.",
  "I read 'Jadavpur Universty' as Jadavpur University, the closest spelling in the NIRF data.", "There's no IIT
  Bangalore in the NIRF rankings, so I assumed you meant IIIT Bangalore (International Institute of Information
  Technology Bangalore).").
- **Step 4, running (`nlq/executor.py`):** years are fitted to the function (a list, one year = the latest asked for,
  or two years = the first and last asked for; given the wrong way round, "from 2024 to 2019", they are swapped,
  because a change is always measured from the earlier to the later year, and the swap is listed as an assumption); `states` on any analysis limits it to institutions in those states
  (ranks stay national); `institute_types` (or "IITs", "all IIMs", "the NITs" written as an institution, or such a
  plural in the question of an analysis that covers every institution) limits it to those institute types, so "Which
  IITs improved the most in Engineering since 2019?" ranks only IITs and the answer starts "Among IITs only" (a bare
  "IIT" on a chart of named institutions still asks which IIT); options a function does not have are dropped and listed. Only the 8 engines' public
  functions or the Chart Builder can be called. Nothing the model writes is run as code (no `exec`/`eval`; a test
  checks the syntax tree of `nlq/`).
- **What the page shows:** the chart card (chart, one-line answer, method, data + CSV), directly under it an
  **"Assumed:"** box with every assumption as a plain sentence, one-click buttons for the other institutions the person
  may have meant ("Use IISc instead", "Use IIM Bangalore instead": they re-run the same plan with that institution,
  without asking the model again), "How I understood your question" (the assumptions again and the plan JSON,
  including `resolved_call`, the exact call we ran), and 3 follow-up questions as buttons. For an institution that
  took part but was never ranked, the page shows the "took part, but never ranked" message instead of an error, with
  buttons for two similar ranked institutions. Six example chips sit above the input; earlier turns are sent with a new question
  so "same for Engineering" works.
- **When the model cannot be reached:** no key, no internet, a rejected key, a used-up quota, an unknown model name or
  a server problem each get a plain message and a fix. If `GEMINI_API_KEY_2` exists it is tried once first. The page
  then offers the closest sample questions, found without any model: the share of the typed words (filler words
  removed, synonyms such as most/highest merged) that also appear in the sample question. "Run Qx.y here" answers
  it in the chat; links open it in the Question Bank and the matching Explore page. The sidebar shows a green or red
  dot: is a key loaded, and does Gemini accept it (checked by asking for the model's description, no text generated).
- **Accuracy test:** 33 varied questions (typos, Hinglish, abbreviations, informal phrasing, a custom chart, an
  out-of-scope question, and 8 edge cases: an institution not in Overall, years before an institution existed, a
  band-only college, two predictions, an opinion, a vague name and a city), each with the acceptable analyses.
  Offline, each reference plan must give a chart from the expected analysis (or the "which one?" buttons); live, the
  model's plan must name an expected analysis, and a prediction or opinion must also carry its notice. Accuracy =
  correct plans / 33. The live test is opt-in (`NIRF_LIVE_TESTS=1`), so a normal test run never uses up the free
  daily quota the demo needs.

### Ask NIRF adapts to what the data actually has (`nlq/adapt.py`)
The model only reads the question; it does not know which lists an institution is in, or in which years. After the
names are resolved, fixed rules fit the plan to the data, and every change is written in the "Assumed:" box.
- **Category auto-pick:** when the question names institutions but no category, Overall is used if every named
  institution is in the Overall ranking in every year asked. Otherwise: one institution -> the category it is ranked
  in for the most years (ties: the most recent, then Overall); several -> the category they share for the most years
  (years in which all of them are listed count first); none shared -> each is shown in its own category, one chart
  each, with the note that ranks from different lists are not comparable. Example: "Give me the line chart for
  rankings of IIIT Bangalore from 2017-2025" -> "IIIT Bangalore is not in the Overall ranking; it is ranked in
  Engineering (2018-2025), so I used Engineering." If the model still wrote Overall but the question never said
  "overall", the rule is applied anyway.
- **Years the institution actually has:** the asked years are cut to the span from the first to the last year the
  institutions are listed in that category; a year inside the span where one is missing stays as a gap. "You asked for
  2017-2025; IIT Dharwad is ranked in Engineering only in 2023-2025, so the chart shows those years." Missing years are
  never filled in.
- **Years a category does not have:** a typed year outside a category's years becomes the nearest year it has, and the
  answer says so ("SDG rankings exist only for 2025, so 2025 is shown (the nearest to 2019)."). Categories that start
  later: Dental 2020, Research Institutions 2021, Agriculture and Innovation 2023, Open / Skill / State Public
  University 2024, SDG 2025. A range that starts too early is cut ("Research Institutions rankings exist only for
  2021-2025, so 2021-2025 are shown.").
- **Band-only colleges:** a rank question about an institution that has no exact rank in the chosen category and years
  is drawn with `trends.band_history` (see above), with the assumption saying why. A score or parameter question about
  such an institution does not draw an empty chart: the answer says "NIRF did not publish scores for ..." with its
  bands, and a button runs the band chart.
- **Predictions and opinions:** "Will IIT Mandi overtake IIT Jodhpur?", "Who will be #1 in 2026?", "Which is better,
  IIT Madras or IIT Bombay?" are not refused. The plan has an optional `notice` field; the model answers with the
  closest factual analysis (usually the rank line of the named institutions, or the top of the latest ranking) and the
  notice "I can't predict future rankings; here is how they have done so far.", shown in a highlighted box above the
  chart. The insight states the plain fact (who is ahead in the latest year and how the gap changed). No forecast line
  is ever drawn.
- **Vague names:** "NIT", "IIT", "IISER" (only a family typed) or "Christian Medical College" (two campuses) get "Which
  one did you mean?" with up to 4 buttons of real institutions, best known first (best Overall rank in their latest
  year). A click re-runs the same plan with that institution, without the model.
- **Cities as places:** "Bangalore colleges", "colleges in Pune": the city goes in `states` and becomes its state, with
  the assumption "'Bangalore' = Karnataka (we filter by state, not city)." (The state of a city is read from the
  institutions located there, plus a short list of big cities.)
- **Two questions in one message:** the first is answered; the second becomes the first follow-up button, and a
  highlighted notice says so ("Your message asks two things; this chart answers the first. The second is the first
  suggestion below.").
- **Short requests are answered, not asked back:** "NIT ranking", "IIM ranks" (a type of institute and nothing else)
  draw today's top 10 of that type followed back in time (`trends.top_n_race` with the institute-type filter).
  "Bangalore colleges in engineering 2025" lists the Karnataka Engineering institutions of 2025 with their ranks;
  "SDG ranking in 2019" draws the SDG list of 2025 (the nearest year) instead of a refusal.
- **Category for a type of institute:** when the question names a type but no category, the category is the ranking
  list with the most institutes of that type: NITs (31 in Engineering, 21 in Overall) and IITs → Engineering, IIMs →
  Management, NLUs → Law, NIPERs → Pharmacy, AIIMS → Medical (7 in each of Medical and Overall: on a tie the subject
  ranking wins), IISERs → Overall. The Assumed box gives the counts.
- **Our reason replaces the model's guess:** whenever our code chooses the category (including Overall because the
  institution is in Overall every year), the model's own sentence about the category is removed and ours is shown:
  "Category: Overall, because none was named and IIT Bombay is in the Overall ranking in every year."

## Exam simulation (Phase 14): 30 new questions, UI path and chat

- **What:** `tests/exam_questions.py` holds 30 examiner questions that are not in Annexure A, across all 8 sections,
  with the tricky cases on purpose: an institution missing in some years, a category that only exists from 2023, a
  state with only one institution, a start year after the end year, tied ranks and band-only ranks.
- **UI path:** the real app is opened headless (Streamlit AppTest), the view is picked and the controls are set as a
  person would. Pass = the app draws exactly the chart of the analysis those settings stand for (same title as the
  direct engine call), or, when the data cannot answer as asked (correlation for one institution, a year before the
  category existed), a message card that explains why.
- **Ask NIRF:** the question is planned by the live Gemini model; the plan is recorded in `tests/exam_chat_plans.json`
  and replayed offline through our executor. Pass = an acceptable analysis run with the settings the question asks
  for (category, years, institutions, states, parameters), or the same explanation as the UI.
- **Run:** `python -m scripts.exam_simulation` (replay) or `--live` (ask the model first); results, the failures found
  on the first run and their fixes: `docs/exam_simulation.md`. Tests: `tests/test_exam.py`.
