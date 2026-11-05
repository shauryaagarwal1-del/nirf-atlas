# Demo script: 7 minutes, live

Goal: show in 7 minutes that (1) the data is complete and clean, (2) all 40 questions work (Level 1), (3) new
questions are answered by changing filters (Level 2), (4) a typed question becomes a chart (Level 3), and that we
can explain every step. Rehearse it at least three times with a timer.

**Roles** (fill in names): **Driver** clicks and never talks over the speaker · **Speaker A** data (Home, Data &
Method) · **Speaker B** Level 1 and Level 2 · **Speaker C** Ask NIRF and the wrap-up. Anyone may take any examiner
question; the person who owns that area answers first.

**Golden rules while presenting:** read the chart title aloud (it states the answer) · point at the axis and say
"rank 1 is at the top, so up means better" the first time a rank chart appears · open "See the data" at least once ·
never scroll fast · if something is slow, keep talking about the method.

---

## Before the demo (checklist)

**The evening before**
- [ ] `git pull` on branch `shaurya` on the demo laptop **and** on a second laptop (backup).
- [ ] `python -m pytest` passes. (On this laptop set `OPENBLAS_NUM_THREADS=1` first if a memory error appears.)
      It never calls Gemini, so it is safe to run on the demo day.
- [ ] `python -m scripts.exam_simulation` shows 30/30 for the UI path and the chat, and each of us has practised
      the tricky questions in `docs/exam_simulation.md` (a state with one institution, start year after end year,
      a category that starts in 2023, ties, band-only ranks).
- [ ] `python scripts/screenshot_pages.py` runs: it screenshots every page at projector size (1366 × 768) in light
      and dark theme and prints each page's load time. The screenshots in `docs/previews/pages/` are the offline
      backup.
- [ ] `.env` has a working `GEMINI_API_KEY` (and ideally `GEMINI_API_KEY_2`). Run `python -m scripts.nlq_accuracy`
      once; do **not** run it again on the morning of the demo (it uses up free quota).
- [ ] Charge both laptops; pack the charger and an HDMI adapter.

**30 minutes before**
- [ ] Start the app: `python -m streamlit run app/Home.py`. Open it in the browser, full screen (F11), zoom 100%.
- [ ] Click through every page once (warms the cache, so the demo is fast).
- [ ] Ask NIRF: the sidebar dot is **green**. Ask one example question so the connection is warm.
- [ ] Set the sidebar back to defaults: Category **Overall**, years **2017–2025**, no states, top N **10**.
- [ ] Phone hotspot ready in case the venue Wi-Fi fails.
- [ ] Open a second browser tab with `docs/previews/pages/` screenshots (or the `docs/previews/Q*.html` charts) in
      case the app cannot run at all.

---

## The script (7:00)

### 0:00–0:45 · Home: what we built (Speaker A)
**Click:** Home (already open).
**Say:** "NIRF Atlas is a dashboard on India's official NIRF rankings from 2017 to 2025, across all 17 ranking
categories. We scraped 290 official pages and cleaned them into one master table of 11,647 rows: one institution,
in one ranking list, in one year. These cards show the scale: 9 years, 17 categories, 1,647 institutions after
name standardisation, 34 states and UTs."
**Point at** the line chart: "This is today's Overall top 10 followed back in time. Rank 1 is at the top, so up
means better."

### 0:45–1:45 · Data & Method: how we cleaned it (Speaker A)
**Click:** sidebar → Data & Method.
**Say:** "Four layers: scrape, clean, eight analysis engines, and the dashboard plus the chat. The raw pages had 49
spellings for 34 states, 2,288 spellings for 1,647 institutions, renamed categories and ranks like '21A' or only a
band like 101–150."
**Click:** in the cleaning steps, choose **step 7, Institution identity**.
**Say:** "We match names by a normalised key in the same state, NIRF's own ID code, hand-checked alias rules and
fuzzy matching; two rows of the same list are never merged, and uncertain pairs go to a human. We never invent
values: a band-only institution gets no fake exact rank. Our spot check compared all 11,647 rows with the original
pages: zero real differences."
**Scroll to** Limitations (one sentence): "Scores are only comparable within a category, because each has its own
weights."

