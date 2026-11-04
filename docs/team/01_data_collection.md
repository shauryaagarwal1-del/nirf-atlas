# 01 · Data collection: getting the rankings from the NIRF website

**In one sentence:** our scraper visits every NIRF ranking page for 2017–2025, saves each page once, and copies
the table on it into a CSV file **without changing any value**.

Deeper reference: `docs/explanations/scraper.md` (how the scraper works), `docs/source_map.md` (what the site
offers, year by year), `docs/sources.md` (sources and licences).

---

## 1. What it does and why

NIRF publishes its rankings only as **web pages** on https://www.nirfindia.org. There is no download button and no
spreadsheet for all years. To analyse nine years we first need the numbers in files a computer can read.

```
  nirfindia.org        save once         read the table        one CSV per page
 +-------------+      +-----------+      +---------------+      +-----------------+
 | web page    | ---> | HTML copy | ---> | rows x columns| ---> | data/raw/csv/   |
 | (category,  |      | (cached,  |      | + hidden      |      | + year, label,  |
 |  band, list)|      |  never    |      |   parameter   |      |   page URL      |
 +-------------+      |  edited)  |      |   scores      |      +-----------------+
                      +-----------+      +---------------+              |
                                                                        v
                                                     scrape_log.csv: one line per page (rows, status, notes)
```

**Result of our run (3 November 2026):** 290 pages, all OK, none failed, **75,626 rows** in total:

| Kind of page | What it holds | Rows |
|---|---|---|
| Ranking page | Exact rank, score, the five parameter scores | 6,976 |
| Rank-band page | Name, city, state only, under a heading such as "Rank-band: 101-150" | 4,671 |
| Participant list | Every institution that applied, with no rank | 63,975 |
| Special Mention (2018 only) | 4 institutions, no rank, no score | 4 |

---

## 2. How the site is organised (what we had to understand first)

- The **home page** links one index page per year.
- Each **year page** links the categories published that year (Overall, Engineering, Medical ...).
- Each **category page** shows the main table (exact ranks with scores) and links to:
  - **rank-band pages** ("Rank-band: 101-150", "151-200"...): institutions NIRF places in a group, not at an exact
    position;
  - the **List of Participating Institutions**: everyone who applied.
- The **five parameter scores** are hidden inside each row's Name cell (the site shows them when you click
  "More Details"). We read that hidden mini-table.
- In 2017, 2018 (and on the University page every year) there are also tabs "By TLR", "By RPC"... giving each
  institution's **rank on that parameter**; we read those too and matched them to the main table by the
  **Institute ID**. The tab scores matched the hidden scores on every row.

Surprises we found and handled:
- The number in a band page's file name is **not** the band (2020 `EngineeringRanking150.html` holds band
  201–250). We take the band from the link text and the page heading instead.
- A hint we were given ("2017 pages sit at a different address") was wrong: that address returns "not found".
  2017 uses the same pattern as every other year.
- The 2023 Innovation page calls its rank column "Band".
- 2025 Dental shows "Rank Withdrawn*" stretched over the Score and Rank columns.

**Categories by year** (17 in total; the full table with row counts is in `docs/source_map.md`):

| Since | Categories added |
|---|---|
| 2017 | Overall, University, College, Engineering, Management, Pharmacy |
| 2018 | Medical, Architecture, Law (+ a one-off "Special Mention" page, not a ranking) |
| 2020 | Dental |
| 2021 | Research Institutions |
| 2023 | Agriculture & Allied Sectors, Innovation |
| 2024 | Open University, Skill University, State Public University |
| 2025 | SDG Institutions |

---

## 3. Key decisions we made (and why)

| Decision | Why |
|---|---|
| **Keep every value as the original text** at this stage (`21A`, `Rank Withdrawn`, `Pondicherry`). | Nothing is guessed or lost while collecting. All fixing happens in the cleaning step, where each rule can be checked and explained. |
| **Save each HTML page once and reuse the saved copy** (a cache). | The website is asked only once; re-running is fast and gives exactly the same files; if the site changes or goes down, our data does not. |
| **Download politely:** one page at a time, a 1–2 second pause, retries if slow. | We do not overload a government website. |
| **Add the year, the category label exactly as NIRF printed it, and the page URL to every row.** | Every number can be traced back to its source page. The original label ("Research" in 2021–23, "Research Institutions" in 2024–25) is kept for honest historical comparison. |
| **Scrape band pages and participant lists too**, not only the main tables. | Band pages tell us who was ranked 101–200 (needed for transitions and new entrants). Participant lists are kept separately so they are never counted as "ranked". |
| **Give Research Institutions their own columns** (QnR, QlR, SFC). | That list uses different parameters; mixing them into TLR/RPC/GO would be wrong. |
| **One bad page never stops the run.** | A page that fails is written to the log as `failed` with the reason and the scraper moves on. We tested this with a fake missing page. |
| **Scope 2017–2025.** | The project statement asks for these nine years. (2016 exists on the site but is outside the brief.) |
| **We did not download the per-institution PDFs** (the data each college submitted). | The questions are answered by the published ranks and scores; the PDFs are a backup source only. |

