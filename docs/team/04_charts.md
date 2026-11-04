# 04 · Charts: which picture for which question, and why

**In one sentence:** every chart is a type taught in the course (`docs/allowed_charts.md`), chosen because it
fits the *shape of the question* (over time → line, compare amounts → bar, one distribution → histogram/box,
two numbers → scatter, where → map, movement between groups → matrix), and every chart states its answer in the
title.

How to *read* each chart type is in `viva_cheatsheet.md`. The full per-question reasoning is in `docs/methods.md`.

---

## 1. The rule of thumb: question shape → chart

| If the question is about... | We use | Example |
|---|---|---|
| **Change over time** | line chart / multi-series line chart, point plot with error bars | Q1.1 rank by year, Q1.4 average score by year |
| **Comparing amounts across groups** | bar chart (sorted, horizontal), grouped or stacked bar | Q2.1 states with most top-100 institutions |
| **A ranked list of winners and losers** | ranked bar chart or lollipop chart around zero | Q1.2 biggest climbers, Q7.4 largest moves |
| **Parts of a whole** | 100% stacked bar (pie chart only in the Chart Builder) | Q3.4 share in each score quartile |
| **The shape of one variable** | histogram with density curve | Q3.1 score distribution |
| **Comparing distributions of groups** | box-and-whisker plot, violin plot, overlapping histogram | Q3.5 spread per category, Q6.1 top 10 vs rest |
| **Relationship between two numbers** | scatterplot + least-squares line | Q4.1 RPC vs overall score |
| **Many correlations at once** | correlogram | Q4.3 which parameter correlates most |
| **Several parameters per institution** | grouped bar chart, matrix heatmap, small multiples | Q5.1 top-5 profiles |
| **Where (geography)** | choropleth map, bar chart of states | Q2.1 on the map |
| **Movement between categories (bands)** | matrix heatmap read like a confusion matrix | Q7.1 51–100 → top 50 |
| **Who stands out** | scatterplot with highlighted points, jittered strip chart, box plot with labelled outliers | Q8.1, Q8.3, Q8.5 |

---

## 2. Every Annexure A question and its chart

| Q | Question (short) | Chart | Why this chart |
|---|---|---|---|
| 1.1 | Rank of an institution 2017–2025 | line chart (multi-series for several) | Change over time; rank axis reversed so up = better; band years as a faint range bar |
| 1.2 | Greatest improvement | bar chart (ranked, horizontal) | Compare amounts; biggest climber is the top bar; labelled "old → new rank" |
| 1.3 | Largest decline | bar chart (ranked, horizontal) | Same chart, falls in coral, biggest fall on top |
| 1.4 | Average score over time | multi-series line chart | Change over time, one line per category |
| 1.5 | Consistently in the top 10 | matrix heatmap | Institution × year grid: "how often" and "which years" at a glance, rank written in each cell |
| 2.1 | States with most top-100 | bar chart (ranked, horizontal) | Compare counts; long state names fit on a horizontal axis |
| 2.2 | Geographic distribution over time | multi-series line chart | Each state's share from a common 0% baseline, so rises and falls can be compared |
| 2.3 | States that improved representation | bar chart (ranked, horizontal) | Change in count; teal = gained, coral = lost |
| 2.4 | Karnataka vs Tamil Nadu | box-and-whisker plot | Compares whole rank distributions (level and spread) per state and year |
| 2.5 | States producing most new entrants | stacked bar chart | Total per state, split by year (who and when) |
| 3.1 | Score distribution in a year | histogram with density curve | Classic picture of one variable's shape; KDE adds a smooth outline; mean and median lines |
| 3.2 | Distribution of ranks | stacked bar chart | Institutions per rank band, split into exact rank vs band only |
| 3.3 | Mean, median, min, max | box-and-whisker plot (+ table) | Makes the summary numbers visible; every institution a dot; mean ± SD diamond |
| 3.4 | % in each score quartile | stacked bar chart (100%) | Parts of a whole |
| 3.5 | Spread across categories | box-and-whisker plot | Many distributions side by side, sorted by median |
| 4.1 | RPC vs overall score | scatterplot | Standard picture of a two-number relationship, with trend line and r, ρ, R², p |
| 4.2 | PR vs overall score | scatterplot | Same |
| 4.3 | Parameter most correlated with overall | correlogram | Every pair's r in one grid; the "Overall score" row answers the question |
| 4.4 | TLR vs RPC | scatterplot | Same as 4.1 |
| 4.5 | Has the research–score correlation changed? | multi-series line chart | r and ρ per year: change over time |
| 5.1 | Top 5 across all five parameters | grouped bar chart | Parameters on the x-axis, one bar per institution: compare one parameter at a time |
| 5.2 | High research, low teaching | scatterplot | Median lines make four quadrants; the "high A, low B" quadrant is highlighted and labelled |
| 5.3 | High teaching, low perception | scatterplot | Same method |
| 5.4 | Score up despite a parameter falling | small-multiple bar charts | One small chart per institution, shared y-axis: which parameter fell, which rose |
| 5.5 | Largest strongest − weakest gap | lollipop chart | A long sorted list with less ink than bars |
| 6.1 | Top 10 vs the rest | violin plot | Shape + box + every dot; fair for groups of very different sizes (10 vs 90) |
| 6.2 | More dispersed in one year? | box-and-whisker plot | Taller box / longer whiskers = more spread, per year |
| 6.3 | Most variable parameter | bar chart (ranked, horizontal) | Ranks a handful of CV values |
| 6.4 | Median and IQR over time | point plot with error bars | Point = median, error bar = Q1 to Q3, so the bar length *is* the IQR |
| 6.5 | Score distribution by state | box-and-whisker plot | Level and spread across many states, sorted by median |
| 7.1 | 51–100 → top 50 | matrix heatmap (confusion-matrix style) | Every movement between bands at once; the answer cells are boxed |
| 7.2 | Entered / exited the top 10 | time-series dot plot | One row per institution, a dot per top-10 year, entry and exit markers |
| 7.3 | % staying in the same band | line chart | Retention per year pair: change over time |
| 7.4 | Largest up and down moves | lollipop chart | Both directions in one sorted picture around zero |
| 7.5 | Moved up / down / same each year | stacked bar chart | Counts and mix per year pair |
| 8.1 | High research for overall score | scatterplot | "Relative to the overall score" = distance from the regression line; outliers highlighted |
| 8.2 | Research much better than teaching | bar chart (ranked, horizontal) | Ranked RPC − TLR gaps |
| 8.3 | Unusual year-to-year score change | jittered strip chart | Every change a dot over a box per year pair; \|z\| > 2 highlighted |
| 8.4 | Strong parameter, poor rank | scatterplot | Parameter vs rank with Q3 and median-rank lines; the corner is highlighted |
| 8.5 | Unusually volatile ranks | box-and-whisker plot | Rank SD per peer band; dots beyond the whisker are the unusual ones |

