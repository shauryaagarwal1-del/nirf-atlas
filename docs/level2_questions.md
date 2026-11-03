# Level 2 rehearsal: 15 new examiner questions

Questions an examiner could ask that are NOT in Annexure A, each answered in the dashboard by turning knobs only
(no code). For each: the page, the view ("What do you want to see?") and the controls to set, then the answer
the dashboard gives. Controls not listed stay at their defaults (sidebar: Overall, 2017-2025, all states).
`tests/test_level2.py` sets exactly these controls in the real app and checks the chart it draws.

### E01. Which states have the most Engineering institutions in the top 50 in 2019?
- **Where:** Geography → tab *More views* → *States with the most institutions in the top list*
- **Controls:** Category = Engineering; Year = 2019; Top list (rank cut-off) = 50
- **Chart:** bar chart
- **Answer:** In 2019, Tamil Nadu has the most institutions in the Engineering top 50 (9); the top three states (Tamil Nadu 9, Uttar Pradesh 5, Maharashtra 4) hold 36% of the 50 places, spread over 19 states/UTs.

### E02. How have IIT Bombay's and IIT Delhi's Engineering ranks changed since 2017?
- **Where:** Trends → *Rank of chosen institutions, year by year*
- **Controls:** Category = Engineering; Institutions = IIT Bombay, IIT Delhi
- **Chart:** multi-series line chart
- **Answer:** Of these 2 institutions, IIT Delhi improved the most (rank 4 in 2017 → 2 in 2025, +2 places), while IIT Bombay fell the most (2 → 3, −1 place).

### E03. Which Pharmacy institutions climbed the most between 2020 and 2024?
- **Where:** Trends → *Biggest climbers between two years*
- **Controls:** Category = Pharmacy; From year → to year = 2020 → 2024; How many institutions = 10
- **Chart:** bar chart
- **Answer:** Between 2020 and 2024, Chitkara University climbed the most in Pharmacy: from rank 38 to 19 (+19 places). Of the 62 institutions with an exact rank in both years, 21 moved up, 39 moved down and 2 kept the same rank.

### E04. Among Kerala's institutions in the University ranking, which climbed the most from 2017 to 2025?
- **Where:** Trends → *Biggest climbers between two years*
- **Controls:** Category = University; Only states = Kerala
- **Chart:** bar chart
- **Answer:** Among institutions in Kerala: Between 2017 and 2025, Cochin University of Science and Technology climbed the most in University: from rank 86 to 32 (+54 places). Of the 3 institutions with an exact rank in both years, 3 moved up, 0 moved down and 0 kept the same rank.

### E05. How have IIM Ahmedabad's parameter scores changed over the years?
- **Where:** Trends → *Parameter scores of one institution, year by year*
- **Controls:** Category = Management; Institution = IIM Ahmedabad
- **Chart:** multi-series line chart
- **Answer:** From 2017 to 2025, IIM Ahmedabad's RPC went from 51.4 to 64.9 (+13.5), the largest gain among its parameters; OI fell the most, from 85.8 to 72.0 (−13.8). Its overall score went from 79.0 to 83.3 (+4.3).

### E06. Which parameter varies the most across Pharmacy institutions in 2023?
- **Where:** Distributions → *Which parameter varies the most*
- **Controls:** Category = Pharmacy; Year = 2023
- **Chart:** bar chart
- **Answer:** In Pharmacy 2023, RPC (Research & Professional Practice) is the most variable parameter (CV 0.71: SD 20.7 around a mean of 29.1) and TLR the least (CV 0.14: SD 9.1 around 67.2). Measured by SD alone, PR would come first (24.9), because it sits at a higher level.

### E07. In 2024, is Perception (PR) linked to the overall score more strongly in Engineering or in Management?
- **Where:** Relationships → *Any two numbers: scatterplot and correlation*
- **Controls:** X axis = PR; Y axis = Overall score; Year = 2024; Category = Engineering, then Management
- **Chart:** scatterplot
- **Answer:** In Engineering 2024, PR and Overall score have a very strong positive relationship (Pearson r = 0.84 · Spearman ρ = 0.70 · R² = 0.71 · p < 0.001 · n = 100); the straight line explains 71% of the variation in Overall score, and 10 more PR points go with +3.8 Overall score points on average.
- **Then Category = Management:** In Management 2024, PR and Overall score have a very strong positive relationship (Pearson r = 0.82 · Spearman ρ = 0.70 · R² = 0.68 · p < 0.001 · n = 100); the straight line explains 68% of the variation in Overall score, and 10 more PR points go with +3.6 Overall score points on average. So PR is linked slightly more strongly in Engineering (r = 0.84) than in Management (r = 0.82); both are very strong.

### E08. Among the Overall top 50 of 2025, how is Graduation Outcomes (GO) related to rank?
- **Where:** Relationships → *Any two numbers: scatterplot and correlation*
- **Controls:** X axis = GO; Y axis = Rank; Only ranks 1 to … = 50
- **Chart:** scatterplot
- **Answer:** In Overall top 50 2025, GO and Rank have a moderate negative relationship (Pearson r = -0.43 · Spearman ρ = -0.48 · R² = 0.18 · p = 0.002 · n = 50); the straight line explains 18% of the variation in Rank. A smaller rank is better, so a negative r means institutions with a higher GO tend to be ranked better.