---

## 4. Concepts explained simply

- **Web page / HTML:** a web page is a text file written in HTML, a language of tags such as `<table>` (a table),
  `<tr>` (a row) and `<td>` (a cell). A browser turns it into what you see; a scraper reads the tags directly.
- **Web scraping:** using a program to read data off web pages, the way a person would copy a table by hand, but
  for 290 pages without typing mistakes.
- **CSV file:** "comma-separated values", a plain-text table: one line per row, commas between the columns. Every
  tool (Excel, pandas) can open it.
- **Cache:** a saved copy kept so you do not have to fetch something again.
- **Rank band:** NIRF gives exact positions only at the top of each list (e.g. 1–100). Below that it publishes
  groups: "these 50 institutions are somewhere in 101–150", in alphabetical order, with no score.
- **Participant list:** every institution that took part, ranked or not. It is much longer than the ranking
  (63,975 rows vs 11,647 ranked rows) and has no rank.
- **Institute ID:** NIRF's own code for an institution (e.g. `IR-O-U-0456`). It is a reliable link between tables
  on the same page, and from 2018 its core part is stable across years (used later to match institutions).
- **Log file:** a diary of the run, one line per page: how many rows, OK or failed, anything odd.

---

## 5. How we know the collection is right

- `data/raw/scrape_log.csv`: every one of the 290 pages has status `ok`.
- For every year × category, the number of rows matches what the site shows (table in `docs/source_map.md`).
- Later, the **spot check** re-read the saved web pages with a separate small reader and compared every field of
  all 11,647 ranked rows with our master table: **0 real differences** (see `02_cleaning.md`).
- A test checks that the raw CSVs still hold the row counts the log recorded.

---

## 6. Likely viva questions with model answers

**Q1. Where does your data come from?**
From the official NIRF website, nirfindia.org, run by the Ministry of Education. We scraped all ranking pages for
2017–2025: 290 pages covering 17 categories, including the main ranking tables, the rank-band pages and the
participant lists. Every chart carries the note "Source: NIRF, Ministry of Education, Govt. of India".

**Q2. Why did you scrape instead of downloading a dataset?**
NIRF publishes the rankings only as web pages; there is no official file for all years. Ready-made datasets online
cover a few years or categories and we cannot verify how they were cleaned. Scraping the official pages ourselves
means every number can be traced to its source page.

**Q3. Did you change any values while scraping?**
No. The scraper keeps every value as the original text, including odd ones like "21A" or "Rank Withdrawn". It only
adds information: the year, the category label as printed and the page address. All cleaning happens in the next
step, where each rule is documented and checked.

**Q4. How did you get the five parameter scores?**
They are on the ranking pages but hidden in each institution's "More Details" box. We read that hidden mini-table
for every row. For 2017–2018 and the University list, the page also has "By TLR / By RPC" tabs with parameter
ranks; we joined those on the Institute ID and confirmed the scores in the tabs matched the hidden ones on every
row.

**Q5. What is a rank band, and why did you scrape those pages?**
Below the top of a list, NIRF publishes groups like "101–150" in alphabetical order with no exact rank and no score.
We scraped them because they tell us an institution *was* ranked that year, which matters for questions about
movement between bands, entries into the ranking and new entrants. We never turn a band into a fake exact rank.

**Q6. Why are participant lists kept separately?**
They list everyone who applied, ranked or not, and they are five to six times longer than the rankings. If we mixed
them into the main table, every count of "ranked institutions" would be wrong. They are stored in a separate table.

**Q7. What happens if the website changes or a page fails?**
Each page is saved once as HTML and reused, so our data does not change when the site changes. If a page fails it is
logged as `failed` with the reason and the run continues. In our final run all 290 pages were OK.

**Q8. How do categories that change over the years affect your data?**
NIRF started with 6 lists in 2017 and had 17 by 2025; some were renamed ("Research" became "Research Institutions").
We keep the label exactly as NIRF printed it in a separate column and add a standard name during cleaning, so a
trend line can run across a rename while the history stays honest. Charts only show the years in which a category
existed.
