# 00 · The big picture: NIRF Atlas as a story

Read this first. It explains the whole project with no technical words. The other files in `docs/team/` go
deeper, one area each:

| File | Area |
|---|---|
| `01_data_collection.md` | Getting the data from the NIRF website |
| `02_cleaning.md` | Turning messy tables into one clean table |
| `03_analysis_methods.md` | The statistics behind every answer |
| `04_charts.md` | Which chart we drew for each question, and why |
| `05_app.md` | The dashboard: pages, filters, how a question becomes a chart |
| `06_ai_chat.md` | Ask NIRF: typing a question in plain English |
| `demo_script.md` | The 7-minute live demo, click by click, with a backup plan |
| `viva_cheatsheet.md` | One page of definitions and chart-reading rules to revise before the viva |

---

## The story (for a 10-year-old)

Imagine every school in a huge country takes part in a big yearly sports day. Judges give each school marks in
five events, add the marks up, and print a list: 1st place, 2nd place, 3rd place... Every year a new list comes
out. Some years they even add new races (a swimming list, a chess list).

India does this for its colleges and universities. It is called **NIRF**, the National Institutional Ranking
Framework, run by the Ministry of Education. Every year since 2016 it publishes lists such as "the best 100
institutions overall", "the best engineering colleges", "the best law schools" and more. The five "events" are:

- **TLR** Teaching, Learning & Resources (good teachers, enough teachers, money spent on students)
- **RPC** Research & Professional Practice (papers, patents, projects)
- **GO** Graduation Outcomes (do students pass, get jobs, go for higher studies)
- **OI** Outreach & Inclusivity (girls, students from other states, disadvantaged students)
- **PR** Perception (what academics and employers think of the place)

Each event is marked out of 100, and the overall score is a weighted mix of the five.

Now imagine someone hands you **nine years of these lists, 2017 to 2025**, printed on hundreds of separate web
pages, with spelling mistakes, names that change ("IIT, Delhi" one year, "IIT Delhi" the next), states written
three different ways and some schools listed only as "somewhere between 101 and 150". Your teacher asks 40
questions, like "Which institutions climbed the most?" or "Which state has the most top-100 colleges?", and wants
each answer as a clear picture.

That is our project. We built a machine with four parts:

1. **The collector** (we call it the *Data Kitchen*, part one). It visits the NIRF website, saves all 290 pages
   and copies every table into a file, without changing a single letter.
2. **The cleaner** (*Data Kitchen*, part two). It fixes spellings, recognises that "IIT, Delhi" and "IIT Delhi"
   are the same place, turns text like "21A" into proper numbers and puts everything into **one big clean table**
   (11,647 rows: one row = one institution, in one list, in one year).
3. **The brain**. Eight "engines", each an expert at one kind of question (trends over time, maps, spreads,
   relationships, outliers ...). You give an engine a question with settings (which year, which list, which
   states), and it gives back a chart, the table behind it, a one-sentence answer and a note on how it calculated
   the answer.
4. **The face and the translator**. The face is the dashboard website with buttons and menus. The translator is a
   chat box: you type "Which states have the most top-100 colleges?", a language model (Google Gemini) turns your
   sentence into a short order form for the brain ("use the geography engine, count states, year 2025, top 100"),
   and the brain does the actual counting. **The language model never does the maths. Our code does.**

So: **website → saved pages → clean table → engines → charts on the dashboard (or in the chat).**

---

## The whole machine in one picture