**Extra views:** India **choropleth map** with a year slider (Geography); **vertically aligned time-series charts**
for State vs State (count on top, median rank below); **PCA scatterplot**; "today's top N followed back in time"
(multi-series line chart on Home); category × year coverage **matrix heatmap** (Data & Method). The **Chart
Builder** adds pie, bubble, grouped bar, violin, histogram, strip and heatmap charts for new questions.

---

## 3. When the "obvious" chart was not allowed: closest allowed choice

The course allows only the types in `docs/allowed_charts.md`. Not allowed: Sankey, radar/spider, parallel
coordinates, treemap, sunburst, waterfall, funnel, slope and dumbbell charts. Our substitutions:

| Usual choice | Not allowed because | What we used instead | Why it works |
|---|---|---|---|
| Radar chart for Q5.1 | Not taught | Grouped bar chart (or matrix heatmap) | Same profile, and bars are easier to read exactly than angles |
| Sankey diagram for Q7.1 | Not taught | Matrix heatmap read like a confusion matrix | Shows every band → band movement with exact counts |
| Slope / dumbbell for "old vs new rank" | Not taught | Ranked bar or lollipop chart of the change, labelled "old → new" | The change itself is the answer; both ranks are in the label |
| 100% stacked area for Q2.2 | In a stacked area only the bottom layer has a flat baseline | Multi-series line chart | Every state's share starts from the same 0% axis |
| Shaded Q1–Q3 band around a line | A band is not a taught type | Point plot with error bars | The error bar shows the same Q1–Q3 range |

A test (`tests/test_engines.py`) reads the allowed list and fails if any engine returns a chart type not on it.

---

## 4. Rules every chart follows

1. **The title states the answer**, not just the topic: "Tamil Nadu has the most institutions in the Overall top
   100 (17)", not "Top 100 by state".
