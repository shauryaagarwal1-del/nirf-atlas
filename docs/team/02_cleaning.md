# 02 · Cleaning: from 290 messy tables to one master table

**In one sentence:** the pipeline stacks all 290 raw files, standardises names, states, categories, ranks and
numbers with rules we can explain, never invents a missing value, and produces **one master table**:
`data/processed/nirf_master.parquet`, 11,647 rows, one row per **(year, category, institution)**.

Deeper reference: `docs/data_audit.md` (the problems we found before cleaning), `docs/cleaning_report.md` (every
step with rows before/after and real examples), `docs/methods.md` (Steps 2–4). The **Data & Method** page in the
dashboard shows the same steps live.

---

## 1. What it does and why

Raw data is messy in ways that silently break charts:

| Problem we found in the raw files | What would go wrong without cleaning |
|---|---|
| "Jammu & Kashmir", "Jammu And Kashmir", "Pondicherry" vs "Puducherry" (49 spellings for 34 states/UTs) | A state count would split one state into several bars; the map would miss states |
| "Indian Institute of Technology, Delhi" (2022) vs "Indian Institute of Technology Delhi" (other years); UPES renamed; 2,288 spellings for 1,647 institutions | IIT Delhi's 2022 rank would vanish from its line; trends and "new entrant" counts would be wrong |
| "Research" (2021–23) vs "Research Institutions" (2024–25) | A trend line would stop at the rename |
| Ranks as text: `21A`, ties (two institutions at 100), `Rank Withdrawn`, bands like `101-150` | Ranks could not be sorted, subtracted or filtered ("top 50") |
| Scores stored as text | No means, medians or correlations possible |
| Participant lists mixed with rankings | Every "number of ranked institutions" would be 5–6 times too large |
| UPPER CASE names, double spaces, broken apostrophes, PIN codes in names | One name looks like two; charts look broken |

Before writing any rule we ran a **data audit** (`docs/data_audit.md`): a read-only report that counts rows per
year × category, lists every state spelling, every rank format, missing values, duplicates and name variants. Every
cleaning rule fixes a problem the audit proved exists.

---

## 2. The pipeline, step by step (what to say in the viva)

```
 290 raw CSVs (75,626 rows)
   |
   | 1  Combine all files into one table
   | 2  Column names to one style (snake_case: "Institute ID" -> institute_id)
   | 3  Year to a whole number
   | 4  Standard category names    (21 labels -> standard names; original label kept)
   | 5  Standard state names       (49 spellings -> 34 states/UTs) + region
   | 6  Text tidy                  (case, spaces, commas, apostrophes, PIN codes)
   | 6b Split: ranked rows stay (11,647) | participant lists go to their own table (63,979)
   | 7  Institution identity       (2,288 spellings -> 1,647 institutions)
   | 8  Ranks, ties and rank bands
   | 9  Numbers to decimals + range check (0-100)
   | 10 Missing values: flagged, NEVER filled in
   | 11 Duplicates: removed and logged (0 found)
   | 12 Derived columns: first year seen, new entrant, years present
   v
 nirf_master.parquet: 11,647 rows x 45 columns   (+ a .csv copy)
```

| Step | What it does | Why |
|---|---|---|
| 1 Combine | Stack 290 files; files with fewer columns get blank cells | Every rule must see all years at once (to spot that two spellings are one state) |
| 2 Column names | One naming style; the odd "Band" column of Innovation 2023 moved into the rank column | Every engine and the chat refer to the same columns in every year |
| 3 Year | Text → integer; checked that each row's year equals its file's year folder (0 mismatches) | Years must sort, filter as ranges and draw time axes |
| 4 Category | A hand-checked table maps each (label, year) to one standard name; `category_original` keeps NIRF's label | A trend runs across renames; history stays honest |
| 5 State | A hand-checked table maps 49 spellings to the 34 official states/UTs and adds a region (Ministry of Home Affairs zonal councils + North-East) | Counts, maps and state comparisons need one name per state |
| 6 Text tidy | UPPER CASE → Title Case, spacing, commas, hyphens, broken apostrophes, PIN codes removed (10,491 rows touched); words never changed | Invisible differences would make one name look like two |
| 6b Split | Participant lists and the 2018 Special Mention go to `nirf_participants.parquet` | They have no rank, so they must never count as "ranked" |
| 7 Identity | One `institution_key` per real institution (details below) | Every trend, mobility and new-entrant question follows one institution over the years |
| 8 Ranks | Keep the raw text; clean integer `rank` for exact ranks; ties flagged; `21A` keeps 21 and is flagged; withdrawn = empty; bands get no exact rank; every row gets a standard `rank_band` and `in_top10/50/100` | "Top 50", "moved from 51–100 into the top 50", "same band next year" become simple filters |
| 9 Numbers | Scores to decimals; anything outside 0–100 would become missing (0 found); a better rank never has a lower score (0 violations) | Statistics need numbers; an out-of-range value can only be an error |
| 10 Missing | Nothing filled in. Flags `has_score`, `has_parameter_scores` + a table of reasons | A made-up value would look like real NIRF data |
| 11 Duplicates | Exact copies and repeated (year, category, institution) removed and written to a log (0 found) | One institution must not be counted twice |
| 12 Derived | `first_year_seen`, `is_new_entrant`, `years_present` per institution per category | Needed for new-entrant (Q2.5) and consistency questions |