```
                         NIRF ATLAS: HOW A QUESTION BECOMES A CHART

  +------------------------+
  |  nirfindia.org          |   290 official web pages, 2017-2025, 17 ranking lists
  |  (Ministry of Education)|
  +-----------+------------+
              |  1. COLLECT (scraper/): save each page once, copy every table as-is
              v
  +------------------------+
  |  data/raw/              |   290 CSV files, 75,626 rows, values kept exactly as printed
  |  (untouched copies)     |   ("21A", "Rank Withdrawn", "Pondicherry", "IIT, Delhi")
  +-----------+------------+
              |  2. CLEAN (pipeline/): standard names, states, categories, ranks, numbers;
              |     never invent a missing value; check every number against the web pages
              v
  +------------------------+
  |  nirf_master.parquet    |   ONE table: 11,647 ranked rows x 45 columns
  |  (single source of      |   1,647 institutions, 34 states/UTs, 17 categories, 9 years
  |   truth)                |
  +-----------+------------+
              |  3. ANALYSE (core/engines/): 8 engines
              v
  +--------------------------------------------------------------------------------+
  |  trends | geography | univariate | bivariate | multivariate | distribution |    |
  |  mobility | outliers                                                          |
  |  each returns:  chart + data table + one-line answer + "how we calculated it"  |
  +-----------+-------------------------------------------------------+------------+
              |  4a. SHOW (app/)                                      |  4b. ASK (nlq/)
              v                                                       v
  +------------------------------+                   +-------------------------------+
  |  Streamlit dashboard          |                   |  Ask NIRF chat                 |
  |  Question Bank (all 40)       |                   |  question --> Gemini writes a  |
  |  7 Explore pages (filters)    |                   |  small JSON plan --> OUR code  |
  |  Chart Builder, Data & Method |                   |  checks it and runs an engine  |
  +------------------------------+                   +-------------------------------+
              \                                                       /
               \___________________ same engines, same numbers _____/
```

---

## What the examiner will test, and which part answers it

| Level | Marks | What is tested | Where in our project |
|---|---|---|---|
| 1 | 10 | All 40 sample questions (Q1.1 to Q8.5) give the correct chart | **Question Bank** page: every question one click away; "Run all 40" shows 40 ticks |
| 2 | 5 | New questions, answered by changing filters (years, category, states, institutions, parameters) | **Explore pages** (every setting of every analysis) and the **Chart Builder** |
| 3 | 5 | A typed question becomes a data query and a chart | **Ask NIRF** chat |

The examiner does not ask about code. He asks us to explain three things: **how we processed the data**,
**which analytical methods we used** and **why each chart looks the way it does**. That is exactly what the
files in this folder teach.

---

## Five rules we follow everywhere (memorise these)

1. **A smaller rank is better.** Rank 1 is the top. On every chart with a rank axis, the axis is flipped so that
   "up = better".
2. **Improvement = old rank − new rank.** Going from rank 20 to rank 5 is 20 − 5 = **+15** (moved up). Going from 5
   to 20 is −15 (moved down).
3. **Never compare scores across categories without a warning.** Each list has its own weights (Engineering, College
   and Law weigh the five parameters differently), so a 70 in Law is not "the same" as a 70 in Engineering. Every
   chart that mixes categories carries a visible note.
4. **Never invent data.** If NIRF only says "somewhere in 101-150", we do not pretend the rank is 125. If a score is
   missing, it stays missing.
5. **Every chart tells its answer.** The title states the finding, axes and legends have titles, hovering shows
   details, and the note "Source: NIRF, Ministry of Education, Govt. of India" sits under every chart.

---

## Key numbers to quote

| Fact | Value |
|---|---|
| Years covered | 9 (2017 to 2025) |
| Ranking categories | 17 (6 lists in 2017 → 17 in 2025) |
| Web pages scraped | 290 (all OK, none failed) |
| Raw rows | 75,626 (incl. 63,975 rows of "participant lists" that have no rank) |
| Ranked rows in the master table | 11,647 (6,974 with an exact rank, 4,671 known only by a rank band) |
| Distinct institutions | 1,647 (from 2,288 different spellings of names) |
| States and UTs | 34 (from 49 raw spellings) |
| Analysis engines | 8 |
| Annexure A questions answered | 40 of 40 |
| Spot check | all 11,647 rows compared with the original pages: 0 real differences |

---

## One-minute version (say this if someone asks "what did you build?")

"We built NIRF Atlas, an interactive dashboard on India's official NIRF university rankings from 2017 to 2025, in
all 17 ranking categories. We scraped 290 pages from the NIRF website, cleaned them into one master table of
11,647 rows (one institution, one list, one year), standardising institution names, states, categories and ranks
without inventing any value. Eight analysis engines answer questions about trends, geography, distributions,
correlations, multi-parameter profiles, rank mobility and outliers; each returns a chart, its data, a one-line
answer and the method. The dashboard answers all 40 sample questions in one click, any new question by changing
filters, and typed questions through a chat where a language model only writes the query plan and our own code
computes every number."
