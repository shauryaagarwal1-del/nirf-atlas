"""Data & Method: where the data comes from, how it was cleaned, what every column means and what to watch out for.

Sections, top to bottom:
  1. Pipeline     a diagram of the four layers, from the NIRF website to the chart, with the real counts;
  2. Sources      the NIRF pages, the map file and the chat model, and what each one is used for;
  3. Cleaning     every cleaning step with rows before and after (read from docs/cleaning_report.md, so the
                  page always matches the last pipeline run), and what it changed and why;
  4. Coverage     which categories exist in which years (heatmap);
  5. Dictionary   every column of the master table, searchable;
  6. Limitations  banded ranks have no score, scores are not comparable across categories, and the NIRF
                  method changed over the years (counts computed from the master table);
  7. Data         the master table filtered by the sidebar, to inspect or download.
"""

import html

import streamlit as st

from app.components import empty_state, kpi_cards, page_header, section_title, show
from app.filters import category_years_map, current, master
from app.nav import PAGES
from core.cleaning_report import find_count, read_cleaning_report
from core.questions import QUESTION_REGISTRY


@st.cache_data(show_spinner=False)
def report():
    return read_cleaning_report()


@st.cache_data(show_spinner=False)
def limitation_counts() -> dict:
    """The numbers quoted in the limitations, counted from the master table."""
    df = master()
    banded = df["is_banded"]
    no_score_exact = ~df["has_score"] & ~banded
    rank_only = (df.groupby("category_std")["has_score"].sum() == 0)
    research = df["category_std"].eq("Research Institutions")
    per_year = df.groupby("year")["category_std"].nunique()
    bands = df.loc[banded, "rank_band_nirf"].dropna().unique()
    return dict(rows=len(df), banded=int(banded.sum()), banded_pct=100 * banded.mean(),
                no_score_exact=int(no_score_exact.sum()), rank_only=sorted(rank_only[rank_only].index),
                research_rows=int(research.sum()), first_year=int(per_year.index.min()),
                last_year=int(per_year.index.max()), first_n=int(per_year.iloc[0]), last_n=int(per_year.iloc[-1]),
                n_band_labels=len(bands))


def esc(text) -> str:
    return html.escape(str(text))


f = current()
rep = report()
steps = rep.steps
changed = dict(zip(steps["step"], steps["what_changed"])) if rep.ok else {}

page_header("Data & Method", "Where the numbers come from, how they were cleaned into one table, what every column "
            "means, what the data cannot tell you, and the table itself to inspect or download.",
            eyebrow="Reference", filters=f, show=("category", "years", "states", "institutions"))

# ---------- 1. pipeline diagram ----------
n_files = find_count(changed.get("1", ""), r"([\d,]+) CSV files")
raw_rows = int(steps["rows_after"].iloc[0]) if rep.ok else None
master_rows = len(master())
n_steps = len(steps) if rep.ok else 12


def num(v, suffix=""):
    return f"{v:,}{suffix}" if isinstance(v, int) else "–"


section_title("From NIRF pages to a chart in four layers", eyebrow="Pipeline",
              lead="Each box is one folder of the project; the numbers are from the last pipeline run.")
st.html(f"""
<div class="nirf-flow">
  <div class="nirf-flow-node src"><div class="tag">Source</div><div class="head">nirfindia.org</div>
    <div class="body">Official ranking pages, 2017–2025, every category</div></div>
  <div class="nirf-flow-arrow" aria-hidden="true"></div>
  <div class="nirf-flow-node"><div class="tag">1 · Data kitchen</div><div class="head">Scrape</div>
    <div class="body"><code>scraper/</code> saves every table untouched in <code>data/raw/</code></div>
    <div class="stat">{num(n_files)} CSV files · {num(raw_rows)} rows</div></div>
  <div class="nirf-flow-arrow" aria-hidden="true"></div>
  <div class="nirf-flow-node"><div class="tag">1 · Data kitchen</div><div class="head">Clean</div>
    <div class="body"><code>pipeline/</code> runs {n_steps} logged steps: names, states, categories, ranks, numbers</div>
    <div class="stat">{num(master_rows)} ranked rows kept</div></div>
  <div class="nirf-flow-arrow" aria-hidden="true"></div>
  <div class="nirf-flow-node key"><div class="tag">Single source of truth</div><div class="head">Master table</div>
    <div class="body"><code>nirf_master.parquet</code>: one row per year × category × institution</div>
    <div class="stat">{master()['institution_key'].nunique():,} institutions · {len(category_years_map())} categories</div></div>
  <div class="nirf-flow-arrow" aria-hidden="true"></div>
  <div class="nirf-flow-node"><div class="tag">2 · Brain</div><div class="head">8 engines</div>
    <div class="body"><code>core/engines/</code>: trends, geography, univariate, bivariate, multivariate,
      distribution, mobility, outliers</div>
    <div class="stat">chart + answer + method + data</div></div>
  <div class="nirf-flow-arrow" aria-hidden="true"></div>
  <div class="nirf-flow-node"><div class="tag">3 · Face  ·  4 · Translator</div><div class="head">Dashboard &amp; Ask NIRF</div>
    <div class="body"><code>app/</code> pages call the engines; <code>nlq/</code> turns a typed question into an
      engine call (the model never calculates)</div>
    <div class="stat">{len(QUESTION_REGISTRY)} questions · {len(PAGES)} pages</div></div>
</div>
""")