2. **Axis titles with units**, also on name axes ("Institution", "State / UT", "NIRF parameter").
3. **Legend title** whenever a legend lists two or more entries.
4. **Rank axes reversed**: rank 1 at the top, so up = better.
5. **Useful hover text**: full institution name, exact values, n, Q1/Q3 where relevant.
6. **Source note** under every chart: "Source: NIRF, Ministry of Education, Govt. of India".
7. **Cross-category warning** whenever scores from different categories share a chart.
8. **Short names on axes, full names on hover** (cut to 36 characters: "IIT Madras", "Sri Ramachandra Institute
   of Higher…").
9. **Never rely on colour alone**: unusually high points are marigold **diamonds**, jumps up teal **triangles up**,
   drops coral **triangles down**, context points grey circles.
10. **Labels never overlap**: point labels are placed automatically in the first free spot around each point, with a
    thin leader line.

**Colour decisions:** one colour-blind-safe palette of 8 colours in a fixed order (checked with a colour-vision
simulation); groups beyond 7–8 are folded into "Other". **Teal = up / gained / positive, coral = down / lost /
negative** everywhere. One light→dark teal scale for amounts (heatmaps, map). Every chart also has a dark-mode
version. White chart surface for projector readability.

---

## 5. Concepts explained simply

- **Encoding:** how a number becomes something you see: position (best), length, angle, area, colour. Bars and
  dots use position and length, which people judge most accurately; this is why we prefer them to pies and radars.
- **Sorted bars:** sorting turns a bar chart into a ranking you can read top to bottom.
- **Diverging bars:** values can be negative, so bars go left (down/lost) or right (up/gained) of a zero line.
- **Small multiples:** the same small chart repeated for each group with the same axes, so panels compare directly.
- **Jitter:** a small random sideways shift so dots with similar values do not hide each other (fixed random seed,
  so the picture is the same every time).
- **Faceting / aligned charts:** stacking charts that share an axis (e.g. year) so you can read them together.
- **Sequential vs diverging colour scale:** sequential (light → dark) for "more"; diverging (two colours around a
  middle) for values that can be positive or negative, like correlations.

---

## 6. Likely viva questions with model answers

**Q1. How did you choose which chart to use for each question?**
By the shape of the question. Change over time gets a line chart; comparing amounts gets a sorted bar chart;
the shape of one variable gets a histogram; comparing distributions gets box or violin plots; two numbers get a
scatterplot with a trend line; geography gets a map; movement between bands gets a transition matrix. We could only
use chart types taught in the course, and each question's "Why this chart?" note in the Question Bank says why.

**Q2. Why is the rank axis upside down?**
Because a smaller rank is better. Reversing the axis puts rank 1 at the top, so a line going up means the
institution improved, which is how people naturally read a chart.

**Q3. Why didn't you use a radar chart for comparing the top five on five parameters (Q5.1)?**
Radar charts are not on our allowed list, and they are also hard to read: values are judged by angle and area and
change with the order of the axes. A grouped bar chart shows the same profile with parameters on the x-axis and one
bar per institution, so each parameter is compared by bar height, which is the most accurate visual judgement.
There is also a heatmap view with the numbers in the cells.

**Q4. Explain the transition matrix for Q7.1.**
Rows are the band in the first year (1-10, 11-50, 51-100, 101+, Not ranked), columns the band in the second year,
and each cell counts the institutions that made that move, darker meaning more. The diagonal is "stayed in the same
band"; cells to the left of it are moves to a better band, to the right to a worse one. The boxed cells (51-100 in
year A into 1-10 or 11-50 in year B) answer the question: 9 Overall institutions between 2017 and 2025.

**Q5. Why a violin plot for top 10 vs the rest, and not just two means?**
Two means hide the spread and the shape. The violin shows the whole distribution as a mirrored smooth curve (wide =
many institutions at that score), the box inside shows median and IQR, and every institution is a dot. It also works
for groups of very different sizes (10 vs 90). In Overall 2025 every top-10 score is above every other score.

**Q6. Why a box plot so often?**
A box plot compresses a distribution into five numbers we can explain: the median (line), Q1 and Q3 (box edges, so
the box is the IQR), the whiskers (up to 1.5 × IQR) and outliers (dots beyond). It lets us compare many groups side
by side (categories, years, states). We add every institution as a dot so small groups are not misleading.

**Q7. How do you make sure charts are readable for everyone, including colour-blind viewers?**
A colour-blind-safe palette checked with a simulation; at most 8 colours, the rest grouped as "Other"; highlights
also use shapes (diamonds, triangles), not just colour; titles state the answer; labels never overlap; full names
on hover; a white surface for the projector and a dark-mode version.

**Q8. How do you show a chart honestly when data is missing or limited?**
We never fill gaps: a year with only a band (e.g. 101–150) is a faint range bar in the rank line, not a fake point;
years without a rank are gaps. When the number of institutions changes between years, the insight warns, and a
"top 100 only" option makes years comparable. Charts mixing categories carry a visible note that their scores are
on different scales.
