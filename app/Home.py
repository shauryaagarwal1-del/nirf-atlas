"""NIRF Atlas: the Streamlit entry point. Run with:  streamlit run app/Home.py

Every page visit runs this file first: it sets up the page, injects the stylesheet once, builds the
sidebar navigation (grouped, with icons) and draws the global filters, then runs the chosen page
from app/pages/. The page catalogue itself is in app/nav.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app.components import inject_css  # noqa: E402
from app.filters import render_sidebar  # noqa: E402
from app.nav import PAGES  # noqa: E402

st.set_page_config(page_title="NIRF Atlas", page_icon=str(ROOT / "assets" / "mark.svg"), layout="wide",
                   initial_sidebar_state="expanded")
inject_css()
st.logo(str(ROOT / "assets" / "logo.svg"), icon_image=str(ROOT / "assets" / "mark.svg"), size="large")

sections: dict[str, list] = {}
for p in PAGES:
    sections.setdefault(p.section, []).append(st.Page(p.path, title=p.title, icon=p.icon, default=p.title == "Home"))
page = st.navigation(sections, position="sidebar")

render_sidebar()
page.run()
