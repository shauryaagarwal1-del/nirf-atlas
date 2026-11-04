# Exam simulation: 30 new questions, answered through the dashboard and through Ask NIRF

A rehearsal of the viva as a strict examiner would run it. Thirty questions that are **not** in Annexure A, spread
over all eight sections, with the tricky cases on purpose:

| Tricky case | Questions |
|---|---|
| An institution missing in some years | X01 (IIM Calcutta: Overall only 2017-2019 and 2023), X29 (volatility, ≥ 6 ranked years) |
| A category that only exists from 2023 | X03, X07, X11, X26 (Agriculture & Allied Sectors, ranked 2023-2025) |
| A state with only one institution | X05 (Mizoram vs Meghalaya), X09 and X15 (Goa), X23 (states with 1+ institutions) |
| Start year after end year | X02 (2024 → 2019), X19 (2022 → 2018), X25 (2025 → 2019) |
| Tied ranks | X06 (two institutions share rank 100 in Overall 2020), X17 (IIT Indore and KIIT share rank 27 in 2025), X27 |
| Band-only ranks | X05 (Mizoram University: exact rank only in 2017 and 2020), X10 (Engineering 2024: 200 of 300 band-only), X24 |

Every question is answered **twice**:

1. **UI path**: the page, the view ("What do you want to see?") and the controls a person sets. The real app is opened
   headless (Streamlit AppTest) and the controls are set exactly as listed. Pass = the app draws exactly the chart of
   the analysis those settings stand for (same chart title as the direct engine call), and the one-line answer
   explains the tricky case. For a question the data cannot answer as asked, pass = a message card that says why.
2. **Ask NIRF chat**: the question is typed as written. The live Gemini model writes the plan, the plan is recorded
   in `tests/exam_chat_plans.json`, and our executor runs it. Pass = an acceptable analysis, run with the settings
   the question asks for (category, years, institutions, states, parameters), or the same explanation as the UI.
   "Chat chart = UI chart" says whether the chat drew the very same chart; "no" means it chose other valid settings
   (for example how many names to label).

Run it again: `python -m scripts.exam_simulation` (replays the recorded plans, no internet needed) or
`python -m scripts.exam_simulation --live` (asks the model for questions not recorded yet). The same checks run in
`python -m pytest tests/test_exam.py`.

## First run: what failed, and the fixes

The first run was on the code of the previous phase (commit `5195a45`), with the reference plans for the chat.
**UI path 24/30, Ask NIRF 20/30.** Every failure was fixed and the simulation was run again (results below).

| Question | What went wrong | Fix |
|---|---|---|
| X01 IIM Calcutta 2017-2025 | The answer said "rank 39 in 2017 to rank 99 in 2023 … an exact rank in 4 of 9 years" but did not say which years were missing. | The one-institution answer now names the band-only years and the years the institution was not in the list ("it was not in the Overall list in 2020-2022, 2024-2025"). A single exact rank no longer reads "rank 98 in 2018 → rank 98 in 2018 (±0 places)". |
| X02, X19, X25 start year after end year (chat) | The chat stopped with "The start year (2024) must be before the end year (2019)". | The chat puts the two years in order and says so: "You gave the later year first (2024 → 2019); a change is always measured from the earlier year to the later one, so 2019 → 2024 is shown." The page sliders already keep the years in order; the page now also sorts them before they reach the sidebar filter. |
| X03 Agriculture top 10 every year (chat) | "Agriculture & Allied Sectors has rankings in 3 years (2023-2025), so min_years must be between 1 and 3." The live model instead chose `min_years = 1` ("at least once"), a wrong reading of "every year". | `consistent_top_n` uses every year a category has when min_years is larger, and says so ("Agriculture & Allied Sectors was ranked in only 3 years, so 'at least 5 years' means every year it has"). The chat rules now say that "every year / always" means all published years, never 1; asked again, the model chose `min_years = 3` (its first reading is kept in `tests/exam_chat_plans.json` as `X03_first_reading`). |
| X06 Overall top 100 in 2020 (tie) | "… hold 38% of the 101 places" with no word on why the top 100 has 101 institutions. | The answer adds: "The top 100 holds 101 institutions because 2 share rank 100: Bangalore University and Mizoram University." |
| X09 Goa 2018 summary (one institution) | "the 1 published scores have a mean of 40.7 … with a standard deviation of nan." | With one score the answer says it is at once the mean, median, minimum and maximum, and that one value has no spread. |
| X17 IIT Indore vs KIIT (tie) | Chat: "No institution called 'KIIT'". UI: the answer did not mention the tie. | Common short forms added (KIIT, LPU, IIIT Hyderabad/Delhi/Bangalore, NMIMS, ISI, MDI, FMS, PGIMER, CMC Vellore, IIFT, UoH). A name plus its city now works ("National Law University Delhi"). The profile answer says when all chosen institutions share a rank. |
| X24 into the top 100 (bands) | The answer only covered 51-100 → top 50, not the question asked. | The band-transition answer also counts the institutions that climbed from 101+ (mostly NIRF band-only positions) into the top 100. |
| X26 Agriculture band retention | "retention was highest for 2023→2024 (100%) and lowest for 2023→2024 (100%). Most stable band: 1-10 (100%), least stable: 1-10 (100%)." | When every year pair (or band) has the same value, the answer says "in every pair of years (2023→2024, 2024→2025) it was 100%" and lists the bands present. |

