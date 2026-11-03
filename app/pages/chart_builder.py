"""Chart Builder: pick variables and an allowed chart type to answer a question no page covers yet.

The builder itself is still being made; until then this page points to the pages that already answer
new questions by changing their filters.
"""

import streamlit as st

from app.components import empty_state, page_header

page_header("Chart Builder", "Choose filters, an X and a Y variable, a colour, an aggregation (count, mean, "
            "median, min, max) and a chart type from the course list, and get a chart.",
            eyebrow="Build & ask · Coming next")

with st.container(border=True, key="card-builder-soon"):
    empty_state("The Chart Builder is being built. Every topic page already answers new questions: change the "
                "category, years, states, institutions or top N in the sidebar, then pick what you want to see.",
                title="Coming soon", hint="Try Relationships for any two numbers, or Distributions for spreads.")
c1, c2, _ = st.columns([1, 1, 2])
c1.page_link("pages/relationships.py", label="Open Relationships", icon=":material/scatter_plot:")
c2.page_link("pages/distributions.py", label="Open Distributions", icon=":material/bar_chart:")