---

## 3. The hardest part: deciding which names are the same institution (step 7)

Ladder of evidence, from strongest to weakest:

1. **Same matching key + same state = same institution.** The matching key is the name in lower case, `&` → `and`,
   punctuation removed, "Govt" → "government", "Bangalore" → "Bengaluru". (Plus the city when one name means two
   different colleges in one state, e.g. several "Government College"s.)
2. **NIRF's own ID code** (stable from 2018): same code core = same institution (210 links).
3. **Hand-written alias rules** in `data/mappings/institution_alias_rules.csv`, each with a note saying why (1 link).
   Example: in 2017 the Engineering list printed "Indraprastha Institute of Information Technology-New Delhi (IIIT
   New Delhi, Delhi)" while every other list used "Indraprastha Institute of Information Technology". The similarity
   was only 81, so the pair waited in the review file and IIIT Delhi had two keys: its 2017 Engineering rank (56)
   was cut off from its line, and in 2018 it was wrongly counted as a new entrant. Same city, never twice in one
   list, so one checked rule joins them.
4. **"Name = other name + its own city"** (e.g. "X" and "X, Chennai" in Tamil Nadu) (55 links).
5. **Fuzzy matching** (rapidfuzz `token_sort_ratio` ≥ 92, same state): sort the words of each name, then measure
   how many character edits turn one into the other, as a 0–100 similarity (42 links).

Safety rules:
- **Two rows of the same ranking list are never merged**: if NIRF lists them separately in one year, they are
  different institutions.
- **Uncertain pairs are not guessed.** Pairs scoring 80–92, or ≥ 92 with evidence against them (different cities,
  different ID codes, each name has its own distinguishing word), go to `data/mappings/institution_review.csv`
  for a human yes/no. The audit showed why: fuzzy matching alone both misses real renames and wrongly merges
  different campuses of one university.
- `canonical_name` = the institution's most recent name.

---

## 4. How ranks are handled (know this well; many questions depend on it)

| What NIRF printed | `rank` (number) | `rank_status` | Notes |
|---|---|---|---|
| `7` | 7 | exact | |
| `100` twice (a tie) | 100 for both | exact, `is_tie` = yes | NIRF uses competition ranking: 1, 2, 2, 4 (the next rank is skipped) |
| `21A` (2018) | 21 | lettered | Kept its number, flagged |
| `Rank Withdrawn` | empty | withdrawn | 2 rows |
| Listed on the "101-150" band page | **empty** | band | `rank_band` = 101-150; we never invent a mid-point like 125 |

Counts: 6,971 exact + 3 lettered = 6,974 rows with a usable exact rank; 4,671 band-only; 2 withdrawn; 333 rows
share a rank with another institution.

**"In the top N" means *certainly* in the top N:** the exact rank is ≤ N, or the *worst* rank of NIRF's band is
≤ N. A row in band 76–100 is certainly in the top 100; a row in band 101–150 is not. We call the worst possible
rank `rank_upper`.

**Exact ranks only, when a rank is used as a number.** Subtracting ranks (improvement), averaging them or drawing a
box plot of ranks needs exact numbers, so band-only rows are left out and the method text says how many.

---

## 5. Validation: how we proved the table is right

Automatic tests (`tests/test_data.py`, `tests/test_master.py`) compare the master table with things outside the
cleaning code:

1. **No duplicates:** no (year, category, institution) appears twice.
2. **States:** every state is one of India's 28 states + 8 UTs, typed from the official list (not read from our own
   mapping, so a wrong mapping would be caught).
3. **Ranges:** every score and parameter is between 0 and 100.
4. **Rank agrees with score:** inside each list, nobody has a score more than 0.01 above someone ranked better.
5. **Coverage:** every year 2017–2025 is present, and each year has exactly the categories NIRF published.
6. **Nothing silently lost:** for every (year, category), master rows = raw ranked rows − logged duplicates.
7. **Known cases:** renames such as UPES and IISc are one institution; same-name colleges in different cities stay
   apart.

