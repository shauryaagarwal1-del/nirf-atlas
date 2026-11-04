# 05 · The app: the dashboard the examiner will click

**In one sentence:** a Streamlit website with 12 pages that runs the same eight engines behind three ways of
asking: one click per Annexure question (Question Bank), any setting of any analysis (Explore pages and Chart
Builder), and typed questions (Ask NIRF).

---

## 1. What it does and why

The examiner tests three levels. Each has its own part of the app:

| Level | What the examiner does | Where |
|---|---|---|
| 1 (10 marks) | Picks any of the 40 sample questions | **Question Bank**: 8 tabs × 5 questions, one click each; "Run all 40" shows 40 ticks |
| 2 (5 marks) | Asks a *new* question ("same for Engineering in 2019, top 50, Kerala only") | **Explore pages** (every knob of every analysis) and **Chart Builder** |
| 3 (5 marks) | Types a question | **Ask NIRF** chat (see `06_ai_chat.md`) |

How to start it: `streamlit run app/Home.py`. Every page except Ask NIRF works offline.

---

## 2. The pages (sidebar order)

| Section | Page | What it shows |
|---|---|---|
| | **Home** | What NIRF Atlas is; key numbers (9 years, 17 categories, 1,693 institutions, 34 states/UTs, 11,647 rows); "today's top N followed back in time" chart; cards linking every page |
| | **Question Bank** | The 40 Annexure A questions. Tabs: Trends, Geospatial, Univariate, Bivariate, Multivariate, Distribution, Mobility, Outliers. Each question: the question, a "Why this chart?" note, its own controls, the chart card. "Run all 40" grid with ticks and previews |
| Explore | **Trends** | Rank lines, parameter lines of one institution, climbers, fallers, average/median score per year, who stayed in the top N, today's top N back in time |
| Explore | **Geography** | Tabs: India map (year slider + play), State vs State, New entrants, More views |
| Explore | **Distributions** | Score histogram, rank bands, summary statistics, quartile shares, top N vs rest, spread per year, median & IQR over time, most variable parameter, scores by state, spread across categories |
| Explore | **Relationships** | "Select any two variables": scatterplot + Pearson r, Spearman ρ, R², p-value, n; correlogram; correlation over the years |
| Explore | **Multi-Parameter** | Parameter profiles, high on one/low on another, overall rose although a parameter fell, strongest − weakest gap, PCA |
| Explore | **Mobility** | Band transition matrix, top-N entries and exits, band retention, largest climbs and falls, up/down/same per year |
| Explore | **Outliers** | Parameter unusually high for the score, research ≫ teaching, unusual score jumps, strong parameter but poor rank, volatile ranks vs peers |
| Build & ask | **Chart Builder** | Pick filters, a group, a number, an aggregation and an allowed chart type for questions no ready-made analysis covers |
| Build & ask | **Ask NIRF (AI)** | Type a question, get the chart |
| Reference | **Data & Method** | Pipeline diagram with real counts, the cleaning steps (rows before/after, what changed, why), category × year coverage, data dictionary, limitations, download |

---

## 3. How one question becomes a chart in the app

```
  sidebar filters (category, years, states, institutions, top N)
        |                         +--- page controls (single year, parameters, |z| cut-off, chart view...)
        v                         v
  page picks an analysis  --->  engine function(settings)  --->  ChartResult
                                (same code for every page          |
                                 and for the chat)                 v
                                                       +---------------------------+
                                                       |  CHART CARD               |
                                                       |  chart (title = answer)   |
                                                       |  one-line answer          |
                                                       |  > How we calculated this |
                                                       |  > See the data  [CSV]    |
                                                       +---------------------------+
```

- **The chart card** is the same everywhere: the chart, the one-sentence answer, "How we calculated this" (the
  method in plain words) and "See the data" (the exact table, downloadable as CSV). This is how we prove a chart is
  right live: open the data and show the numbers.
- **The sidebar filters are shared**: category, year range, states, institutions and top N follow you from page to
  page. On Explore pages the controls above the chart and the sidebar are the *same* value: change either and both
  update.
- **Every parameter of every analysis has a control** (a test checks this), so any variation of an Annexure
  question is a few clicks away. Example: Q2.1 asks about the Overall top 100 in 2025; changing Category to
  Engineering, Year to 2019 and Top list to 50 answers "Which states have the most Engineering institutions in the
  top 50 in 2019?" (Tamil Nadu, 9).
- **"Only states"** on any analysis limits it to institutions in those states, and the chart's subtitle, answer and
  method say so (ranks stay national).
- **Friendly messages instead of crashes**: an impossible choice (a parameter question for Innovation, which
  publishes no parameter scores; "From year" after "To year") explains what to change.
- **Deep links**: `?q=Q4.3` in the address opens that question, so a link can be shared or bookmarked.

---

## 4. Level 2 strategy (what to do when the examiner asks something new)

