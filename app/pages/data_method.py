"""Data & Method: where the data comes from, how it was cleaned, coverage, and the filtered table to download."""

import streamlit as st

from app.components import page_header, section_title, show
from app.filters import current

f = current()
page_header("Data & Method", "Where the numbers come from, how they were cleaned into one table, and the table "
            "itself, filtered by the sidebar, to inspect or download.", eyebrow="Reference", filters=f,
            show=("category", "years", "states", "institutions"))

section_title("From NIRF pages to one master table", eyebrow="Pipeline")
st.html("""
<div class="nirf-pipeline">
  <div class="nirf-pipe"><div class="num">01 · SCRAPE</div><div class="head">Download</div>
    <div class="body">Every NIRF ranking page 2017–2025, all categories, saved untouched in <code>data/raw/</code>.</div></div>
  <div class="nirf-pipe"><div class="num">02 · AUDIT</div><div class="head">Inspect</div>
    <div class="body">Columns, rank bands, missing values and name variants are listed before any change.</div></div>
  <div class="nirf-pipe"><div class="num">03 · CLEAN</div><div class="head">Standardise</div>
    <div class="body">One spelling per institution, state and category; numbers typed; duplicates logged and removed.</div></div>
  <div class="nirf-pipe"><div class="num">04 · VALIDATE</div><div class="head">Check</div>
    <div class="body">Tests compare the master table with the raw pages, so every chart starts from checked data.</div></div>
</div>
""")

section_title("Which categories exist in which years", eyebrow="Coverage")
show("univariate", "coverage_by_category_year", key="dm-coverage")

section_title("The master table for your selection", eyebrow="Data")
rows = f.rows()
st.dataframe(rows.drop(columns=["source_url"], errors="ignore"), hide_index=True, width="stretch", height=420)
st.download_button("Download these rows (CSV)", rows.to_csv(index=False).encode("utf-8"),
                   file_name="nirf_atlas_selection.csv", mime="text/csv", icon=":material/download:")
