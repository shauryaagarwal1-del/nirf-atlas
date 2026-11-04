# 03 · Analysis methods: the statistics behind every answer

**In one sentence:** eight engines answer eight kinds of question with simple, explainable statistics (counts,
shares, mean, median, quartiles, IQR, standard deviation, coefficient of variation, correlation, regression lines,
z-scores and the 1.5 × IQR rule), and every answer comes with the method written in plain words.

Deeper reference: `docs/methods.md` has one entry per question (definition, calculation, chart, filters). This file
teaches the ideas behind them.

---

## 1. What the engines do and why

Every engine function takes simple settings (years, category, states, institutions, parameters, top N) and returns
the same five things, which we call a **ChartResult**:

| Part | What it is | Why |
|---|---|---|
| chart | The Plotly figure | The picture that answers the question |
| table | The exact numbers behind the chart | Anyone can check the chart; downloadable as CSV |
| insight | One plain-English sentence with the answer | The examiner gets the answer, not just a picture |
| method | How it was calculated, in plain words | Every number is explainable |
| chart type | The chart's name from our allowed list | Tests make sure we only use taught charts |

| Engine | Kind of question | Annexure A questions | Main methods |
|---|---|---|---|
| **trends** | Change over time | Q1.1–Q1.5 | rank by year, improvement, mean/median per year, years in the top N |
| **geography** | Where (states, regions) | Q2.1–Q2.5 | counts and shares per state, change in counts, median rank per state, new entrants |
| **univariate** | One variable's shape | Q3.1–Q3.5 | histogram + KDE, mean/median/min/max, SD, quartiles, IQR, skewness |
| **bivariate** | Two variables together | Q4.1–Q4.5 | Pearson r, Spearman ρ, R², p-value, least-squares line |
| **multivariate** | All five parameters at once | Q5.1–Q5.5 | parameter profiles, median quadrants, z-score gaps, changes, max − min gap, PCA |
| **distribution** | Comparing spreads | Q6.1–Q6.5 | group statistics, SD, IQR, coefficient of variation, box/violin |
| **mobility** | Movement between ranks | Q7.1–Q7.5 | rank bands, transition matrix, retention %, up/down/same counts |
| **outliers** | What breaks the pattern | Q8.1–Q8.5 | regression residuals, z-scores, Q3/median cut-offs, 1.5 × IQR rule, rank volatility |

All charts are drawn **within one category** (and usually one year), because each category has its own weights.

---

## 2. The definitions we chose (the examiner will probe these)

| Term | Our definition | Why this one |
|---|---|---|
| **Rank** | Smaller = better. Rank axes are flipped so up = better. | Matches how everybody reads a ranking |
| **Improvement** | old rank − new rank (positive = moved up) | One sign convention everywhere: 20 → 5 is +15 |
| **In the top N** | Rank is *certainly* ≤ N: exact rank ≤ N, or NIRF band whose worst rank ≤ N | Uses band rows without inventing exact ranks |
| **Exact ranks only** | When ranks are subtracted, averaged or put in a box plot | A band like 101–150 cannot be subtracted |
| **Consistently in the top 10** (Q1.5) | In the top 10 in at least *k* of the years (default 5) | "Consistent" needs a number; the user can change *k* |
| **State share** (Q2.2) | State's top-N institutions ÷ all top-N institutions × 100 | Shares add to 100% each year, so years compare fairly |
| **New entrant** (Q2.5) | First appearance in that category's ranked list, in a year when the category already existed | Nobody can be "new" in 2017 or in a list's launch year |
| **Quartile groups** (Q3.4) | Two views: fixed quarters of the 0–100 scale, or the data's own Q1/median/Q3 | Statistical quartiles hold 25% each *by definition*, so the fixed-scale view is the informative one |
| **Strength of r** | \|r\| < 0.2 very weak, < 0.4 weak, < 0.6 moderate, < 0.8 strong, else very strong | One fixed scale for every sentence |
| **High on A, relatively low on B** (Q5.2/5.3) | A above A's median **and** B below B's median, sorted by z(A) − z(B) | Medians are not pulled by extreme values; z-scores put A and B on one scale |
| **Strongest − weakest gap** (Q5.5) | Highest − lowest of an institution's five parameter scores | Direct, all on the same 0–100 scale |
| **Most variable parameter** (Q6.3) | Coefficient of variation = SD ÷ mean | Parameters sit at very different levels (PR ≈ 24, GO ≈ 75), so plain SD is unfair |
| **Mobility bands** (Q7) | 1-10, 11-50, 51-100, 101+, Not ranked | Every NIRF band fits wholly inside one of these, so band rows can be followed |
| **Retention** (Q7.3) | Same band in both years ÷ ranked in both years × 100 | Joiners and leavers counted separately |
| **Unusually high research for its score** (Q8.1) | Residual from the least-squares line, residual z > 2 | "Relative to the overall score" = distance from the line |
| **Unusual score change** (Q8.3) | z of the change within its year pair, \|z\| > 2 | When NIRF's method shifts everyone (+4 on average in 2017→18), not everyone looks unusual |
| **Strong parameter, poor rank** (Q8.4) | Parameter ≥ Q3 (top quarter) and exact rank worse than the median rank | Simple, explainable cut-offs |
| **Volatility** (Q8.5) | SD of an institution's exact ranks over ≥ 4 years; unusual = above Q3 + 1.5 × IQR of its peer band | Ranks naturally move more lower down (median SD 0.8 in the top 10 vs 11.7 in 51–100), so compare with peers |

