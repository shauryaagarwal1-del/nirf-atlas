"""The list of dashboard pages: file, title, icon, sidebar section and a one-line description.

One place for the page catalogue, so the sidebar navigation (app/Home.py) and the cards on the
home page always show the same pages in the same order.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PageInfo:
    path: str          # relative to app/ (the folder of the entry point)
    title: str
    icon: str          # Material icon shown in the sidebar and on the home cards
    section: str       # sidebar group
    description: str   # shown on the home page card


PAGES = [
    PageInfo("pages/home.py", "Home", ":material/home:", "",
             "Overview, key numbers and how to use the atlas."),
    PageInfo("pages/question_bank.py", "Question Bank", ":material/quiz:", "",
             "The 40 Annexure A questions, one click each."),
    PageInfo("pages/trends.py", "Trends", ":material/show_chart:", "Explore",
             "How ranks and scores moved from 2017 to 2025: climbers, fallers and steady leaders."),
    PageInfo("pages/geography.py", "Geography", ":material/public:", "Explore",
             "Which states hold the top places, and how that map is changing."),
    PageInfo("pages/distributions.py", "Distributions", ":material/bar_chart:", "Explore",
             "The shape and spread of scores: histograms, quartiles, box and violin plots."),
    PageInfo("pages/relationships.py", "Relationships", ":material/scatter_plot:", "Explore",
             "How two NIRF numbers move together: scatterplots and correlations."),
    PageInfo("pages/multi_parameter.py", "Multi-Parameter", ":material/stacked_bar_chart:", "Explore",
             "All five parameters at once: profiles, gaps and strongest-vs-weakest."),
    PageInfo("pages/mobility.py", "Mobility", ":material/swap_vert:", "Explore",
             "Movement between rank bands, top-10 entries and exits, up/down/same counts."),
    PageInfo("pages/outliers.py", "Outliers", ":material/radar:", "Explore",
             "Institutions that break the pattern: unusual scores, jumps and volatility."),
    PageInfo("pages/chart_builder.py", "Chart Builder", ":material/construction:", "Build & ask",
             "Pick any variables and an allowed chart type to answer a new question."),
    PageInfo("pages/ask_nirf.py", "Ask NIRF (AI)", ":material/forum:", "Build & ask",
             "Type a question in plain English and get the chart that answers it."),
    PageInfo("pages/data_method.py", "Data & Method", ":material/menu_book:", "Reference",
             "Where the data comes from, how it was cleaned, and the full table to download."),
]
