"""Ask NIRF (AI): type a question in plain English and get the chart that answers it.

The language model (Gemini API) will only turn the question into a small JSON plan
{engine, function, params}; our own code checks the plan and runs the engine, so every number
still comes from the cleaned data. The chat is still being connected; until then this page
explains how it will work and links to the Question Bank.
"""

import streamlit as st

from app.components import empty_state, page_header

page_header("Ask NIRF", "Type a question such as \"How did IIT Madras's rank change since 2017?\" and get the "
            "chart, the answer and the method. The Gemini API reads the question; our engines do every calculation.",
            eyebrow="Build & ask · Natural language")

with st.container(border=True, key="card-ask-soon"):
    empty_state("The chat is being connected. It will translate a question into a plan (which analysis, with which "
                "category, years, states and institutions), check that plan against the data, and draw the chart "
                "with the same engines as the rest of the atlas.",
                title="Coming soon", hint="Meanwhile, the Question Bank answers the 40 sample questions.")
c1, _ = st.columns([1, 3])
c1.page_link("pages/question_bank.py", label="Open the Question Bank", icon=":material/quiz:")