---

## 3. The concepts, explained simply (with tiny examples)

Take five scores: **50, 52, 55, 60, 83**.

### Centre
- **Mean** = sum ÷ count = 300 ÷ 5 = **60**. Pulled up by the 83.
- **Median** = middle value when sorted = **55**. Not affected by the 83. When the mean is above the median, a few
  high values are pulling it: the data is **right-skewed**. NIRF scores are right-skewed (Overall 2025: mean 57.8,
  median 55.4): many institutions just above the cut-off, a few stars far above.

### Spread
- **Min / max / range**: 50, 83, range 33. Depends on just two values.
- **Quartiles**: Q1 cuts off the lowest 25%, Q2 is the median, Q3 cuts off the highest 25%.
- **IQR** = Q3 − Q1 = the width of the middle 50%. Robust: extreme values don't change it.
- **Standard deviation (SD)**: the typical distance of a value from the mean. Big SD = spread out. (We use the
  sample SD, dividing by n − 1.)
- **Coefficient of variation (CV)** = SD ÷ mean. Spread *relative to the average*. Example: PR has SD 21.3 around a
  mean of 24.2 (CV 0.88); TLR has SD 7.4 around 69.2 (CV 0.11). PR varies far more relative to its level.
- **Skewness**: a number for lopsidedness; positive = long tail to the right.

### Standing out
- **z-score** = (value − mean) ÷ SD: how many SDs away from the average. z = +2 means "two SDs above average".
  If values are roughly bell-shaped, only about 5% have |z| > 2, so we call those "unusual".
- **1.5 × IQR rule**: a value below Q1 − 1.5·IQR or above Q3 + 1.5·IQR is an outlier. This is exactly what the
  whiskers of a box plot show; dots beyond them are outliers.

### Relationships
- **Pearson r** (−1 to +1): how well the points follow a *straight line*. +1 perfect rising line, 0 no straight-line
  relation, −1 perfect falling line. Sensitive to outliers.
- **Spearman ρ (rho)**: Pearson r computed on the *ranks* of the values. Captures any steadily rising or falling
  relation, even curved, and is robust to outliers. Natural for rank data. If ρ and r differ by 0.15 or more, our
  insight says the pattern is not a straight line or a few points dominate.
- **Least-squares line (regression / trend line)**: the straight line y = a + b·x that makes the sum of squared
  vertical distances from the points as small as possible. The slope b says how much y changes per unit of x.
- **R²**: the share of the variation in y explained by the line (0 to 1). With one x, R² = r². Example: RPC vs
  overall score in Overall 2025 has r = 0.89, so R² = 0.79: the line explains 79% of the differences in score.