**Spot check:** a separate small reader (not the scraper's code) re-read the saved web pages and compared every
field of **all 11,647 rows** (116,470 fields) with the master table. Result: **0 real differences, 0 institutions
missing**. Every difference was an intended cleaning (487 tidied names/cities, 104 states renamed such as
Pondicherry → Puducherry).

**Bonus check on the weights:** for every category-year we fitted overall score = w1·TLR + w2·RPC + w3·GO +
w4·OI + w5·PR by least squares. The fitted weights are exactly NIRF's published weights and reproduce every score
to within 0.02 (rounding). So the scores in our table are internally consistent with NIRF's own formula. A test
(`tests/test_data.py`) checks this on every scored row. (The weights are in `viva_cheatsheet.md`.)

---

## 6. Concepts explained simply

- **Data cleaning:** fixing a dataset so the same thing is always written the same way, numbers are numbers, and
  errors and gaps are visible, without changing what the data says.
- **Standardisation:** choosing one official form for each value (one spelling per state, one name per category).
- **Mapping table (lookup table):** a two-column list "raw spelling → standard name" that a person checked by hand.
  If a new spelling appears in a future scrape, the pipeline stops and asks instead of guessing.
- **Entity resolution (record linkage):** deciding which differently written records are the same real-world
  thing. Here: which names are the same institution.
- **Fuzzy matching:** measuring how similar two texts are (0–100) when they are not exactly equal.
- **Missing value (NaN):** an empty cell meaning "unknown". We distinguish "not published" (Research Institutions
  have no TLR by design) from "blank".
- **Imputation:** filling a missing value with a guess (e.g. the average). **We deliberately do not impute**: every
  chart shows only values NIRF really published.
- **Duplicate:** the same record appearing twice.
- **Competition ranking ("1224"):** tied items share a rank and the next rank is skipped.
- **Parquet:** a compact, fast file format for tables that also remembers each column's type (a CSV copy is kept
  for people who want to open it in Excel).
- **Single source of truth:** one table every chart reads from, so two pages can never disagree.

---

## 7. Likely viva questions with model answers

**Q1. What were the main data-quality problems, and how did you fix them?**
Five main ones. (1) The same state spelled many ways: 49 spellings mapped to 34 official states/UTs. (2) The same
institution named differently across years: 2,288 spellings grouped into 1,647 institutions using a matching key,
NIRF's ID codes, alias rules and fuzzy matching, with uncertain pairs sent for human review. (3) Category renames:
a standard name plus the original label. (4) Ranks as text (ties, "21A", "Rank Withdrawn", bands): a clean numeric
rank, flags and a standard band. (5) Participant lists mixed with rankings: moved to a separate table.

**Q2. How did you handle missing values?**
We never fill them in. Institutions listed only in a rank band have no score on the NIRF site, and some categories
(Innovation, SDG, Open and Skill University) publish no scores at all. We keep those cells empty, add flags
(`has_score`, `has_parameter_scores`) and a reason table, and each analysis uses only the rows that really have the
values it needs, saying in its method text how many rows were left out.

**Q3. Why not give band-only institutions the middle of their band, e.g. 125 for 101–150?**
Because that would invent data: the real rank could be anywhere from 101 to 150, and a made-up 125 would look like a
real NIRF number in every chart. Instead we use only facts that are certain: an institution in band 76–100 is
certainly in the top 100. When a rank must be a number (subtracting, averaging), we use exact ranks only and report
how many rows were excluded.

**Q4. How do you know two names are the same institution?**
In order of strength: identical name after normalising (lower case, punctuation removed, "&" to "and") in the same
state; the same NIRF ID code; a hand-checked alias rule; the same name plus its own city; and finally a fuzzy
similarity of at least 92 in the same state. Two rows of the same ranking list are never merged, and uncertain pairs
are left for a human decision rather than guessed.

**Q5. How did you handle categories that changed over time?**
A hand-checked mapping gives each (label, year) a standard name, e.g. "Research" (2021–23) and "Research
Institutions" (2024–25) both become Research Institutions. The label NIRF printed stays in `category_original`, so
historical comparisons are honest, and charts show a category only in the years it existed. New categories simply
start in their first year; nobody is counted as a "new entrant" in a list's launch year.

**Q6. How do you know your cleaned data is correct?**
Automatic tests check no duplicates, valid states from the official list, scores between 0 and 100, rank agreeing
with score, complete coverage, and that no row was dropped without a record. A spot check re-read the original web
pages with an independent reader and compared all 11,647 rows field by field: zero real differences.

**Q7. How did you handle ties and duplicates?**
Ties are real: NIRF uses competition ranking, so two institutions at rank 100 both keep 100 and are flagged `is_tie`.
Duplicates would count an institution twice; we drop exact copies and repeated (year, category, institution) rows
and log every dropped row. We found zero, which confirms the identity step never gives two rows of one list the same
key.

**Q8. What does one row of the master table mean, and what are its key columns?**
One row = one institution in one ranking category in one year. Key columns: `institution_key` and `canonical_name`
(who), `state` and `region` (where), `year`, `category_std` and `category_original` (which list), `rank_raw`, `rank`,
`rank_band` and `in_top10/50/100` (position), `score` and the five parameters `tlr, rpc, go, oi, pr` (marks), and
`is_new_entrant`, `first_year_seen` (history). The full data dictionary is on the Data & Method page.