Found while preparing the questions (fixed as well, with tests in this phase's checks):

- **A wrong institution for a short form:** "LPU" was matched to *Sambalpur University* (the letters l-p-u appear inside
  "Samba**lpu**r"). Spelling-based matching is now used only for names of 6 or more letters, and LPU is a known short form.
- **A false message with a state filter:** "Goa, Overall 2025" said "NIRF has no Overall ranking for 2025. Overall
  rankings exist for 2017-2022". It now says "No institution in Goa is in the Overall ranking of 2025 (they appear in
  2017-2022)".
- **An empty chart for a one-institution state:** the rank trajectory for Mizoram (its only institution is band-only
  in 2025) drew "None of these 0 institutions …". The default is now the best-ranked of the latest year that has any
  ranked institution, by exact rank and then by band.
- **Numbers in the wrong order:** "Meghalaya has more exact ranks (2 vs 6 institution-years …)" now reads "(6 vs 2 …)";
  the State comparison says "institutions with an exact rank" instead of "ranked institutions".
- **Grammar:** "1 institutions were in the top 10 every year" → "1 institution was".
- **Tooling:** `scripts/run_all_questions.py` crashed on a Windows console (the minus sign "−" cannot be printed in
  cp1252); the scripts now print UTF-8. A normal `pytest` run sent the 25 chat test questions to Gemini whenever a key
  was present, which used up most of the free daily quota; the live tests are now opt-in (`NIRF_LIVE_TESTS=1`).

Not changed (a team decision): `data/mappings/institution_review.csv` has 208 possible name matches waiting for a
human `approve` (yes/no). Among them are institutions renamed in 2018 that are split into two today, such as
*Thapar University* (2017) and *Thapar Institute of Engineering and Technology* (2018-2025), *Siksha 'O' Anusandhan
University* → *Siksha 'O' Anusandhan*, and *Symbiosis International University* → *Symbiosis International*. Until
they are approved, such an institution starts in 2018 in trend charts and counts as a 2018 new entrant. Only answers
that span 2017 and 2018 are touched (for example X27 counts such a rename as one exit and one entry in 2018).

## Results of the latest run

<!-- results:start -->
_Last run: 05 November 2026. UI path: **30/30 pass**. Ask NIRF chat: **30/30 pass** (30 of 30 planned by the live Gemini model). Regenerate with `python -m scripts.exam_simulation`._

| ID | Section | Tricky case | UI path | Chat | Chat plan | Chat chart = UI chart |
|---|---|---|---|---|---|---|
| X01 | 1. Trends | missing in some years | PASS | PASS | `trends.rank_trajectory` | yes |
| X02 | 1. Trends | start year after end year | PASS | PASS | `trends.biggest_movers` | yes |
| X03 | 1. Trends | category only from 2023 | PASS | PASS | `trends.consistent_top_n` | yes |
| X04 | 1. Trends | – | PASS | PASS | `trends.average_score_over_time` | yes |
| X05 | 2. Geography | state with one institution; band-only ranks | PASS | PASS | `geography.compare_states` | no (other valid settings) |
| X06 | 2. Geography | tied ranks at the cut-off | PASS | PASS | `geography.state_counts` | yes |
| X07 | 2. Geography | category only from 2023 | PASS | PASS | `geography.state_representation_change` | yes |
| X08 | 2. Geography | – | PASS | PASS | `geography.new_entrants_by_state` | yes |
| X09 | 3. Univariate | state with one institution | PASS | PASS | `univariate.summary_stats` | yes |
| X10 | 3. Univariate | band-only ranks | PASS | PASS | `univariate.rank_distribution` | yes |
| X11 | 3. Univariate | year before the category existed | PASS | PASS | `univariate.score_distribution` | no (other valid settings) |
| X12 | 3. Univariate | – | PASS | PASS | `univariate.quartile_shares` | yes |
| X13 | 4. Bivariate | – | PASS | PASS | `bivariate.scatter_relation` | yes |
| X14 | 4. Bivariate | – | PASS | PASS | `bivariate.correlation_with_overall` | yes |
| X15 | 4. Bivariate | state with one institution | PASS | PASS | `bivariate.scatter_relation` | same message |
| X16 | 4. Bivariate | – | PASS | PASS | `bivariate.correlation_over_time` | yes |
| X17 | 5. Multivariate | tied ranks | PASS | PASS | `multivariate.parameter_profile` | yes |
| X18 | 5. Multivariate | – | PASS | PASS | `multivariate.gap_finder` | yes |
| X19 | 5. Multivariate | start year after end year | PASS | PASS | `multivariate.improved_despite_decline` | yes |
| X20 | 5. Multivariate | – | PASS | PASS | `multivariate.strongest_weakest_gap` | yes |
| X21 | 6. Distribution | – | PASS | PASS | `distribution.top10_vs_rest` | yes |
| X22 | 6. Distribution | – | PASS | PASS | `distribution.dispersion_by_year` | yes |
| X23 | 6. Distribution | state with one institution | PASS | PASS | `distribution.score_by_state` | yes |
| X24 | 7. Mobility | band-only ranks | PASS | PASS | `mobility.band_transitions` | yes |
| X25 | 7. Mobility | start year after end year | PASS | PASS | `mobility.biggest_rank_moves` | yes |
| X26 | 7. Mobility | category only from 2023 | PASS | PASS | `mobility.band_retention` | yes |
| X27 | 7. Mobility | tied ranks at the cut-off | PASS | PASS | `mobility.top10_entries_exits` | yes |
| X28 | 8. Outliers | – | PASS | PASS | `outliers.unusual_score_jumps` | yes |
| X29 | 8. Outliers | missing in some years | PASS | PASS | `outliers.volatility_vs_peers` | yes |
| X30 | 8. Outliers | – | PASS | PASS | `outliers.strong_param_poor_rank` | yes |

### X01. How has IIM Calcutta's Overall rank changed from 2017 to 2025?
- **Section:** 1. Trends · **tricky case:** missing in some years
- **UI path:** Trends → *Rank of chosen institutions, year by year*; Institutions = IIM Calcutta → PASS
  - shown: IIM Calcutta: rank 39 in 2017 → rank 99 in 2023 (Overall)
  - answer: IIM Calcutta went from rank 39 in 2017 to rank 99 in 2023 in Overall (−60 places); its best rank was 26 (first reached in 2019) and it had an exact rank in 4 of 9 years; it was not in the Overall list in 2020-2022, 2024-2025.
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `trends.rank_trajectory` → PASS
  - shown: IIM Calcutta: rank 39 in 2017 → rank 99 in 2023 (Overall)
  - how it understood the question: Institution: IIM Calcutta; Category: Overall; Years: 2017 to 2025; I read 'IIM Calcutta' as Indian Institute of Management Calcutta; You asked for 2017-2025; IIM Calcutta is ranked in Overall only in 2017-2019, 2023, so the chart shows 2017-2023.

### X02. Show the biggest Overall climbers with start year 2024 and end year 2019.
- **Section:** 1. Trends · **tricky case:** start year after end year
- **UI path:** Trends → *Biggest climbers between two years*; From year → to year dragged to 2024 → 2019 → PASS
  - shown: Saveetha Institute of Medical and T… climbed the most in Overall, 2019→2024 (+45 places)
  - answer: Between 2019 and 2024, Saveetha Institute of Medical and Technical Sciences climbed the most in Overall: from rank 67 to 22 (+45 places). Of the 76 institutions with an exact rank in both years, 32 moved up, 39 moved down and 5 kept the same rank.
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `trends.biggest_movers` → PASS
  - shown: Saveetha Institute of Medical and T… climbed the most in Overall, 2019→2024 (+45 places)
  - how it understood the question: Category: Overall, as specified in the question; Start year: 2024; End year: 2019; Direction: up (climbers); Limit: top 10 movers; You gave the later year first (2024 → 2019); a change is always measured from the earlier year to the later one, so 2019 → 2024 is shown.

### X03. Which Agriculture institutions stayed in the top 10 in every year they were ranked?
- **Section:** 1. Trends · **tricky case:** category only from 2023
- **UI path:** Trends → *Who stayed in the top N for many years*; Category = Agriculture & Allied Sectors (the 'at least … years' slider now stops at 3) → PASS
  - shown: 10 institutions were in the Agriculture & Allied Sectors top 10 in at least 3 of 3 years
  - answer: 10 institutions were in the Agriculture & Allied Sectors top 10 in at least 3 of the 3 years (2023-2025); 10 of them were there every year: Indian Agricultural Research Instit…, ICAR - National Dairy Research Inst…, Punjab Agricultural University, Banaras Hindu University, Indian Veterinary Research Institut…, Tamil Nadu Agricultural University, Central Institute of Fisheries Educ…, G.B. Pant Universtiy of Agriculture…, Sher-e-Kashmir University of Agricu…, Chaudhary Charan Singh Haryana Agri….
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `trends.consistent_top_n` → PASS
  - shown: 10 institutions were in the Agriculture & Allied Sectors top 10 in at least 3 of 3 years
  - how it understood the question: Category: Agriculture & Allied Sectors, as specified in the question; Top N: 10 institutions; Minimum years: 3 (since Agriculture & Allied Sectors has been published from 2023 to 2025, covering all 3 years).

### X04. How has the median score of Engineering institutions changed over the years?
- **Section:** 1. Trends
- **UI path:** Trends → *Average or median score per year*; Categories = Engineering; Statistic = Median → PASS
  - shown: The median Engineering score rose from 43.3 in 2017 to 55.6 in 2025
  - answer: The median Engineering score went from 43.3 in 2017 to 55.6 in 2025 (+12.3 points); the middle 50% of institutions scored between 49.2 and 62.1 in 2025 (IQR 12.9, was 12.5). Careful: the number of scored institutions changes over the years in Engineering (e.g. Engineering: 100 in 2017-2018, 2023-2025; 200 in 2019-2022); set top_n=100 for a like-for-like comparison.
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `trends.average_score_over_time` → PASS
  - shown: The median Engineering score rose from 43.3 in 2017 to 55.6 in 2025
  - how it understood the question: Category: Engineering, as specified in the question; Statistic: Median score, as requested.

### X05. How do Mizoram's institutions compare with Meghalaya's in the Overall ranking?
- **Section:** 2. Geography · **tricky case:** state with one institution; band-only ranks
- **UI path:** Geography; Tab State vs State; State A = Mizoram; State B = Meghalaya → PASS
  - shown: Meghalaya leads Mizoram on both the number and the rank of its Overall institutions | Meghalaya's Overall institutions rank higher than Mizoram's (median 82.5 vs 97)
  - answer: Over 2017-2025, Meghalaya had more Overall-ranked institutions in 1 of 9 years (on average 1.1 vs 1.0 a year), and also had a better (lower) median rank in 2 of 2 years where both have one (pooled median 82.5 vs 97).
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `geography.compare_states` → PASS
  - shown: Meghalaya's institutions rank better in Overall (median 82)
  - how it understood the question: Category: Overall; States compared: Mizoram and Meghalaya.

### X06. Which states had the most institutions in the Overall top 100 in 2020?
- **Section:** 2. Geography · **tricky case:** tied ranks at the cut-off
- **UI path:** Geography → *States with the most institutions in the top list*; Tab More views; Year = 2020; Top list = 100 → PASS
  - shown: Tamil Nadu has the most Overall top-100 institutions in 2020 (18)
  - answer: In 2020, Tamil Nadu has the most institutions in the Overall top 100 (18); the top three states (Tamil Nadu 18, Maharashtra 12, Uttar Pradesh 8) hold 38% of the 101 places, spread over 24 states/UTs. The top 100 holds 101 institutions because 2 share rank 100: Bangalore University and Mizoram University.
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `geography.state_counts` → PASS
  - shown: Tamil Nadu has the most Overall top-100 institutions in 2020 (18)
  - how it understood the question: Category: Overall, as requested in the query; Year: 2020; Top N: 100, matching 'top 100' in the query.

### X07. Which states gained or lost the most places in the Agriculture top 25 between 2023 and 2025?
- **Section:** 2. Geography · **tricky case:** category only from 2023
- **UI path:** Geography → *States that gained or lost places in the top list*; Tab More views; Category = Agriculture & Allied Sectors; Top list = 25 (years start at 2023 by themselves) → PASS
  - shown: Uttar Pradesh gained the most Agriculture & Allied Sectors top-25 places, 2023→2025 (+2)
  - answer: Between 2023 and 2025, Uttar Pradesh improved Agriculture & Allied Sectors top-25 representation the most (+2, 2 → 4); Tamil Nadu lost the most (−2). 5 states gained, 5 lost and 9 stayed the same.
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `geography.state_representation_change` → PASS
  - shown: Uttar Pradesh gained the most Agriculture & Allied Sectors top-25 places, 2023→2025 (+2)
  - how it understood the question: Category: Agriculture & Allied Sectors, as specified in the question; Time range: 2023 to 2025, matching the published years for this category; Top N: 25, based on the question's mention of 'top 25'.

### X08. Which states produced the most new Medical institutions in the rankings since 2019?
- **Section:** 2. Geography
- **UI path:** Geography; Tab New entrants; Category = Medical; Years = 2019-2025 → PASS
  - shown: Tamil Nadu produced the most new Medical entrants (6, 2019-2025)
  - answer: Of 41 institutions that entered the Medical ranking for the first time in 2019-2025, Tamil Nadu produced the most (6, 15%), followed by Karnataka (5) and Maharashtra (4).
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `geography.new_entrants_by_state` → PASS
  - shown: Tamil Nadu produced the most new Medical entrants (6, 2019-2025)
  - how it understood the question: Category: Medical, as specified in the question; Timeframe: since 2019, applied to the Medical ranking category which started in 2018; I read 'since 2019' as 2019-2025.

### X09. What are the mean, median, minimum and maximum Overall scores of Goa's institutions in 2018?
- **Section:** 3. Univariate · **tricky case:** state with one institution
- **UI path:** Distributions → *Average, median, minimum and maximum score*; Year = 2018; Only states = Goa → PASS
  - shown: Overall 2018: only one published score (40.7, Goa University)
  - answer: Among institutions in Goa: In Overall 2018, only one institution has a published score: Goa University with 40.7, which is at once the mean, median, minimum and maximum; one value has no spread, so the standard deviation and IQR cannot be calculated.
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `univariate.summary_stats` → PASS
  - shown: Overall 2018: only one published score (40.7, Goa University)
  - how it understood the question: Category: Overall, as requested; Year: 2018, as requested; State: Goa, as requested; Metric: Overall score; Only institutions located in Goa are included (ranks stay national).

### X10. How many Engineering institutions sit in each rank band in 2024, including those NIRF lists only as a band?
- **Section:** 3. Univariate · **tricky case:** band-only ranks
- **UI path:** Distributions → *How many institutions sit in each rank band*; Category = Engineering; Year = 2024 → PASS
  - shown: Engineering 2024: 300 institutions ranked, 100 with an exact rank
  - answer: In Engineering 2024, NIRF ranked 300 institutions: 100 with an exact rank (1-100) and 200 only within bands (101-150: 50, 151-200: 50, 201-300: 100); 2 institutions share a rank with another (ties).
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `univariate.rank_distribution` → PASS
  - shown: Engineering 2024: 300 institutions ranked, 100 with an exact rank
  - how it understood the question: Category: Engineering, as requested; Year: 2024, as specified.

### X11. Show the score distribution of Agriculture institutions in 2020.
- **Section:** 3. Univariate · **tricky case:** year before the category existed
- **UI path:** Distributions → *Score distribution in one year*; Category = Agriculture & Allied Sectors: the Year list offers only 2023, 2024, 2025 → PASS
  - shown: Agriculture & Allied Sectors 2025: most scores lie<br>between 50 and 61; the distribution is right-skewed
  - answer: In Agriculture & Allied Sectors 2025, the 40 published scores run from 46.9 to 89.2; the mean is 57.2 and the median 55.5, so the distribution is right-skewed: a few high scorers pull the mean above the median (skewness 1.48).
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-05) → `univariate.score_distribution` → PASS
  - shown: Agriculture & Allied Sectors 2023: most scores lie<br>between 44 and 57; the distribution is right-skewed
  - how it understood the question: Category: Agriculture & Allied Sectors, as named in the question; Year: 2020. Note that Agriculture & Allied Sectors rankings were first published in 2023, so the engine will move this request to the nearest available year (2023) automatically; Agriculture & Allied Sectors rankings exist only for 2023-2025, so 2023 is shown (the nearest to 2020).