- **Residual** = actual − predicted (by the line). A large positive residual = "much higher than expected".
- **p-value**: the chance of seeing a correlation this strong if there were really none. p < 0.05 = "statistically
  significant" (unlikely to be chance). It is not the strength: a tiny r can be significant with many points.
- **Correlation is not causation.** And because the overall score *is* a weighted sum of the parameters, part of
  every parameter-vs-score correlation is built in; our charts say so.

### Many variables at once
- **PCA (principal component analysis)**: turns the five parameters into z-scores, then finds new axes. PC1 is the
  direction along which institutions differ most; PC2 the next, at right angles. Each institution gets a PC1 and PC2
  value (a weighted sum of its z-scores; the weights are called loadings). In Overall 2025, PC1 keeps 44% of the
  variation and correlates r = 0.99 with the overall score (a general "strength" axis); PC2 (22%) contrasts OI
  against RPC. Used as an extra view only; every Annexure question uses simpler methods.

### Shapes
- **KDE (kernel density estimate)**: put a small bell curve on every value and add them up; the result is a smooth
  outline of the histogram. Its width (bandwidth) is chosen automatically by Scott's rule.

---

## 4. Methods per engine (one paragraph each)

- **Trends:** look up each institution's rank per year and join exact ranks with a line (band years drawn as a faint
  range, never a point, and listed in the answer). For band-only colleges, `band_history` draws each year's band as
  an error bar from its best to its worst rank (nothing averaged, nothing joined). With two institutions the answer
  says who is ahead in the latest year and how the gap changed. Biggest movers: improvement between two years among institutions with an exact rank in both.
  Average score over time: mean or median per category-year, optionally with Q1–Q3; `top_n = 100` keeps lists of
  different lengths comparable. Consistency: count years in the top N.
- **Geography:** count institutions certainly in the top N per state; share = count ÷ all × 100; change = end count −
  start count. State comparisons use the median exact rank (and report how many institutions each state has, because
  a state with many institutions also has more of them lower down). New entrants counted per state and year.
- **Univariate:** histogram with 2.5-point bins + KDE + mean/median lines; summary table (n, mean, median, min, max,
  range, SD, Q1, Q3, IQR, CV); rank bands split into exact vs band-only; quartile shares; spread per category.
- **Bivariate:** Pearson, Spearman, R², p-value and the least-squares line for any two numbers; correlogram of all
  parameters with the overall score; r per year for Q4.5 (called "strengthened/weakened" only for a change > 0.05).
- **Multivariate:** five parameter scores side by side; median quadrants with z-score gaps; change in each parameter
  vs change in overall score (improved overall although a parameter fell, possible because the score is a weighted
  sum); strongest − weakest gap; PCA.
- **Distribution:** compare groups (top 10 vs rest, years, parameters, states) by median, IQR, SD and CV; years with
  different list lengths flagged.
- **Mobility:** give every institution a mobility band in both years and count each (band A, band B) pair: a
  transition matrix. Retention = stayed ÷ ranked in both. Up/down/same from exact ranks in consecutive years.
- **Outliers:** residual z-scores from a regression line (Q8.1); RPC − TLR (Q8.2); z of year-to-year changes within
  each year pair (Q8.3); Q3 and median cut-offs (Q8.4); 1.5 × IQR rule on rank SD within peer bands (Q8.5).

**Extra power for Level 2:** every analysis can be limited to chosen states ("only Kerala"). Ranks stay the national
NIRF ranks, while counts, averages, quartiles, z-scores and correlations are calculated within those states, and the
chart's subtitle, answer and method say so.

---

## 5. Key decisions (and why)