### E09. How many Engineering institutions moved from the 51-100 band into the top 50 between 2018 and 2025?
- **Where:** Mobility → *Moves between rank bands from one year to another*
- **Controls:** Category = Engineering; From year → to year = 2018 → 2025
- **Chart:** matrix heatmap
- **Answer:** Between 2018 and 2025, 5 Engineering institutions moved from the 51-100 band into the top 50: IIT Jodhpur, Kalasalingam Academy of Research and Education, Kalinga Institute of Industrial Technology, Malaviya National Institute of Technology, NIT Silchar. Of the 159 institutions ranked in both years, 104 (65%) stayed in the same band, 16 moved to a better band and 39 to a worse one; 42 dropped out of the list and 141 were newly listed.

### E10. Which Law institutions entered or left the top 5 from one year to the next?
- **Where:** Mobility → *Entries and exits of the top N, year to year*
- **Controls:** Category = Law; Top N = 5
- **Chart:** time-series dot plot
- **Answer:** Across 2018-2025, 9 different institutions were in the Law top 5; there were 7 entries and 7 exits, in 7 of 7 year-to-year changes. 3 institutions were in the top 5 every year. In 2025: Gujarat National Law University entered; Symbiosis Law School, Pune left.

### E11. Which University institutions had unusually high research (RPC) for their overall score in 2021, using |z| > 1.5?
- **Where:** Outliers → *A parameter unusually high for the overall score*
- **Controls:** Category = University; Year = 2021; Parameter = RPC; Unusual if |z| is above = 1.5
- **Chart:** scatterplot
- **Answer:** In University 2021, 7 of 100 institutions have RPC more than 1.5 standard deviations above the line through all institutions: International Institute of Information Technolo… (RPC 30.3 vs 14.0 expected, z = 2.2), Vellore Institute of Technology (RPC 56.8 vs 41.0 expected, z = 2.2), Institute of Chemical Technology (RPC 55.8 vs 40.2 expected, z = 2.1), Birla Institute of Technology (RPC 26.7 vs 13.4 expected, z = 1.8) and 3 more.

### E12. Which Overall institutions in 2025 score high on Perception but relatively low on Graduation Outcomes?
- **Where:** Multi-Parameter → *High on one parameter, low on another*
- **Controls:** High on = PR; Low on = GO; Year = 2025
- **Chart:** scatterplot
- **Answer:** In Overall 2025, 20 of 100 institutions have PR above the median (18.5) but GO below the median (73.4). The clearest case is All India Institute of Medical Sciences, Delhi (rank 8: PR 75.4, GO 68.7, z-gap 3.06), followed by Anna University, Post Graduate Institute of Medical Education an…, International Institute of Information Technolo….

### E13. What share of the Overall top 100 in 2025 does each region hold?
- **Where:** Chart Builder
- **Controls:** Categories = Overall; From/To year = 2025; Rank cut-off = Top 100; Chart type = Pie chart; X axis = Region; Aggregation = Count
- **Chart:** pie chart
- **Answer:** South has the largest share: 35% of the institutions (Overall; 2025; ranks 1–100; 100 institutions, 100 rows).

### E14. How many institutions entered the Overall ranking for the first time in each year?
- **Where:** Chart Builder
- **Controls:** Quick start = New entrants per year (stacked bar: X Year, Colour New entrant, Count)
- **Chart:** stacked bar chart
- **Answer:** Most new entrants: 2018 (59); 2017 has the most institutions in total (200) (Overall; 2017-2025; 368 institutions, 1,800 rows).

### E15. How has the average TLR of Engineering institutions in the North and the South changed over time?
- **Where:** Chart Builder
- **Controls:** Categories = Engineering; Regions = North, South; Chart type = Line chart; X axis = Year; Y axis = TLR; Aggregation = Mean; Colour / group = Region
- **Chart:** multi-series line chart
- **Answer:** In 2025, South has the highest mean TLR (74.1) (Engineering; 2017-2025; North, South regions; 166 institutions, 781 rows).

## Gaps found while answering, and what we changed

| Gap | Fix |
|---|---|
| The sidebar's States filter changed only a few charts; "for Kerala only" was impossible for most analyses (E04). | Every Explore analysis now takes a state filter ("Only states"): it runs on the institutions of those states, and the subtitle, answer and method say so (`core/runner.py`, `core/data.py :: only_states()`). |
| Pages offered only some parameters of each analysis (e.g. no \|z\| threshold for score jumps, no chart variants, fixed top N). | Each view now has a control for every parameter of its engine function, checked by a test (`app/explorer.py`, `tests/test_explorer.py`). |
| No way to see one institution's five parameter scores over the years (E05). | New analysis `trends.parameter_trends()` (Trends → "Parameter scores of one institution, year by year"). |
| The two-variable scatter could not colour by category, could not be limited to the top 50 (E08), and with Rank on an axis its data table had two columns called "rank". | `scatter_relation()` pools several categories (with the cross-category note), takes "only ranks 1 to N", and names the published rank `published_rank`. |
| Changing the category reset the chosen X/Y, year and parameters (E07 needs the same X and Y in two categories). | Local choices are kept when the new category offers them, and reset only when it does not. |
| No chart for "new entrants per year" (E14) or "top 10 by RPC" as a bar list. | Chart Builder: a "New entrant" group and "Show groups: top N" for bar charts. |
| Mobility "entries and exits" stopped at the top 50. | Top N now goes up to 100. |
| With a state filter, "Today's top N" said "rank 1" for a state's best institution. | The answer now gives its real national rank, and the rank axis is deep enough to show every line. |

Known limit (for Phase 12): nicknames such as "NIT Trichy" are not yet matched to "NIT Tiruchirappalli" in the
institution search; official names and short forms (IIT, NIT, IIM ...) work.