### X12. What share of Management institutions falls in each statistical quartile in 2022?
- **Section:** 3. Univariate
- **UI path:** Distributions → *Share of institutions in each score quartile*; Category = Management; Year = 2022; Quartiles = Statistical Q1/Q2/Q3 → PASS
  - shown: Management 2022 quartile cut points: Q1 45.1, median 50.4, Q3 57.8
  - answer: Statistical quartiles split the 101 Management 2022 institutions into four groups of about 25% each by construction (26%, 25%, 25%, 25%); what they tell us are the cut points: a quarter score below 45.1, half below 50.4, and the top quarter above 57.8.
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `univariate.quartile_shares` → PASS
  - shown: Management 2022 quartile cut points: Q1 45.1, median 50.4, Q3 57.8
  - how it understood the question: Category: Management, as specified in the question; Year: 2022, as specified in the question; Mode: statistical, to calculate the data's own quartiles (Q1, median, Q3).

### X13. In Medical 2025, how strongly is Perception related to the overall score?
- **Section:** 4. Bivariate
- **UI path:** Relationships → *Any two numbers: scatterplot and correlation*; Category = Medical; Year = 2025; X axis = PR; Y axis = Overall score → PASS
  - shown: PR and Overall score: strong positive relationship in Medical 2025 (r = 0.79)
  - answer: In Medical 2025, PR and Overall score have a strong positive relationship (Pearson r = 0.79 · Spearman ρ = 0.65 · R² = 0.62 · p < 0.001 · n = 50); the straight line explains 62% of the variation in Overall score, and 10 more PR points go with +3.4 Overall score points on average.
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `bivariate.scatter_relation` → PASS
  - shown: PR and Overall score: strong positive relationship in Medical 2025 (r = 0.79)
  - how it understood the question: Category: Medical, as explicitly named; Year: 2025, as explicitly named; Variables: Perception (pr) and overall score (score).

### X14. Which parameter is most correlated with the overall score in Pharmacy 2019?
- **Section:** 4. Bivariate
- **UI path:** Relationships → *Which parameter is most linked to the overall score*; Category = Pharmacy; Year = 2019 → PASS
  - shown: RPC tracks the overall score most closely in Pharmacy 2019 (r = 0.89)
  - answer: In Pharmacy 2019, RPC (Research & Professional Practice) has the strongest correlation with the overall score (r = 0.89, p < 0.001), followed by PR (r = 0.67); the weakest is OI (r = 0.54). Among the parameters themselves, GO and OI move together the most (r = 0.55).
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `bivariate.correlation_with_overall` → PASS
  - shown: RPC tracks the overall score most closely in Pharmacy 2019 (r = 0.89)
  - how it understood the question: Category: Pharmacy, as specified in the question; Year: 2019, as specified in the question; View: bar chart to easily compare the correlation coefficients of each parameter.