1. **Is it an Annexure question with different settings?** Open it in the Question Bank (or the matching Explore
   page) and change the controls: year(s), category, institutions, states, parameters, top N, threshold.
2. **Is it a different analysis of the same kind?** The Explore page for that topic lists every analysis in plain
   English under "What do you want to see?".
3. **Is it a simple "group and summarise" question?** Chart Builder: filters → X group → number → count/mean/median
   → chart type. Example: "What share of the Overall top 100 in 2025 does each region hold?" → pie chart, Region,
   Count: South 35%.
4. **Typed is faster?** Ask NIRF.

We rehearsed 15 new questions this way: `docs/level2_questions.md` (each with page, controls and the answer), and
a test sets exactly those controls in the real app and checks the answer.

---

## 5. Key decisions (and why)

| Decision | Why |
|---|---|
| **Streamlit** (Python) for the website | The whole project stays in Python with pandas and Plotly; interactive widgets with little code |
| **Plotly** charts | Interactive: hover for details, zoom, legend toggles, download as image |
| **One shared engine layer** for all pages and the chat | One calculation per question: two pages can never disagree |
| **Question Bank separate from Explore pages** | Level 1 needs speed (one click per question); Level 2 needs every setting |
| **Chart card with method and data** on every chart | The examiner asks about methods: the explanation is always one click away, and the data can be checked |
| **Only the open tab is computed; the master table is loaded once** | Pages open in under a second during the live demo |
| **Projector layout** (tested at 1366 × 768), light and dark theme | The demo runs on a projector; screenshots of every page are in `docs/previews/pages/` |
| **Automatic tests run the real app** (headless) | All 40 deep links open with one chart and no error; every Explore view draws a chart; the 15 Level 2 answers are checked |

---

## 6. Concepts explained simply

- **Dashboard:** a page of charts and controls that answers questions about data interactively.
- **Streamlit:** a Python library that turns a script into a web app. Each time you click something, the script
  runs again from the top with the new choices (a "rerun").
- **Widget:** a control such as a dropdown, slider, multiselect or toggle.
- **Session state:** the app's memory for one visitor (your current filters), so choices survive page changes.
- **Caching:** keeping a result in memory so it is not recomputed (the master table is read once per server).
- **Interactive chart:** hovering shows exact values; clicking a legend entry hides that series.
- **Deep link:** an address that opens the app at a specific question.
- **Headless test:** running the app inside a test without a screen, clicking controls in code and checking the
  result.

---

## 7. Likely viva questions with model answers

**Q1. Walk us through the dashboard's structure.**
Twelve pages in four groups. Home gives an overview and key numbers. The Question Bank holds all 40 Annexure
questions, one click each. Seven Explore pages (Trends, Geography, Distributions, Relationships, Multi-Parameter,
Mobility, Outliers) offer every analysis with every setting. Chart Builder and Ask NIRF handle new questions, and
Data & Method explains the data and cleaning. All pages share the sidebar filters and the same eight engines.

**Q2. How would you answer a question that is not among the 40?**
First, change the filters of the closest question: years, category, states, institutions, parameters, top N. If it
is a different kind of question, the Explore page for that topic lists more analyses. For simple group-and-summarise
questions there is the Chart Builder, and for typed questions the Ask NIRF chat. We rehearsed 15 such questions.

**Q3. How do we know a chart is correct, live?**
Every chart card has "See the data" with the exact table behind the chart and a CSV download, and "How we calculated
this" with the method. The numbers come from the master table, which was checked field by field against the
original NIRF pages. Automated tests also check that all 40 questions draw their intended chart.

**Q4. What happens if I choose something that doesn't make sense, like TLR for Innovation?**
The app shows a friendly message explaining why (Innovation publishes no parameter scores) and what to change,
instead of an empty or wrong chart. The same for impossible year ranges or filters with no data.

**Q5. Why Streamlit and Plotly?**
Both are Python, so data processing, analysis and the website share one language and one codebase. Streamlit gives
widgets and pages with little code; Plotly gives interactive charts with hover details, which help the examiner see
exact values and full institution names.

**Q6. Do the filters apply everywhere?**
Category, year range, states, institutions and top N are shared by every page and follow you between pages. Each
analysis can add its own controls, such as a single year, the parameters to compare, the z cut-off or the chart
variant. The state filter limits any analysis to institutions in those states and the chart says so.

**Q7. How did you make sure the app is fast and doesn't crash in the demo?**
The master table is loaded once and kept in memory, and only the open tab or chosen analysis is computed, so pages
open in under a second. Automatic tests run the real app headless: all 40 questions, every Explore view and the
Level 2 questions. Every question was also run for every category to make sure each gives a chart or a friendly
message.

**Q8. Which chart is the "select any two variables" feature the statement mentions?**
The Relationships page, first view: choose X and Y (overall score, any parameter, or rank), the category, year,
colouring, top N, states and trend line on/off. It draws the scatterplot with a least-squares line and shows Pearson
r, Spearman ρ, R², the p-value and n, plus one sentence interpreting them.