| Decision | Why |
|---|---|
| Prefer **median and IQR** over mean and SD when describing a "typical" value or comparing groups | Scores are right-skewed and have stars; medians and IQRs are not pulled by them |
| Report **both Pearson and Spearman** | Pearson for straight lines (what the trend line shows), Spearman for rank-like, possibly curved relations |
| Use **CV, not SD**, for "which parameter varies most" | Fair across parameters at different levels; we also say when SD would give a different answer |
| **z > 2** for "unusual" and **1.5 × IQR** for box-plot outliers | Standard, explainable thresholds; the user can change the z cut-off |
| Compute z-scores **within a year pair** for score jumps | Removes NIRF method changes that moved every institution |
| Compare volatility **with peers** (same median-rank band) | Lower positions move more by nature; a fair comparison is with similar institutions |
| **Exact ranks only** for arithmetic on ranks; report how many rows were left out | Never invent ranks from bands |
| `top_n = 100` option for time comparisons | List lengths changed (Engineering ranked 200 exactly in 2019–2022, 100 otherwise) |
| **No complex machine learning** | Every method must be explainable in one sentence; PCA is the only advanced method and is an extra view |

---

## 6. Likely viva questions with model answers

**Q1. Why do you use the median instead of the mean in many places?**
NIRF scores are right-skewed: most institutions sit just above the cut-off and a few top institutions score far
higher. The mean is pulled towards those few (Overall 2025: mean 57.8, median 55.4); the median is the middle value
and is not moved by extremes, so it describes a typical institution better. We still show the mean where the
question asks for it (Q1.4, Q3.3).

**Q2. What is the difference between Pearson and Spearman correlation, and which do you use?**
Pearson r measures how well points follow a straight line and is sensitive to outliers. Spearman ρ is Pearson
computed on ranks, so it measures any steadily increasing or decreasing relationship and is robust to outliers. We
report both. Pearson matches the straight trend line we draw; Spearman suits rank data. If they differ by 0.15 or
more, our insight says the pattern is curved or a few points dominate.

**Q3. Which parameter is most strongly associated with the overall score, and does that mean it causes it?**
In Overall 2025, RPC (research) has the strongest correlation, r = 0.89, followed by PR (0.85); OI is weakest
(0.12). But correlation is not causation, and part of it is built in: the overall score is a weighted sum of the
parameters (RPC carries 30%), so a parameter with a big weight on which institutions differ a lot will correlate
strongly.

**Q4. How do you define an outlier?**
Two standard rules. For values compared with an expectation, a z-score above 2 (more than two standard deviations
from the average, or from the regression line for Q8.1); with bell-shaped data only about 5% go beyond ±2. For
groups, the box-plot rule: below Q1 − 1.5 × IQR or above Q3 + 1.5 × IQR. The z cut-off can be changed in the
dashboard.

**Q5. Why use the coefficient of variation to find the most variable parameter?**
Because parameters sit at very different levels: in Overall 2025 PR averages about 24 and GO about 75. The standard
deviation alone favours parameters with bigger numbers. CV = SD ÷ mean measures spread relative to the parameter's
own average, so the comparison is fair. PR is the most variable (CV 0.88), TLR the least (0.11).

**Q6. How do you measure "improvement" when some years have only rank bands?**
Improvement = old rank − new rank, so positive means moved up. It needs exact ranks in both years, because a band
like 101–150 cannot be subtracted. Institutions without an exact rank in either year are left out, and the method
text says how many. For band-based questions (Q7.1, Q7.3) we use mobility bands, which band rows can be placed in
with certainty.

**Q7. What does R² tell you, and what does the p-value tell you?**
R² is the share of the variation in y that the straight line explains, from 0 to 1; with one predictor it equals r².
RPC explains 79% of the variation in overall score in Overall 2025. The p-value is the chance of seeing a
correlation this strong if there were truly none; below 0.05 we call it statistically significant. R² is about
strength, p is about whether the pattern could be chance.

**Q8. How did you decide which institutions are unusually volatile?**
Volatility is the standard deviation of an institution's exact ranks over at least four years. Ranks naturally move
more lower down the list (median SD 0.8 in the top 10 vs 11.7 in 51–100), so we compare each institution with peers
whose median rank is in the same band, and call it unusual if its SD is above Q3 + 1.5 × IQR of its peers. That is
the box-plot outlier rule, and the box plot shows it directly. In Overall, IIM Calcutta and Savitribai Phule Pune
University are examples.