### 1:45–3:30 · Question Bank: Level 1 (Speaker B)
**Click:** sidebar → Question Bank. Tab **1 · Trends** → **Q1.1**.
**Say:** "All 40 Annexure questions, eight tabs of five. Q1.1: IIT Madras went from rank 2 in 2017 to rank 1 and
has held it every year since 2019 (IISc was first in 2017 and 2018). Every chart has a one-line answer, 'How we calculated this' and 'See the data'."
**Click:** tab **2 · Geospatial** → **Q2.1**. Open **See the data**.
**Say:** "Tamil Nadu has the most institutions in the Overall top 100 in 2025, 17, then Maharashtra 11 and Uttar
Pradesh 9. 'Top 100' means certainly in the top 100: an exact rank up to 100, or a band that ends by 100. Here is
the exact table behind the chart, downloadable as CSV."
**Click:** tab **4 · Bivariate** → **Q4.3**.
**Say:** "A correlogram: Pearson r between every pair. Research, RPC, has the strongest correlation with the
overall score, r = 0.89, then Perception, 0.85. Part of that is built in, because the score is a weighted sum
with RPC at 30%."
**Click:** tab **7 · Mobility** → **Q7.1**.
**Say:** "A transition matrix: rows are the band in 2017, columns in 2025, each cell counts institutions. The
diagonal is 'stayed in the band'. The boxed cells answer the question: 9 institutions moved from 51–100 into the
top 50."
*(Optional if ahead of time: click **Run all 40** and say "every question runs and draws its registered chart
type: 40 ticks".)*

### 3:30–5:15 · Level 2: new questions by changing filters (Speaker B)
**Click:** back to **Q2.1**. Change **Category → Engineering**, **Year → 2019**, **Top N (rank cut-off) → 50**.
**Say:** "A new question: which states have the most Engineering institutions in the top 50 in 2019? Same method,
new settings: Tamil Nadu again, with 9." Click **Reset**.
**Click:** sidebar → Geography → tab **India map**. Press **▶ Play**.
**Say:** "The same count on a choropleth map. The colour scale is fixed across years, so a colour means the same
number in every year; watch the South stay dark."
**Click:** sidebar → Relationships (first view: any two numbers). Set **X = PR**, **Y = Overall score**,
**Year = 2024**, **Category = Engineering**.
**Say:** "The statement's 'select two variables' feature: scatterplot, least-squares line, Pearson r 0.84,
Spearman ρ 0.70, R² 0.71. A strong positive relationship, and significant." Then switch **Category → Management**:
"r = 0.82, so PR is linked slightly more strongly in Engineering."
*(If the examiner asks something new here, answer it now instead; that is the point of Level 2.)*

### 5:15–6:30 · Ask NIRF: Level 3 (Speaker C)
**Click:** sidebar → Ask NIRF (AI). Click the example chip **"Karnataka vs TN engineering colleges"**.
**Say:** "Gemini reads the question and writes only a small JSON plan: which of our analyses to run and with which
settings. It never sees the data and never calculates a number. Our code checks the plan, translates 'TN' to Tamil
Nadu, and runs the same engine as the dashboard."
**Click:** open **How I understood your question**. Point at the assumptions and the plan.
**Click:** the Hinglish chip **"Kaun se institutes hamesha top 10 mein rahe?"**.
**Say:** "Hinglish works too: this becomes 'who stayed in the top 10 for many years'." Read the title aloud (with the
Question Bank's default settings, 8 institutions were in the Overall top 10 in all 9 years). Click one
**follow-up** button if time allows.
*(If the examiner wants to type, let them type. Good test questions: "which pharmacy colleges climbed the most in
the last 3 years", "IIT Bombay rank since 2017". If they try a trick question, read the "Assumed:" box aloud:
"IIIT Bangalore from 2017-2025" → Engineering 2018-2025, because it is not in Overall and not ranked in 2017;
"Will IIT Mandi overtake IIT Jodhpur?" → the past with a notice, no forecast; "rank trend of NIT" → buttons to pick
which one; "NIT ranking" → the top 10 NITs in Engineering, the list most NITs are in; two questions at once → the
first is answered and a notice points to the second.)*

### 6:30–7:00 · Wrap-up (Speaker C)
**Say:** "So: all 40 questions in one click, any new question by changing filters or in the Chart Builder, and typed
questions through the chat, which plans the query while our code computes every number. Every chart states its
answer, shows its method and its data, and uses only chart types from the course list. Thank you; we're happy to
explain any step."

---

## Backup plan: if something breaks

| What breaks | What we do (and say) |
|---|---|
| **A page is slow** | Keep talking about the method of the chart that is loading; never stare at the spinner. Pages normally open in under a second after the warm-up click-through. |
| **The app shows an error or freezes** | Press **R** in the browser (Streamlit rerun) or reload the page. If it persists: in the terminal press Ctrl+C and run `streamlit run app/Home.py` again (≈ 10 s). Meanwhile Speaker A explains the cleaning steps from memory. |
| **A filter combination gives a message instead of a chart** | That is designed: read the message aloud ("Innovation publishes no parameter scores") and click **Reset**. |
| **Ask NIRF: red dot / quota used up / no internet** | Say: "The chat needs the Gemini API; when it cannot be reached it falls back without any model." Show the fallback: it offers the closest sample questions; click **Run Qx.y here**. Then switch to the phone hotspot and try once more. The app also tries the next Gemini model and the spare key automatically. |
| **Ask NIRF misunderstands a question** | Open **How I understood your question**, explain what it planned, then rephrase more specifically ("in Engineering, 2023"), or answer the same question in the Question Bank / Explore page. This shows the design: the plan is transparent and checkable. |
| **No internet at all** | Everything except Ask NIRF works offline. Do the full demo, and for Level 3 show the fallback and explain the pipeline with `06_ai_chat.md`. |
| **Projector looks wrong** (cut off, tiny) | Browser zoom Ctrl + − / Ctrl + 0; collapse the sidebar with its arrow; the layout was tested at 1366 × 768. |
| **The demo laptop fails** | Switch to the second laptop (already pulled and tested). |
| **Nothing runs at all** | Open the screenshots in `docs/previews/pages/` and the interactive chart files `docs/previews/Q1.1.html` … `Q8.5.html` (they open in any browser, offline) and present from them. |
| **Examiner asks something we cannot answer with filters** | Try the Chart Builder (group + number + aggregation + chart). If the data cannot answer it (e.g. fees, salaries, 2016), say so honestly: "NIRF does not publish that in the rankings; our data covers ranks, scores and the five parameters for 2017–2025." Never guess a number. |

---

## 30-second answers to have ready

- **"What does the chart's title mean?"** It states the answer to the question, in words.
- **"Where is this number from?"** "See the data" under the chart; every number comes from the master table, which
  was checked against the original NIRF pages.
- **"Why this chart?"** The Question Bank shows a "Why this chart?" note for every question (see `04_charts.md`).
- **"What if an institution only has a band?"** It counts for "certainly in the top N" questions but is left out of
  rank arithmetic; we never invent a mid-point. Its history is drawn as the band chart (Trends → "Rank bands of
  colleges without an exact rank"): each bar spans the published band.
- **"Will X overtake Y?" / "Who will be #1 next year?"** "We don't forecast: the chat shows how they have done so
  far, says who is ahead now and how the gap changed, and labels it clearly as the past."
- **"Can scores be compared across categories?"** No: each category has its own weights; charts that mix them carry
  a visible note.