# ---------- 2. sources ----------
section_title("Sources", eyebrow="Where it comes from")
st.html("""
<div class="nirf-sources">
  <div class="nirf-source"><div class="head">NIRF rankings 2017–2025</div>
    <div class="body">National Institutional Ranking Framework, Ministry of Education, Government of India
      (<a href="https://www.nirfindia.org" target="_blank" rel="noopener">nirfindia.org</a>). All ranks, scores and
      parameter scores in the atlas come from these published tables; nothing is estimated.</div>
    <div class="use">Used for: every number and chart</div></div>
  <div class="nirf-source"><div class="head">Map of India (state boundaries)</div>
    <div class="body">Open-source GeoJSON from the datta07/INDIAN-SHAPEFILES repository (MIT licence), with
      Telangana and Ladakh as separate units. A visual aid, not an official map.</div>
    <div class="use">Used for: the choropleth map on the Geography page</div></div>
  <div class="nirf-source"><div class="head">Google Gemini API</div>
    <div class="body">Reads a typed question and returns a small JSON plan (which analysis, which filters).
      It never sees the data and never computes a number.</div>
    <div class="use">Used for: Ask NIRF only</div></div>
</div>
""")
st.caption("Full details, file hashes and licence text: docs/sources.md · scraping notes: docs/source_map.md.")

# ---------- 3. cleaning steps ----------
section_title("Cleaning, step by step", eyebrow="Rows before → after",
              lead=f"Read from docs/cleaning_report.md (generated {rep.generated})." if rep.generated else None)
if not rep.ok:
    empty_state("docs/cleaning_report.md was not found or could not be read.", title="Cleaning report missing",
                hint="Run  python -m pipeline.clean  to rebuild the master table and write the report.")
else:
    raw_names = find_count(changed.get("7", ""), r"([\d,]+) raw name spellings")
    insts = find_count(changed.get("7", ""), r"into ([\d,]+) institutions")
    raw_states = find_count(changed.get("5", ""), r"([\d,]+) raw spellings")
    states = find_count(changed.get("5", ""), r"-> ([\d,]+) official")
    dups = find_count(changed.get("11", ""), r"Exact duplicate rows dropped: ([\d,]+)")
    kpi_cards([
        ("Raw rows", num(raw_rows), f"from {num(n_files)} downloaded CSV files"),
        ("Ranked rows kept", num(master_rows), "participant lists set apart, not deleted"),
        ("Institutions", num(insts), f"from {num(raw_names)} name spellings"),
        ("States & UTs", num(states), f"from {num(raw_states)} spellings"),
        ("Duplicates dropped", num(dups), "every dropped row would be logged"),
    ])
    top = max(steps["rows_after"].max(), 1)
    rows_html = []
    for r in steps.itertuples():
        width = 100 * r.rows_after / top
        delta = (f"<span class='delta down'>−{abs(r.change):,}</span>" if r.change < 0 else
                 f"<span class='delta up'>+{r.change:,}</span>" if r.change > 0 else "<span class='delta same'>no rows lost</span>")
        rows_html.append(
            f"<tr><td class='num'>{esc(r.step)}</td><td class='what'>{esc(r.what)}</td>"
            f"<td class='num'>{r.rows_before:,}</td><td class='num'>{r.rows_after:,}</td><td>{delta}</td>"
            f"<td class='barcell'><div class='bar' style='width:{width:.1f}%'></div></td></tr>")
    st.html("<div class='nirf-steptable-wrap'><table class='nirf-steptable'><thead><tr><th>Step</th><th>What</th>"
            "<th class='num'>Rows before</th><th class='num'>Rows after</th><th>Change</th>"
            "<th>Rows after (bar)</th></tr></thead><tbody>" + "".join(rows_html) + "</tbody></table></div>")
    st.caption("Most steps change values, not the number of rows; what each one changed is listed below. Step 6b "
               "moves the participant lists (institutions that took part but were not ranked) into their own table.")
    labels = [f"Step {s} · {w}" for s, w in zip(steps["step"], steps["what"])]
    pick = st.selectbox("Show what a step changed and why", labels, index=7 if len(labels) > 7 else 0,
                        key="dm-step")
    row = steps.iloc[labels.index(pick)]
    st.html(f"<div class='nirf-callout'><div class='label'>What changed</div><div class='text'>{esc(row['what_changed'])}"
            f"</div><div class='label' style='margin-top:.6rem'>Why</div><div class='text'>{esc(row['why'])}</div></div>")