### X15. How is research related to the overall score for institutions in Goa in 2018?
- **Section:** 4. Bivariate · **tricky case:** state with one institution
- **UI path:** Relationships → *Any two numbers: scatterplot and correlation*; Year = 2018; Only states = Goa (X = RPC, Y = Overall score are the defaults) → PASS
  - shown: ? This selection has no answer Only 1 Overall institutions in 2018 have both RPC and Overall score; at least 3 are needed for a correlation. (Only institutions in Goa are included; clear the state filter to use all of India.) Try a wider year range, another category, or clear the state and institution filters. /* NIRF Atlas: "National Observatory" refinements on top of .streamlit/config.toml. Light-mode tokens are defined here; assets/style-dark.css redefines the same tokens for dark mode and is injected after this file when the dark theme is active. Chart colours live in core/theme.py. */ :root { --ink: #141b3d; --ink-2: #4a5274; --ink-3: #7c83a1; --bg: #f4f5f9; --surface: #ffffff; --surface-2: #f8f9fc; --border: #dce0eb; --border-soft: #e8ebf2; --teal: #0e9c8c; --teal-ink: #0b7f72; --teal-soft: #e2f4f1; --marigold: #e39a12; --marigold-ink: #925c00; --marigold-soft: #fdf4e1; --indigo: #4a50c8; --navy: #121838; --navy-2: #1d2450; --shadow: 0 1px 2px rgba(20, 27, 61, 0.04), 0 6px 20px rgba(20, 27, 61, 0.05); --shadow-hover: 0 2px 4px rgba(20, 27, 61, 0.06), 0 12px 28px rgba(20, 27, 61, 0.09); --font-display: "Fraunces", Georgia, serif; --font-body: "Inter", system-ui, sans-serif; --font-mono: "JetBrains Mono", Consolas, monospace; } /* ---------- page frame ---------- */ [data-testid="stMainBlockContainer"] { max-width: 1320px; padding-top: 2.6rem; padding-bottom: 5rem; } [data-testid="stHeader"] { background: transparent; } [data-testid="stDecoration"] { display: none; } /* ---------- sidebar ---------- */ [data-testid="stSidebar"] [data-testid="stSidebarHeader"] { padding-top: 1.2rem; } [data-testid="stSidebarNav"] [data-testid="stNavSectionHeader"] { font-family: var(--font-mono); font-size: 0.68rem; letter-spacing: 0.14em; text-transform: uppercase; opacity: 0.55; margin-top: 0.6rem; } [data-testid="stSidebarNavLink"] { border-radius: 8px; margin: 1px 0; transition: background 120ms ease; } [data-testid="stSidebarNavLink"][aria-current="page"] { background: rgba(240, 169, 46, 0.14); box-shadow: inset 3px 0 0 #f0a92e; } [data-testid="stSidebarNavLink"][aria-current="page"] span { color: #f6c766 !important; font-weight: 600; } .nirf-side-title { font-family: var(--font-mono); font-size: 0.68rem; letter-spacing: 0.14em; text-transform: uppercase; opacity: 0.6; margin: 0.4rem 0 -0.2rem; } .nirf-side-summary { font-size: 0.8rem; line-height: 1.5; opacity: 0.75; border-top: 1px solid rgba(232, 234, 246, 0.14); padding-top: 0.8rem; margin-top: 0.2rem; } .nirf-side-summary b { font-family: var(--font-mono); font-weight: 500; color: #f6c766; } /* ---------- headings & text ---------- */ .nirf-eyebrow { font-family: var(--font-mono); font-size: 0.72rem; font-weight: 500; letter-spacing: 0.16em; text-transform: uppercase; color: var(--marigold-ink); } .nirf-page-header { padding-bottom: 1.1rem; margin-bottom: 0.4rem; border-bottom: 1px solid var(--border); } .nirf-page-header .nirf-title { font-family: var(--font-display); font-weight: 600; font-size: 2.55rem; line-height: 1.12; letter-spacing: -0.015em; color: var(--ink); margin: 0.35rem 0 0.45rem; font-variation-settings: "opsz" 96; } .nirf-page-header .nirf-subtitle { font-size: 1.04rem; line-height: 1.55; color: var(--ink-2); max-width: 820px; } .nirf-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 0.9rem; } .nirf-chip { display: inline-flex; align-items: center; gap: 6px; font-size: 0.78rem; color: var(--ink-2); background: var(--surface); border: 1px solid var(--border); border-radius: 999px; padding: 3px 11px; } .nirf-chip b { font-weight: 600; color: var(--ink); } .nirf-chip .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--teal); } .nirf-section-title { margin: 2.6rem 0 1rem; } .nirf-section-title .nirf-h2 { font-family: var(--font-display); font-weight: 600; font-size: 1.6rem; letter-spacing: -0.01em; color: var(--ink); margin-top: 0.25rem; } .nirf-section-title .nirf-lead { color: var(--ink-2); font-size: 0.96rem; margin-top: 0.2rem; } /* ---------- hero (home) ---------- */ .nirf-hero { position: relative; overflow: hidden; border-radius: 22px; padding: 3.2rem 3.2rem 2.9rem; color: #eef0fa; background: radial-gradient(1.2px 1.2px at 12% 22%, rgba(255, 255, 255, 0.55), transparent 60%), radial-gradient(1px 1px at 28% 68%, rgba(255, 255, 255, 0.35), transparent 60%), radial-gradient(1.4px 1.4px at 46% 14%, rgba(255, 255, 255, 0.45), transparent 60%), radial-gradient(1px 1px at 58% 82%, rgba(255, 255, 255, 0.3), transparent 60%), radial-gradient(1.2px 1.2px at 71% 36%, rgba(246, 199, 102, 0.7), transparent 60%), radial-gradient(1px 1px at 88% 18%, rgba(255, 255, 255, 0.4), transparent 60%), radial-gradient(1px 1px at 93% 74%, rgba(255, 255, 255, 0.35), transparent 60%), radial-gradient(900px 420px at 92% 120%, rgba(14, 156, 140, 0.32), transparent 60%), radial-gradient(700px 380px at 105% -30%, rgba(227, 154, 18, 0.2), transparent 60%), linear-gradient(135deg, #121838 0%, #1a2150 55%, #17325a 100%); box-shadow: 0 20px 50px rgba(18, 24, 56, 0.18); } .nirf-hero::after { content: ""; position: absolute; inset: 0; background-image: linear-gradient(rgba(255, 255, 255, 0.035) 1px, transparent 1px), linear-gradient(90deg, rgba(255, 255, 255, 0.035) 1px, transparent 1px); background-size: 44px 44px; mask-image: linear-gradient(90deg, transparent 0%, #000 55%, #000 100%); pointer-events: none; } .nirf-hero .orbit { position: absolute; right: -40px; top: 50%; transform: translateY(-50%); width: 440px; height: 440px; opacity: 0.9; pointer-events: none; } .nirf-hero .content { position: relative; z-index: 1; max-width: 640px; } .nirf-hero .nirf-eyebrow { color: #f6c766; } .nirf-hero .title { font-family: var(--font-display); font-weight: 600; font-size: 4.4rem; line-height: 1; letter-spacing: -0.03em; margin: 0.9rem 0 1rem; font-variation-settings: "opsz" 144; color: #ffffff; } .nirf-hero .title em { font-style: italic; font-weight: 500; color: #f6c766; } .nirf-hero .purpose { font-size: 1.16rem; line-height: 1.6; color: rgba(238, 240, 250, 0.82); max-width: 560px; } .nirf-hero .meta { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 1.6rem; } .nirf-hero .meta span { font-family: var(--font-mono); font-size: 0.74rem; letter-spacing: 0.04em; color: rgba(238, 240, 250, 0.85); border: 1px solid rgba(238, 240, 250, 0.18); background: rgba(255, 255, 255, 0.04); border-radius: 999px; padding: 4px 12px; } /* ---------- KPI cards ---------- */ .nirf-kpis { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 14px; margin: 1.4rem 0 0.4rem; } .nirf-kpi { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 1.05rem 1.15rem 1rem; box-shadow: var(--shadow); position: relative; } .nirf-kpi::before { content: ""; position: absolute; left: 1.15rem; top: 0; width: 26px; height: 3px; border-radius: 0 0 3px 3px; background: var(--teal); } .nirf-kpi:first-child::before { background: var(--marigold); } .nirf-kpi.accent::before { background: var(--accent); } .nirf-kpi .label { font-size: 0.76rem; font-weight: 500; letter-spacing: 0.04em; text-transform: uppercase; color: var(--ink-3); margin-top: 0.3rem; } .nirf-kpi .value { font-family: var(--font-mono); font-size: 1.95rem; font-weight: 500; letter-spacing: -0.02em; color: var(--ink); margin: 0.25rem 0 0.1rem; font-variant-numeric: tabular-nums; } .nirf-kpi .foot { font-size: 0.78rem; color: var(--ink-3); } @media (max-width: 1440px), (max-height: 820px) { /* Projector / laptop (1366 x 768): tighter hero and page frame so more of the content fits on screen. */ [data-testid="stMainBlockContainer"] { padding-top: 1.8rem; } .nirf-hero { padding: 2.2rem 2.6rem 2rem; } .nirf-hero .title { font-size: 3.6rem; margin: 0.6rem 0 0.7rem; } .nirf-hero .purpose { font-size: 1.06rem; } .nirf-hero .meta { margin-top: 1.1rem; } .nirf-hero .orbit { width: 380px; height: 380px; } .nirf-kpi { padding: 0.85rem 1rem 0.8rem; } .nirf-kpi .value { font-size: 1.7rem; } .nirf-page-header .nirf-title { font-size: 2.2rem; } .nirf-section-title { margin: 2rem 0 0.8rem; } } @media (max-width: 1100px) { .nirf-kpis { grid-template-columns: repeat(3, minmax(0, 1fr)); } } @media (max-width: 640px) { .nirf-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); } .nirf-hero { padding: 2rem 1.4rem; } .nirf-hero .title { font-size: 3rem; } .nirf-hero .orbit { display: none; } } /* ---------- cards (bordered containers with a card-/navcard- key) ---------- */ [class*="st-key-card-"], [class*="st-key-navcard-"] { background: var(--surface); border: 1px solid var(--border) !important; border-radius: 16px !important; box-shadow: var(--shadow); } [class*="st-key-card-"] { padding: 0.5rem 0.6rem 0.4rem; } [class*="st-key-navcard-"] { padding: 1.1rem 1.2rem 0.9rem; transition: transform 140ms ease, box-shadow 140ms ease, border-color 140ms ease; height: 100%; } [class*="st-key-navcard-"]:hover { transform: translateY(-2px); box-shadow: var(--shadow-hover); border-color: var(--marigold) !important; } [class*="st-key-navcard-"] [data-testid="stPageLink"] a { padding: 0; background: transparent !important; } /* Not the icon span: the display font would break the Material icon ligature (the icon name showed as text). */ [class*="st-key-navcard-"] [data-testid="stPageLink"] a p, [class*="st-key-navcard-"] [data-testid="stPageLink"] a span:not([data-testid="stIconMaterial"]) { font-family: var(--font-display); font-size: 1.12rem; font-weight: 600; color: var(--ink); } [class*="st-key-navcard-"] [data-testid="stPageLink"] [data-testid="stIconMaterial"] { color: var(--teal) !important; font-size: 1.3rem; } .nirf-navdesc { font-size: 0.88rem; line-height: 1.5; color: var(--ink-2); margin-top: -0.2rem; min-height: calc(1.5em * 3); /* every card the same height, whether its text takes 2 or 3 lines */ } /* ---------- chart card parts ---------- */ .nirf-callout { background: var(--marigold-soft); border: 1px solid rgba(227, 154, 18, 0.28); border-left: 3px solid var(--marigold); border-radius: 10px; padding: 0.85rem 1.05rem 0.9rem; margin: 0.2rem 0 0.6rem; } .nirf-callout .label { font-family: var(--font-mono); font-size: 0.68rem; font-weight: 600; letter-spacing: 0.15em; text-transform: uppercase; color: var(--marigold-ink); } .nirf-callout .text { font-size: 0.99rem; line-height: 1.6; color: var(--ink); margin-top: 0.25rem; } .nirf-cardmeta { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 0.1rem 0 0.5rem; } .nirf-badge { font-family: var(--font-mono); font-size: 0.72rem; color: var(--teal-ink); background: var(--teal-soft); border-radius: 6px; padding: 2px 8px; } .nirf-why { font-size: 0.86rem; color: var(--ink-2); } [class*="st-key-card-"] [data-testid="stExpander"] details { border-color: var(--border-soft); border-radius: 10px; background: var(--surface-2); } [class*="st-key-card-"] [data-testid="stExpander"] summary p { font-weight: 500; font-size: 0.92rem; } /* ---------- empty state ---------- */ .nirf-empty { text-align: center; border: 1.5px dashed var(--border); border-radius: 16px; padding: 2.6rem 1.6rem; background: var(--surface-2); } .nirf-empty .icon { width: 46px; height: 46px; margin: 0 auto 0.8rem; border-radius: 50%; display: grid; place-items: center; background: var(--marigold-soft); color: var(--marigold-ink); font-family: var(--font-display); font-size: 1.4rem; font-weight: 600; } .nirf-empty .title { font-family: var(--font-display); font-size: 1.2rem; font-weight: 600; color: var(--ink); } .nirf-empty .msg { color: var(--ink-2); font-size: 0.94rem; line-height: 1.55; max-width: 560px; margin: 0.4rem auto 0; } .nirf-empty .hint { color: var(--ink-3); font-size: 0.84rem; margin-top: 0.7rem; } /* ---------- how-to steps ---------- */ .nirf-steps { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; } .nirf-step { border-top: 1px solid var(--border); padding-top: 1rem; } .nirf-step .num { font-family: var(--font-mono); font-size: 0.8rem; font-weight: 600; color: var(--marigold-ink); letter-spacing: 0.1em; } .nirf-step .head { font-family: var(--font-display); font-size: 1.18rem; font-weight: 600; color: var(--ink); margin: 0.3rem 0 0.3rem; } .nirf-step .body { font-size: 0.92rem; line-height: 1.55; color: var(--ink-2); } @media (max-width: 800px) { .nirf-steps { grid-template-columns: 1fr; } } /* ---------- data & method ---------- */ /* Pipeline diagram: boxes joined by arrows; wraps to two rows on narrow screens. */ .nirf-flow { display: flex; align-items: stretch; gap: 0; row-gap: 14px; } .nirf-flow-node { flex: 1 1 0; min-width: 0; background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 0.8rem 0.85rem 0.85rem; box-shadow: var(--shadow); display: flex; flex-direction: column; } .nirf-flow-node.src { background: var(--surface-2); border-style: dashed; box-shadow: none; } .nirf-flow-node.key { border: 1.5px solid var(--marigold); background: var(--marigold-soft); } .nirf-flow-node .tag { font-family: var(--font-mono); font-size: 0.64rem; letter-spacing: 0.1em; text-transform: uppercase; color: var(--teal-ink); font-weight: 600; } .nirf-flow-node.key .tag { color: var(--marigold-ink); } .nirf-flow-node .head { font-family: var(--font-display); font-weight: 600; font-size: 1.05rem; color: var(--ink); margin: 0.2rem 0 0.25rem; } .nirf-flow-node .body { font-size: 0.8rem; line-height: 1.45; color: var(--ink-2); flex: 1; } .nirf-flow-node code { font-size: 0.74rem; overflow-wrap: anywhere; } .nirf-flow-node .stat { font-family: var(--font-mono); font-size: 0.72rem; color: var(--ink); border-top: 1px solid var(--border-soft); margin-top: 0.55rem; padding-top: 0.45rem; } .nirf-flow-arrow { flex: 0 0 16px; align-self: center; height: 2px; background: var(--ink-3); position: relative; margin: 0 3px; } .nirf-flow-arrow::after { content: ""; position: absolute; right: -1px; top: -4px; border-left: 7px solid var(--ink-3); border-top: 5px solid transparent; border-bottom: 5px solid transparent; } @media (max-width: 1000px) { .nirf-flow { flex-wrap: wrap; } .nirf-flow-node { flex-basis: 40%; } .nirf-flow-arrow { display: none; } } .nirf-dict-wrap { max-height: 460px; overflow-y: auto; } .nirf-dict td { vertical-align: top; line-height: 1.45; } .nirf-dict td.col { font-family: var(--font-mono); font-size: 0.8rem; overflow-wrap: anywhere; color: var(--teal-ink); } .nirf-dict td.ex { font-family: var(--font-mono); font-size: 0.78rem; color: var(--ink-2); } .nirf-dict th { position: sticky; top: 0; z-index: 1; } .nirf-dict { table-layout: fixed; } .nirf-dict th:nth-child(1) { width: 21%; } .nirf-dict th:nth-child(2) { width: 48%; } .nirf-dict th:nth-child(3) { width: 9%; } .nirf-dict td.ex { overflow-wrap: anywhere; } .nirf-sources, .nirf-limits { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; } .nirf-limits { grid-template-columns: repeat(2, minmax(0, 1fr)); } .nirf-source, .nirf-limit { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 1rem 1.1rem; box-shadow: var(--shadow); } .nirf-limit { border-left: 3px solid var(--marigold); } .nirf-source .head, .nirf-limit .head { font-family: var(--font-display); font-weight: 600; font-size: 1.06rem; color: var(--ink); margin-bottom: 0.3rem; } .nirf-source .body, .nirf-limit .body { font-size: 0.88rem; line-height: 1.55; color: var(--ink-2); } .nirf-source .use { font-family: var(--font-mono); font-size: 0.7rem; color: var(--teal-ink); margin-top: 0.6rem; } .nirf-limit .num { font-family: var(--font-mono); font-size: 0.75rem; font-weight: 600; color: var(--marigold-ink); } @media (max-width: 900px) { .nirf-sources, .nirf-limits { grid-template-columns: 1fr; } } /* Cleaning steps: a table with a small bar of the row count after each step. */ .nirf-steptable-wrap { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; box-shadow: var(--shadow); overflow-x: auto; margin-top: 0.6rem; } .nirf-steptable { width: 100%; border-collapse: collapse; font-size: 0.86rem; color: var(--ink); } .nirf-steptable th { text-align: left; font-weight: 500; font-size: 0.74rem; letter-spacing: 0.04em; text-transform: uppercase; color: var(--ink-3); padding: 0.65rem 0.8rem; border-bottom: 1px solid var(--border); background: var(--surface-2); } .nirf-steptable td { padding: 0.42rem 0.8rem; border-bottom: 1px solid var(--border-soft); } .nirf-steptable tr:last-child td { border-bottom: none; } .nirf-steptable .num { text-align: right; font-family: var(--font-mono); font-variant-numeric: tabular-nums; } .nirf-steptable td.num:first-child { text-align: center; color: var(--ink-3); } .nirf-steptable .delta { font-family: var(--font-mono); font-size: 0.8rem; } .nirf-steptable .delta.up { color: var(--teal-ink); } .nirf-steptable .delta.down { color: var(--marigold-ink); font-weight: 600; } .nirf-steptable .delta.same { color: var(--ink-3); font-family: var(--font-body); } .nirf-steptable .barcell { width: 22%; min-width: 120px; } .nirf-steptable .bar { height: 8px; border-radius: 4px; background: var(--teal); opacity: 0.85; } /* ---------- widgets ---------- */ [data-testid="stMetricValue"] { font-family: var(--font-mono); } .stButton button[kind="primary"], [data-testid="stDownloadButton"] button[kind="primary"] { color: #141b3d; font-weight: 600; } [data-testid="stPlotlyChart"] { border-radius: 12px; overflow: hidden; } /* ---------- question bank ---------- */ .nirf-q-head { margin: 1.1rem 0 0.7rem; padding-left: 14px; border-left: 3px solid var(--marigold); } .nirf-q-top { display: flex; align-items: center; gap: 10px; } .nirf-q-id { font-family: var(--font-mono); font-size: 0.8rem; font-weight: 600; color: var(--navy); background: var(--marigold); border-radius: 6px; padding: 2px 8px; } .nirf-q-section { font-family: var(--font-mono); font-size: 0.7rem; letter-spacing: 0.12em; text-transform: uppercase; color: var(--ink-3); } .nirf-q-text { font-family: var(--font-display); font-weight: 600; font-size: 1.45rem; line-height: 1.3; color: var(--ink); margin: 0.35rem 0 0.3rem; } .nirf-q-why { font-size: 0.88rem; line-height: 1.5; color: var(--ink-2); max-width: 900px; } .nirf-q-why b { color: var(--teal-ink); font-weight: 600; } [class*="st-key-qb-pick-"] [role="radiogroup"] { gap: 4px; } [class*="st-key-qb-pick-"] [role="radiogroup"] label { width: 100%; padding: 6px 10px; border-radius: 8px; border: 1px solid var(--border-soft); background: var(--surface); } [class*="st-key-qb-pick-"] [role="radiogroup"] label:has(input:checked) { border-color: var(--marigold); background: var(--marigold-soft); } [class*="st-key-qb-controls-"] { background: var(--surface-2); } .nirf-runall-summary { margin: 0.6rem 0 0.4rem; padding: 10px 14px; border-radius: 10px; font-size: 0.95rem; color: var(--ink); } .nirf-runall-summary.ok { background: var(--teal-soft); border: 1px solid var(--teal); } .nirf-runall-summary.bad { background: var(--marigold-soft); border: 1px solid var(--marigold); } .nirf-grid-section { font-family: var(--font-mono); font-size: 0.72rem; letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink-3); margin: 1rem 0 0.1rem; } .nirf-tile-head { display: flex; align-items: center; gap: 8px; font-size: 0.95rem; color: var(--ink); } .nirf-tick { display: inline-grid; place-items: center; width: 20px; height: 20px; border-radius: 50%; font-size: 0.75rem; font-weight: 700; color: #fff; } .nirf-tick.ok { background: var(--teal); } .nirf-tick.bad { background: #c8433a; } .nirf-tile-time { margin-left: auto; font-family: var(--font-mono); font-size: 0.7rem; color: var(--ink-3); } .nirf-tile-text { font-size: 0.78rem; line-height: 1.35; color: var(--ink-2); height: calc(1.35em * 3); overflow: hidden; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; margin-top: 4px; } /* ---------- Ask NIRF chat ---------- */ .nirf-ask-steps { margin: 0.4rem 0 1.4rem; } .nirf-ask-title { font-family: var(--font-display); font-size: 1.12rem; font-weight: 600; color: var(--ink); margin: 0.1rem 0 0.4rem; } .nirf-ask-next { font-family: var(--font-mono); font-size: 0.68rem; font-weight: 600; letter-spacing: 0.15em; text-transform: uppercase; color: var(--ink-3); margin: 0.7rem 0 0.1rem; } .nirf-ask-note { border: 1px solid var(--border); border-left: 3px solid var(--indigo); border-radius: 10px; background: var(--surface-2); padding: 0.8rem 1.05rem 0.85rem; margin: 0.1rem 0 0.4rem; } .nirf-ask-note.bad { border-left-color: #c8443a; } .nirf-ask-note.warn { border-left-color: var(--marigold); } .nirf-ask-note .title { font-weight: 600; color: var(--ink); } .nirf-ask-note .msg { color: var(--ink-2); font-size: 0.94rem; line-height: 1.55; margin-top: 0.2rem; } .nirf-ask-note .fix { color: var(--ink-2); font-size: 0.9rem; line-height: 1.5; margin-top: 0.45rem; } .nirf-ask-notice { border: 1px solid var(--border); border-left: 3px solid var(--teal); border-radius: 10px; background: var(--teal-soft); padding: 0.65rem 1.05rem 0.7rem; margin: 0.1rem 0 0.55rem; } .nirf-ask-notice .title { font-family: var(--font-mono); font-size: 0.68rem; font-weight: 600; letter-spacing: 0.15em; text-transform: uppercase; color: var(--teal-ink); } .nirf-ask-notice .msg { color: var(--ink); font-size: 0.97rem; line-height: 1.5; margin-top: 0.15rem; } .nirf-ask-assumed { border: 1px solid var(--border); border-left: 3px solid var(--marigold); border-radius: 10px; background: var(--marigold-soft); padding: 0.6rem 1.05rem 0.65rem; margin: 0.5rem 0 0.3rem; } .nirf-ask-assumed .title { font-family: var(--font-mono); font-size: 0.68rem; font-weight: 600; letter-spacing: 0.15em; text-transform: uppercase; color: var(--marigold-ink); } .nirf-ask-assumed ul { margin: 0.25rem 0 0; padding-left: 1.1rem; } .nirf-ask-assumed li { color: var(--ink); font-size: 0.93rem; line-height: 1.5; margin: 0.1rem 0; } .nirf-ai-status { display: flex; align-items: center; gap: 8px; font-size: 0.8rem; line-height: 1.4; border-top: 1px solid rgba(232, 234, 246, 0.14); padding-top: 0.8rem; margin-top: 0.4rem; } .nirf-ai-status .dot { flex: none; width: 9px; height: 9px; border-radius: 50%; background: #e0574b; box-shadow: 0 0 0 3px rgba(224, 87, 75, 0.22); } .nirf-ai-status.ok .dot { background: #2fbf8f; box-shadow: 0 0 0 3px rgba(47, 191, 143, 0.22); }
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `bivariate.scatter_relation` → PASS
  - shown: Only 1 Overall institutions in 2018 have both RPC and Overall score; at least 3 are needed for a correlation. (Only institutions in Goa are included; clear the state filter to use all of India.)
  - how it understood the question: Category: Overall, because none was named; Parameter for research: RPC (Research and Professional Practice); Year: 2018, as specified; Filtered to institutions in Goa; Only institutions located in Goa are included (ranks stay national).

### X16. Has the link between Perception and the overall score in Engineering changed since 2017?
- **Section:** 4. Bivariate
- **UI path:** Relationships → *How one parameter's link to the overall score changed over the years*; Category = Engineering; Parameter = PR → PASS
  - shown: The PR-score correlation in Engineering stayed<br>about the same: r = 0.84 in 2017 → 0.84 in 2025
  - answer: In Engineering, the correlation between PR and the overall score went from r = 0.84 in 2017 to 0.84 in 2025 (±0.00); it was highest in 2020 (0.90) and lowest in 2023 (0.84).
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `bivariate.correlation_over_time` → PASS
  - shown: The PR-score correlation in Engineering stayed<br>about the same: r = 0.84 in 2017 → 0.84 in 2025
  - how it understood the question: Category: Engineering, as specified in the question; Parameter: pr (Perception), representing the link between Perception and overall score; Timeframe: since 2017 (covers all available years from 2017 to 2025).

### X17. Compare the parameter scores of IIT Indore and KIIT, which were tied at rank 27 in Overall 2025.
- **Section:** 5. Multivariate · **tricky case:** tied ranks
- **UI path:** Multi-Parameter → *Parameter profile of chosen institutions*; Year = 2025; Institutions = IIT Indore, Kalinga Institute of Industrial Technology → PASS
  - shown: Kalinga Institute of Industrial Tec… leads on 3 of 5<br>parameters; the biggest difference is in OI (14 points)
  - answer: Among these 2 institutions in Overall 2025, Kalinga Institute of Industrial Tec… has the highest score on TLR, GO, OI. They differ most on OI (64.2 to 77.7, a 13.5-point range) and least on TLR (3.1 points). All of them share rank 27 (a tie: NIRF gave them the same overall rank), so the parameters show how each one reaches that rank.
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `multivariate.parameter_profile` → PASS
  - shown: Kalinga Institute of Industrial Tec… leads on 3 of 5<br>parameters; the biggest difference is in OI (14 points)
  - how it understood the question: Category: Overall, as stated in the question; Year: 2025, as stated in the question; Institutions: IIT Indore and KIIT; I read 'IIT Indore' as Indian Institute of Technology Indore; I read 'KIIT' as Kalinga Institute of Industrial Technology.

### X18. Which Engineering institutions in 2024 have high Graduation Outcomes but low Research scores?
- **Section:** 5. Multivariate
- **UI path:** Multi-Parameter → *High on one parameter, low on another*; Category = Engineering; Year = 2024; High on = GO; Low on = RPC → PASS
  - shown: 18 Engineering institutions in 2024 score above the median on GO but below it on RPC
  - answer: In Engineering 2024, 18 of 100 institutions have GO above the median (66.9) but RPC below the median (39.9). The clearest case is Indian Institute of Information Technology Allahabad (rank 87: GO 80.6, RPC 24.9, z-gap 2.24), followed by Banasthali Vidyapith, Rajiv Gandhi Institute of Petroleum…, Netaji Subhas University of Technol….
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `multivariate.gap_finder` → PASS
  - shown: 18 Engineering institutions in 2024 score above the median on GO but below it on RPC
  - how it understood the question: Category: Engineering, as specified in the question; Year: 2024, as specified in the question; High parameter: Graduation Outcomes (go); Low parameter: Research and Professional Practice (rpc).

### X19. Which University institutions raised their overall score even though a parameter fell, with start year 2022 and end year 2018?
- **Section:** 5. Multivariate · **tricky case:** start year after end year
- **UI path:** Multi-Parameter → *Overall score rose although a parameter fell*; Category = University; From year → to year dragged to 2022 → 2018 → PASS
  - shown: 49 of 60 University institutions raised their<br>score 2018→2022 while at least one parameter fell
  - answer: Of the 72 University institutions scored in both 2018 and 2022, 60 improved their overall score, and 49 of those did so despite a fall in at least one parameter (most often TLR: 39 institutions). The largest such gain is Jamia Millia Islamia (+9.7 points, although TLR fell).
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `multivariate.improved_despite_decline` → PASS
  - shown: 49 of 60 University institutions raised their<br>score 2018→2022 while at least one parameter fell
  - how it understood the question: Category: University, as specified in the question; Start year: 2022, as specified; End year: 2018, as specified; You gave the later year first (2022 → 2018); a change is always measured from the earlier year to the later one, so 2018 → 2022 is shown.

### X20. Which Law institutions have the biggest gap between their strongest and weakest parameter in 2025?
- **Section:** 5. Multivariate
- **UI path:** Multi-Parameter → *Biggest gap between strongest and weakest parameter*; Category = Law; Year = 2025; How many institutions = 15 → PASS
  - shown: Galgotias University has the most lopsided profile in Law 2025: OI 75 vs PR 0
  - answer: In Law 2025, Galgotias University has the largest gap between its strongest and weakest parameter (OI 75.2 − PR 0.0 = 75.2 points). Across all 40 institutions the median gap is 52.1; the most common pattern is strongest TLR, weakest PR (10 institutions).
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `multivariate.strongest_weakest_gap` → PASS
  - shown: Galgotias University has the most lopsided profile in Law 2025: OI 75 vs PR 0
  - how it understood the question: Category: Law, as specified in the question; Year: 2025, as specified in the question.

### X21. How does the score distribution of the top 5 Dental colleges differ from the rest in 2024?
- **Section:** 6. Distribution
- **UI path:** Distributions → *Top N versus the rest*; Category = Dental; Year = 2024; Top N group = 5 → PASS
  - shown: The top 5's median score (74.4) is 21 points above the rest (53.8) in Dental 2024
  - answer: In Dental 2024, the top 5 have a median score of 74.4 (IQR 3.7) against 53.8 (IQR 6.3) for the other 35 scored institutions. Every top-5 score is above every other score (gap 2.1 points between the lowest top-5 score and the highest of the rest). The rest are more spread out (SD 5.3 vs 3.9). The rest are right-skewed: many institutions sit just above the cut-off and few higher up.
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `distribution.top10_vs_rest` → PASS
  - shown: The top 5's median score (74.4) is 21 points above the rest (53.8) in Dental 2024
  - how it understood the question: Category: Dental, as specified in the question; Year: 2024, as specified in the question; Top group: top 5 institutions, as specified in the question; View: violin plot for distribution comparison.

### X22. Among only the top 50, were Overall scores more spread out in 2017 than in 2025?
- **Section:** 6. Distribution
- **UI path:** Distributions → *Spread of scores in each year*; Only ranks 1 to … = 50 → PASS
  - shown: Overall scores were most dispersed in 2021 (SD 10.3) and least in 2025 (SD 8.0)
  - answer: Overall scores were most spread out in 2021 (SD 10.3, IQR 9.1) and least in 2025 (SD 8.0, IQR 9.5); in 2025 they were less dispersed than in 2017 (SD 8.8 → 8.0).
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `distribution.dispersion_by_year` → PASS
  - shown: Overall scores were most dispersed in 2021 (SD 10.3) and least in 2025 (SD 8.0)
  - how it understood the question: Category: Overall, as specified in the question; Top N: limited to the top 50 institutions; Metric: score dispersion measured via box plot (standard deviation and IQR).

### X23. How do Overall scores differ across states in 2025, including states with only one institution?
- **Section:** 6. Distribution · **tricky case:** state with one institution
- **UI path:** Distributions → *Scores by state*; States with at least … institutions = 1 → PASS
  - shown: Delhi has the highest median Overall score in<br>2025 (66.6) among states with 1+ institutions
  - answer: In Overall 2025, among the 22 states with at least 1 scored institutions, Delhi has the highest median score (66.6, n = 8) and Jammu and Kashmir the lowest (50.1); Uttar Pradesh is the most spread out (IQR 12.8).
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `distribution.score_by_state` → PASS
  - shown: Delhi has the highest median Overall score in<br>2025 (66.6) among states with 1+ institutions
  - how it understood the question: Category: Overall, as specified in the question; Year: 2025, as specified; Minimum institutions per state: set to 1 to include states with only a single ranked institution.

### X24. How many Engineering institutions climbed from outside the top 100 into the top 100 between 2020 and 2025?
- **Section:** 7. Mobility · **tricky case:** band-only ranks
- **UI path:** Mobility → *Moves between rank bands from one year to another*; Category = Engineering; From year → to year = 2020 → 2025 → PASS
  - shown: 5 Engineering institutions moved from the 51-100<br>band into the top 50 between 2020 and 2025
  - answer: Between 2020 and 2025, 5 Engineering institutions moved from the 51-100 band into the top 50: Chandigarh University, IIT Jodhpur, Kalasalingam Academy of Research an…, Koneru Lakshmaiah Education Foundat…, Lovely Professional University. Of the 213 institutions ranked in both years, 163 (77%) stayed in the same band, 19 moved to a better band and 31 to a worse one; 87 dropped out of the list and 87 were newly listed. 13 climbed from 101+ (where NIRF publishes mostly bands such as 101-150) into the top 100.
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `mobility.band_transitions` → PASS
  - shown: 5 Engineering institutions moved from the 51-100<br>band into the top 50 between 2020 and 2025
  - how it understood the question: Category: Engineering, as specified in the question; Years: 2020 to 2025, as specified in the question; Top 100 transition is captured via the band transitions matrix between the two years.

### X25. Which Overall institutions made the largest rank moves between 2025 and 2019?
- **Section:** 7. Mobility · **tricky case:** start year after end year
- **UI path:** Mobility → *Largest climbs and falls between two years*; From year → to year dragged to 2025 → 2019 → PASS
  - shown: Biggest Overall moves 2019→2025: Amity University +47<br>places · Savitribai Phule Pune University −74 places
  - answer: Between 2019 and 2025 in Overall, Amity University climbed the most (84 → 37, +47 places) and Savitribai Phule Pune University fell the most (17 → 91, −74 places).
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `mobility.biggest_rank_moves` → PASS
  - shown: Biggest Overall moves 2019→2025: Amity University +47<br>places · Savitribai Phule Pune University −74 places
  - how it understood the question: Category: Overall, as specified in the question; Year A: 2019, as specified; Year B: 2025, as specified; Top N: 10 largest upward and downward moves.

### X26. What share of Agriculture institutions stayed in the same rank band from one year to the next?
- **Section:** 7. Mobility · **tricky case:** category only from 2023
- **UI path:** Mobility → *Share that stayed in the same band each year*; Category = Agriculture & Allied Sectors → PASS
  - shown: On average 100% of Agriculture & Allied Sectors institutions<br>stay in the same band from one year to the next
  - answer: In Agriculture & Allied Sectors, on average 100% of the institutions ranked in two consecutive years stayed in the same band (1-10, 11-50, 51-100, 101+); in every pair of years (2023→2024, 2024→2025) it was 100%. Bands present: 1-10 (100% stay), 11-50 (100% stay).
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `mobility.band_retention` → PASS
  - shown: On average 100% of Agriculture & Allied Sectors institutions<br>stay in the same band from one year to the next
  - how it understood the question: Category: Agriculture & Allied Sectors, as specified in the question; by_band: True, to show the retention share for each rank band over time.

### X27. Which institutions entered or left the Overall top 100 from one year to the next?
- **Section:** 7. Mobility · **tricky case:** tied ranks at the cut-off
- **UI path:** Mobility → *Entries and exits of the top N, year to year*; Top N = 100 → PASS
  - shown: 169 different institutions were in the Overall<br>top 100 in 2017-2025; 53 were there every year
  - answer: Across 2017-2025, 169 different institutions were in the Overall top 100; there were 95 entries and 95 exits, in 8 of 8 year-to-year changes. 53 institutions were in the top 100 every year. In 2025: Indian Agricultural Research Instit…, IIT Bhubaneswar, International Institute of Informat…, Manipal University Jaipur, Mumbai University, Tamil Nadu Agricultural University, Post Graduate Institute of Medical…, Madan Mohan Malaviya University of…, National Institute of Mental Health…, AIIMS Bhubaneswar, Sher-e-Kashmir University of Agricu… entered; Acharya Nagarjuna University, Gujarat University, Mysore University, NIT Durgapur, Periyar University, Shoolini University of Biotechnolog…, Tata Institute of Social Sciences, Sri Ramachandra Institute of Higher…, AIIMS Jodhpur, Indian Statistical Institute, Kolka…, AIIMS Patna left.
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `mobility.top10_entries_exits` → PASS
  - shown: 169 different institutions were in the Overall<br>top 100 in 2017-2025; 53 were there every year
  - how it understood the question: Category: Overall, as specified in the prompt; Threshold: Top 100, as requested by the user; Method: Tracks consecutive years of published rankings to identify institutions entering or leaving the top 100 list.

### X28. Which Engineering institutions had unusually large year-to-year score changes, using |z| above 2.5?
- **Section:** 8. Outliers
- **UI path:** Outliers → *Unusually large year-to-year score changes*; Category = Engineering; Unusual if |z| is above = 2.5 → PASS
  - shown: 24 unusual year-to-year score changes in Engineering;<br>the largest: NIT Delhi +17.4 points (2022→2023)
  - answer: Out of 993 year-to-year score changes in Engineering (2017-2025), 24 are unusual (|z| > 2.5): 20 jumps up and 4 drops. The most extreme is National Institute of Technology Delhi in 2022→2023 (34.0 → 51.4, +17.4 points, z = +5.2). Institutions with unusual changes more than once: NIT Delhi (2×), UPES (2×), Chandigarh University (2×).
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `outliers.unusual_score_jumps` → PASS
  - shown: 24 unusual year-to-year score changes in Engineering;<br>the largest: NIT Delhi +17.4 points (2022→2023)
  - how it understood the question: Category: Engineering, explicitly requested; Z-score threshold: 2.5, explicitly requested.

### X29. Which Pharmacy institutions have unusually volatile ranks compared with their peers, counting only those ranked in at least 6 years?
- **Section:** 8. Outliers · **tricky case:** missing in some years
- **UI path:** Outliers → *Unusually volatile ranks compared with peers*; Category = Pharmacy; Ranked in at least … years = 6 → PASS
  - shown: 2 Pharmacy institutions move far more than their peers; most:<br>Bombay College of Pharmacy (rank SD 21.6 vs 6.4 typical)
  - answer: Of the 62 Pharmacy institutions with at least 6 exact ranks, 2 are unusually volatile for their peer band: Bombay College of Pharmacy (median rank 24, SD 21.6 vs peer median 6.4), JSS College of Pharmacy (Ootacamund) (median rank 7, SD 4.8 vs peer median 1.6). Typical volatility grows down the list: median rank SD 1-10 1.6, 11-25 6.4, 26-50 7.6, 51-100 13.6.
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `outliers.volatility_vs_peers` → PASS
  - shown: 2 Pharmacy institutions move far more than their peers; most:<br>Bombay College of Pharmacy (rank SD 21.6 vs 6.4 typical)
  - how it understood the question: Category: Pharmacy, as specified in the question; Minimum years required: 6 years, as specified in the question.

### X30. Which University institutions have a strong Perception score but a relatively poor rank in 2023?
- **Section:** 8. Outliers
- **UI path:** Outliers → *Strong parameter, relatively poor rank*; Category = University; Year = 2023; Parameter = PR → PASS
  - shown: 4 of the 26 University institutions with a<br>top-quartile PR in 2023 are ranked in the bottom half
  - answer: In University 2023, 26 institutions have PR at or above Q3 (40.9); 4 of them still rank below the median rank (50.5): Christ University (PR 51.3, rank 67), Graphic Era University (PR 47.4, rank 55), Guru Gobind Singh Indraprastha Univ… (PR 44.6, rank 74), UPES (PR 42.1, rank 52). Their other parameters hold them back.
- **Ask NIRF:** live model (gemini-flash-lite-latest, 2026-11-04) → `outliers.strong_param_poor_rank` → PASS
  - shown: 4 of the 26 University institutions with a<br>top-quartile PR in 2023 are ranked in the bottom half
  - how it understood the question: Category: University; Year: 2023; Parameter: Perception (pr).
<!-- results:end -->
