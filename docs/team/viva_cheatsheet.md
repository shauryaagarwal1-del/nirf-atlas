# Viva cheat sheet

Revise this the night before and again in the corridor. Detail is in files `00` to `06` of this folder.

**Our five rules:** smaller rank = better (rank axes flipped, up = better) · improvement = old rank − new rank
(+ = moved up) · scores are compared only within one category · we never invent data (no mid-points for bands,
no filled-in scores) · every chart states its answer in the title and carries "Source: NIRF, Ministry of
Education, Govt. of India".

---

## 1. Definitions

Example data for the numbers below: scores **50, 52, 55, 60, 83**.

| Term | Plain-words definition |
|---|---|
| **Mean** | Sum ÷ count (300 ÷ 5 = 60). Pulled towards extreme values. |
| **Median** | The middle value when sorted (55). Not moved by extremes; better for skewed data like NIRF scores. |
| **Quartiles (Q1, Q2, Q3)** | The values that cut the sorted data into four equal-sized groups of 25%. Q2 = median. |
| **IQR** | Q3 − Q1: the width of the middle 50%. A robust measure of spread (extremes don't affect it). |
| **Standard deviation (SD)** | The typical distance of values from the mean. Bigger = more spread. (Sample SD, divide by n − 1.) |
| **Coefficient of variation (CV)** | SD ÷ mean: spread relative to the average, so variables at different levels compare fairly (PR: SD 21.3 / mean 24.2 = 0.88; TLR: 7.4 / 69.2 = 0.11). |
| **Pearson r vs Spearman ρ** | Pearson r (−1 to +1): how well points follow a **straight line**; sensitive to outliers. Spearman ρ: Pearson on the **ranks**; any steadily rising/falling relation, robust to outliers, natural for rank data. We report both. |
| **R squared (R²)** | Share of the variation in y explained by the regression line, 0 to 1. With one x, R² = r² (RPC vs score: r 0.89 → R² 0.79). |
| **z-score** | (value − mean) ÷ SD: how many SDs from average. \|z\| > 2 = "unusual" (about 5% of bell-shaped data). |
| **Outlier** | A value far from the rest. Our rules: \|z\| > 2, or beyond Q1 − 1.5·IQR / Q3 + 1.5·IQR (box-plot whiskers). |
| **Choropleth map** | A map whose regions are coloured by a value (states by number of top-100 institutions). |
| **Correlogram** | A heatmap of the correlation r between every pair of variables, r printed in each cell, mirror image across the diagonal (diagonal = 1). |
| **Transition matrix** | Rows = group in year A, columns = group in year B, cell = how many moved from row to column. Diagonal = stayed. Read like a confusion matrix. |
| **Lollipop chart** | A bar chart drawn as a thin stem with a dot at the end: less ink for long sorted lists. |
| **Violin plot** | A box plot plus the distribution's shape: a smoothed density curve mirrored on both sides (wide = many values there). |
| **ECDF** | Empirical cumulative distribution function: for each value x, the share of data ≤ x. A rising step curve from 0 to 1; read the median where it crosses 0.5. (On the allowed list; not used in our dashboard.) |
| **PCA** | Principal component analysis: turns the 5 parameters (as z-scores) into new axes. PC1 = direction of greatest difference between institutions, PC2 = next, at right angles. Overall 2025: PC1 keeps 44% of the variation, r = 0.99 with the overall score. |
| Also know | **p-value**: chance of a correlation this strong if there were none; < 0.05 = significant. **Residual**: actual − predicted by the line. **Skewness**: lopsidedness; right-skewed = long tail of high values, mean > median. **KDE**: a smooth curve made by adding a small bell curve on every value. **Volatility**: SD of an institution's ranks over the years. |

---

## 2. How to read every chart type we use

| Chart | How to read it | Where we use it |
|---|---|---|
| **Line chart** | x = year, y = value; slope = change. On rank charts rank 1 is at the top, so up = better. | Q1.1, Q7.3, SD per year |
| **Multi-series line chart** | One line per group on shared axes; compare slopes and crossings. | Q1.4, Q2.2, Q4.5, top-N race |
| **Vertically aligned time-series charts** | Stacked panels sharing one year axis; read the same year straight down. | State vs State (count + median rank) |
| **Time-series dot plot** | One row per item, a dot per year it qualifies; gaps = not qualifying. Triangle = entered, cross = left. | Q7.2 |
| **Point plot with error bars** | Point = median (or mean), bar = Q1 to Q3; longer bar = more spread. | Q6.4, Q1.4 spread view |
| **Bar chart** (sorted, horizontal) | Bar length = amount; sorted top to bottom = a ranking. Bars left of zero = negative (coral = down/lost, teal = up/gained). | Q1.2, Q1.3, Q2.1, Q2.3, Q6.3, Q8.2 |
| **Grouped bar chart** | Groups on x, one bar per series inside each group; compare bars within a group. | Q5.1 (parameters × institutions) |
| **Stacked bar chart** | Bar = total, segments = parts; a 100% bar shows shares. Compare the bottom segment easily, middle ones less so. | Q2.5, Q3.2, Q3.4, Q7.5 |
| **Small-multiple bar charts** | The same small chart per item on a shared axis; compare panels. | Q5.4 |
| **Lollipop chart** | Like a sorted bar chart: stem length = value, dot = end. | Q5.5, Q7.4 |
| **Pie chart** | Slice angle = share of the whole; only for parts of a whole (counts). | Chart Builder |
| **Histogram** | x = value intervals (bins), bar height = how many fall in each. Shows the shape. | Chart Builder |
| **Overlapping histogram** | Two half-transparent histograms on the same bins; compare where groups sit. | Q6.1 alternative |
| **Histogram with density curve** | Histogram + smooth KDE outline; dashed lines = mean and median (mean right of median = right-skewed). | Q3.1 |
| **Box-and-whisker plot** | Line = median; box = Q1 to Q3 (height = IQR); whiskers to the furthest point within 1.5 × IQR; dots beyond = outliers. Our dots show every institution. | Q2.4, Q3.3, Q3.5, Q6.2, Q6.5, Q8.5 |
| **Violin plot** | Width = how many at that value; inner box = median and IQR. | Q6.1 |
| **Jittered strip chart** | Every value a dot, shifted sideways at random so dots don't hide each other; highlighted dots = \|z\| > 2. | Q8.3 |
| **Scatterplot** | One dot per institution, x vs y. Rising cloud = positive relation; tight = strong. Line = least squares; dots far from it = residual outliers. Dashed median lines split it into quadrants (Q5.2/5.3). | Q4.1, Q4.2, Q4.4, Q5.2, Q5.3, Q8.1, Q8.4 |
| **Bubble chart** | A scatterplot whose bubble area shows a third number. | Chart Builder |
| **PCA scatterplot** | Each dot = an institution placed by PC1 and PC2; close dots have similar parameter profiles. Colour = rank band. | Multi-Parameter (extra) |
| **Matrix heatmap** | Grid of cells coloured by value (darker = more), value printed in the cell. Q7.1 is the transition matrix. | Q1.5, Q5.1 alternative, Q7.1, coverage |
| **Correlogram** | Heatmap of r: teal = positive, coral = negative, darker = stronger; read the "Overall score" row for Q4.3. | Q4.3 |
| **Choropleth map** | State colour = count (light → dark teal, grey = none); the scale is fixed across years; slider/▶ steps through years. | Geography map |

---

## 3. The NIRF parameters and their weights

| Code | Name | What it measures (simply) |
|---|---|---|
| **TLR** | Teaching, Learning & Resources | Student strength, faculty-student ratio, faculty with PhDs, money spent |
| **RPC** | Research & Professional Practice | Publications, citations, patents, research projects |
| **GO** | Graduation Outcomes | Students graduating on time, placements, higher studies, median salary |
| **OI** | Outreach & Inclusivity | Students from other states, women, economically disadvantaged students, facilities for the differently abled |
| **PR** | Perception | Opinion of academic peers and employers |

Each is scored out of 100; **overall score = weighted sum**. We **verified the weights from our own data**: a
least-squares fit of score on the five parameters for every category-year reproduces every published score to
within 0.02 (checked on every scored row by `tests/test_data.py`).

| Category | TLR | RPC | GO | OI | PR |
|---|---|---|---|---|---|
| Overall, University, Engineering, Management, Pharmacy, Medical, Dental, Agriculture, State Public University | 30% | 30% | 20% | 10% | 10% |
| College (2018–2025) | 40% | 15% | 25% | 10% | 10% |
| College (2017) | 30% | 20% | 25% | 15% | 10% |
| Law | 40% | 15% | 25% | 10% | 10% |
| Architecture & Planning (2019–2025) | 40% | 20% | 20% | 10% | 10% |
| Architecture (2018) | 30% | 30% | 20% | 10% | 10% |
| Research Institutions | QnR 30% | QlR 30% | SFC 20% | 10% | 10% |

Research Institutions use QnR (Quantitative Research), QlR (Qualitative Research) and SFC (Student, Faculty &
Collaboration) instead of TLR, RPC, GO. Innovation, SDG Institutions, Open University and Skill University publish
ranks only, no parameter scores.

---

## 4. Key design decisions and the reason for each

| Decision | Reason |
|---|---|
| One master table, one row per (year, category, institution) | A single source of truth: every page and the chat read the same numbers |
| Keep raw text when scraping; clean in a separate, documented step | Nothing lost or guessed; every rule can be explained and checked |
| Keep `category_original` beside the standard category | Honest history across renames ("Research" → "Research Institutions") |
| Hand-checked mapping tables for states, categories, aliases | A person checked them; a new spelling stops the pipeline instead of being guessed |
| Uncertain institution matches go to human review; one list's rows never merged | Wrong merges would corrupt trends; better unmatched than wrongly matched |
| No imputation; band-only rows get no exact rank | A made-up number would look like real NIRF data |
| "Top N" = certainly in the top N (exact rank or band end ≤ N) | Uses band rows without inventing ranks |
| Exact ranks only for rank arithmetic, with the count left out stated | Bands cannot be subtracted or averaged |
| Medians and IQR for typical values and group comparisons | Scores are right-skewed; medians resist the few stars |
| Pearson and Spearman both reported | Straight-line strength + rank-based robustness |
| CV for "most variable parameter" | Parameters sit at different levels (PR ≈ 24, GO ≈ 75) |
| \|z\| > 2 and 1.5 × IQR for "unusual" | Standard, explainable thresholds; z cut-off adjustable |
| Score-jump z within each year pair; volatility vs peer band | Removes method-change years; lower ranks move more by nature |
| Only chart types from the course list (test-enforced) | We can explain each; radar → grouped bar, Sankey → transition matrix, stacked area → multi-series line |
| Title states the answer; axis + legend titles; full names on hover; source note | Readable on a projector without explanation |
| Colour-blind-safe palette, teal = up, coral = down, shapes for highlights | Readable by everyone, never colour alone |
| Same 8 engines behind Question Bank, Explore pages, Chart Builder and chat | Pages can never disagree |
| Chat: the model writes a JSON plan, our code computes every number | No hallucinated numbers; safe (nothing the model writes is run as code) |
| Chat fallbacks: next model, spare key, offline closest-question match | The live demo cannot depend on one quota or the internet |
| Automated tests: data checks, all 40 questions, the real app headless, 15 Level 2 and 25 chat questions | Confidence that it works live |

---

## 5. Numbers to quote

9 years (2017–2025) · 17 categories (6 in 2017 → 17 in 2025) · 290 pages · 75,626 raw rows · **11,647 ranked rows**
(6,974 exact, 4,671 band-only) · **1,693 institutions** from 2,288 spellings · **34 states/UTs** from 49 spellings ·
spot check of all rows: **0 real differences** · 8 engines · 40/40 questions.

Headline answers (Overall, defaults): IIT Madras rank 1 since 2019 (Q1.1) · biggest climber 2017→2025 Saveetha,
91 → 23 (Q1.2) · 8 institutions in the top 10 every year (Q1.5) · Tamil Nadu most top-100 institutions in 2025, 17
(Q2.1) · scores right-skewed, mean 57.8 > median 55.4 (Q3.1) · RPC most correlated with score, r = 0.89 (Q4.3) ·
PR most variable, CV 0.88 (Q6.3) · 9 institutions moved 51–100 → top 50, 2017→2025 (Q7.1) · 86% stay in their band
year to year (Q7.3).