# ---------- 4. coverage ----------
section_title("Which categories exist in which years", eyebrow="Coverage",
              lead="NIRF added and renamed categories over time; each one is compared only in the years it exists.")
show("univariate", "coverage_by_category_year", key="dm-coverage")

# ---------- 5. data dictionary ----------
section_title("Data dictionary", eyebrow="Every column of the master table")
if rep.dictionary.empty:
    empty_state("The data dictionary is part of docs/cleaning_report.md, which could not be read.",
                title="Data dictionary missing", hint="Run  python -m pipeline.clean  to write it again.")
else:
    query = st.text_input("Search the columns", placeholder="e.g. rank, score, state", key="dm-dict-q",
                          label_visibility="collapsed")
    d = rep.dictionary
    if query:
        hit = d.apply(lambda r: query.lower() in " ".join(r).lower(), axis=1)
        d = d[hit]
    if d.empty:
        st.caption(f"No column mentions '{query}'.")
    else:
        # An HTML table (not st.dataframe) so long meanings wrap onto several lines instead of being cut off.
        body = "".join(f"<tr><td class='col'>{esc(r.column)}</td><td>{esc(r.meaning)}</td><td>{esc(r.type)}</td>"
                       f"<td class='ex'>{esc(r.example)}</td></tr>" for r in d.itertuples())
        st.html("<div class='nirf-steptable-wrap nirf-dict-wrap'><table class='nirf-steptable nirf-dict'><thead><tr>"
                "<th>Column</th><th>Meaning</th><th>Type</th><th>Example (IIT Madras, Overall 2025)</th></tr></thead>"
                f"<tbody>{body}</tbody></table></div>")
        st.caption(f"{len(d)} of {len(rep.dictionary)} columns · the same dictionary is in docs/cleaning_report.md.")

# ---------- 6. limitations ----------
lim = limitation_counts()
section_title("Limitations: read every chart with these in mind", eyebrow="What the data cannot tell you")
st.html(f"""
<div class="nirf-limits">
  <div class="nirf-limit"><div class="num">01</div><div class="head">Banded ranks have no score</div>
    <div class="body">{lim['banded']:,} of {lim['rows']:,} rows ({lim['banded_pct']:.0f}%) are published only as a rank
      band such as 101-150, with no exact rank and no score. They count in "how many in the top 200" questions but
      are left out of every average, correlation and score chart; we never invent a mid-point. Another
      {lim['no_score_exact']:,} rows have an exact rank but no score, mostly the rank-only lists
      ({', '.join(lim['rank_only'])}).</div></div>
  <div class="nirf-limit"><div class="num">02</div><div class="head">Scores are not comparable across categories</div>
    <div class="body">Each category has its own parameter weights (and Research Institutions use QNR, QLR and SFC
      instead of TLR, RPC and GO), so a 60 in Engineering and a 60 in Pharmacy do not mean the same thing.
      Charts that put several categories side by side carry a visible note; compare shapes, not levels.</div></div>
  <div class="nirf-limit"><div class="num">03</div><div class="head">The NIRF method changed over the years</div>
    <div class="body">NIRF grew from {lim['first_n']} lists in {lim['first_year']} to {lim['last_n']} in
      {lim['last_year']}, renamed some (Research → Research Institutions, Architecture → Architecture and
      Planning), changed which positions get exact ranks (we see {lim['n_band_labels']} different band labels) and
      revises its parameter definitions between editions. A score change from one year to the next can partly come
      from the method, not only from the institution.</div></div>
  <div class="nirf-limit"><div class="num">04</div><div class="head">Ranks are relative, and lists change</div>
    <div class="body">A rank says where an institution stands among those that took part that year. Institutions
      join, leave or are withdrawn, so "moved up" can mean others fell out. Mobility charts count only institutions
      ranked in both years and say how many dropped out or were newly listed.</div></div>
</div>
""")

# ---------- 7. the table ----------
section_title("The master table for your selection", eyebrow="Data",
              lead="Filtered by the sidebar (category, years, states, institutions).")
rows = f.rows()
if rows.empty:
    empty_state("No rows match the sidebar filters.", title="Nothing to show for this selection")
else:
    st.dataframe(rows.drop(columns=["source_url"], errors="ignore"), hide_index=True, width="stretch", height=420)
    st.download_button(f"Download these {len(rows):,} rows (CSV)", rows.to_csv(index=False).encode("utf-8"),
                       file_name="nirf_atlas_selection.csv", mime="text/csv", icon=":material/download:")
