"""Home: what NIRF Atlas is, the key numbers of the dataset, one overview chart and links to every page."""

import streamlit as st

from app.components import kpi_cards, nav_cards, section_title, show
from app.filters import category_years_map, current, master
from app.nav import PAGES

ORBIT = """
<svg class="orbit" viewBox="0 0 440 440" fill="none" xmlns="http://www.w3.org/2000/svg">
  <circle cx="220" cy="220" r="120" stroke="rgba(246,199,102,0.55)" stroke-width="1.4"/>
  <circle cx="220" cy="220" r="170" stroke="rgba(255,255,255,0.10)" stroke-width="1"/>
  <circle cx="220" cy="220" r="212" stroke="rgba(255,255,255,0.06)" stroke-width="1" stroke-dasharray="2 6"/>
  <ellipse cx="220" cy="220" rx="196" ry="70" transform="rotate(-24 220 220)" stroke="rgba(47,194,174,0.6)" stroke-width="1.4"/>
  <ellipse cx="220" cy="220" rx="120" ry="44" stroke="rgba(246,199,102,0.25)" stroke-width="1"/>
  <path d="M220 100c40 34 40 206 0 240M220 100c-40 34-40 206 0 240" stroke="rgba(246,199,102,0.22)" stroke-width="1"/>
  <circle cx="384" cy="146" r="6" fill="#f6c766"/>
  <circle cx="384" cy="146" r="14" stroke="rgba(246,199,102,0.35)"/>
  <circle cx="62" cy="300" r="4" fill="#2fc2ae"/>
  <circle cx="300" cy="110" r="2.5" fill="#ffffff" opacity="0.8"/>
  <circle cx="150" cy="330" r="2" fill="#ffffff" opacity="0.6"/>
</svg>
"""

f = current()
df = master()
cats = category_years_map()
years = sorted(df["year"].unique())

st.html(f"""
<div class="nirf-hero">{ORBIT}
  <div class="content">
    <div class="nirf-eyebrow">National Institutional Ranking Framework · {years[0]}–{years[-1]}</div>
    <div class="title">NIRF <em>Atlas</em></div>
    <div class="purpose">Nine years of India's official university rankings, cleaned into one table, so any
      question about who ranks where, and why, becomes a chart in a few clicks.</div>
    <div class="meta"><span>{len(cats)} categories</span><span>5 parameters · TLR RPC GO OI PR</span>
      <span>Ministry of Education data</span></div>
  </div>
</div>
""")

first_lists = sum(1 for ys in cats.values() if ys[0] == years[0])
last_lists = sum(1 for ys in cats.values() if years[-1] in ys)
kpi_cards([
    ("Years covered", f"{len(years)}", f"{years[0]} to {years[-1]}"),
    ("Categories", f"{len(cats)}", f"{first_lists} lists in {years[0]} → {last_lists} in {years[-1]}"),
    ("Unique institutions", f"{df['institution_key'].nunique():,}", "after name standardisation"),
    ("States & UTs", f"{df['state'].nunique()}", "where ranked institutions are"),
    ("Total rows", f"{len(df):,}", "year × category × institution"),
])

n = max(2, min(f.top_n, 20))
section_title(f"The {f.category} top {n}, year by year", eyebrow="Overview",
              lead="Today's leaders followed back in time. Change the category, years or top N in the sidebar.")
show("trends", "top_n_race", key="home-race", category=f.category, years=f.years, n=n)

section_title("How to use the atlas", eyebrow="Three steps")
st.html("""
<div class="nirf-steps">
  <div class="nirf-step"><div class="num">01</div><div class="head">Set the filters</div>
    <div class="body">Choose a category, year range, states, institutions and top N in the sidebar. They follow
    you to every page.</div></div>
  <div class="nirf-step"><div class="num">02</div><div class="head">Pick a question or a topic</div>
    <div class="body">Start from the 40 questions in the Question Bank, or open a topic page such as Trends or
    Mobility and choose what you want to see.</div></div>
  <div class="nirf-step"><div class="num">03</div><div class="head">Read the answer, check the method</div>
    <div class="body">Every chart comes with a one-line answer, a plain-words explanation of how it was
    calculated, and the data behind it to download.</div></div>
</div>
""")

section_title("Explore the atlas", eyebrow="Every page")
nav_cards([p for p in PAGES if p.title != "Home"])
