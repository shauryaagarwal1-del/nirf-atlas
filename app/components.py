"""Shared UI building blocks for every page: header, chart card, empty state, KPI cards, links.

Pages stay short because they only choose WHAT to show; this module decides HOW it looks:
  * page_header()  the title block at the top of each page, with the active global filters as chips;
  * chart_card()   one ChartResult as a card: the chart, the insight in a highlighted callout,
                   "How we calculated this" (the method) and "See the data" (table + CSV download);
  * show()         runs an engine function (cached, optionally for chosen states only) and draws its
                   chart card, or a friendly empty state when the filters give no rows or the engine
                   explains why it cannot answer;
  * kpi_cards(), empty_state(), section_title(), nav_cards() for the home and reference pages.
The look itself is in assets/style.css (+ style-dark.css) and the chart template in core/theme.py.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import pandas as pd
import streamlit as st

from core.data import NirfInputError, SHORT
from core.result import ChartResult
from core.runner import run
from core.theme import dark_variant, for_theme, with_surface

ASSETS = Path(__file__).resolve().parents[1] / "assets"

PLOTLY_CONFIG = {
    "displaylogo": False,
    "scrollZoom": False,          # the mouse wheel scrolls the page, never zooms a map (use the +/- buttons)
    "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
    "toImageButtonOptions": {"format": "png", "scale": 2, "filename": "nirf_atlas_chart"},
}


# ---------- theme ----------

def is_dark() -> bool:
    """True when the viewer is using the dark theme (Settings menu, or the system setting)."""
    try:
        return st.context.theme.type == "dark"
    except Exception:  # older Streamlit or no browser context (tests)
        return False


def inject_css() -> None:
    """Add the atlas stylesheet (and the dark-mode tokens when needed). Called once per run by app/Home.py."""
    css = (ASSETS / "style.css").read_text(encoding="utf-8")
    if is_dark():
        css += "\n" + (ASSETS / "style-dark.css").read_text(encoding="utf-8")
    st.html(f"<style>{css}</style>")


def _esc(text) -> str:
    return html.escape(str(text))


def _md_inline(text: str) -> str:
    """Escape text for HTML but keep **bold** from engine insights."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", _esc(text))


# ---------- headers ----------

def filter_chips(f, show: tuple[str, ...] = ("category", "years", "states", "institutions", "top_n")) -> str:
    chips = []
    if "category" in show:
        chips.append(f"<span class='nirf-chip'><span class='dot'></span><b>{_esc(f.category)}</b></span>")
    if "years" in show:
        chips.append(f"<span class='nirf-chip'>Years <b>{_esc(f.span)}</b></span>")
    if "states" in show:
        label = ", ".join(f.states[:3]) + (f" +{len(f.states) - 3}" if len(f.states) > 3 else "") if f.states \
            else "All states"
        chips.append(f"<span class='nirf-chip'>States <b>{_esc(label)}</b></span>")
    if "institutions" in show and f.institutions:
        names = f.institution_labels()
        label = ", ".join(names[:2]) + (f" +{len(names) - 2}" if len(names) > 2 else "")
        chips.append(f"<span class='nirf-chip'>Institutions <b>{_esc(label)}</b></span>")
    if "top_n" in show:
        chips.append(f"<span class='nirf-chip'>Top <b>{f.top_n}</b></span>")
    return "<div class='nirf-chips'>" + "".join(chips) + "</div>"


def page_header(title: str, subtitle: str, eyebrow: str | None = None, filters=None,
                show: tuple[str, ...] = ("category", "years", "states", "institutions", "top_n")) -> None:
    """The title block at the top of a page; with `filters`, the active global filters appear as chips."""
    eb = f"<div class='nirf-eyebrow'>{_esc(eyebrow)}</div>" if eyebrow else ""
    chips = filter_chips(filters, show) if filters is not None else ""
    st.html(f"<div class='nirf-page-header'>{eb}<div class='nirf-title'>{_esc(title)}</div>"
            f"<div class='nirf-subtitle'>{_esc(subtitle)}</div>{chips}</div>")


def section_title(title: str, eyebrow: str | None = None, lead: str | None = None) -> None:
    eb = f"<div class='nirf-eyebrow'>{_esc(eyebrow)}</div>" if eyebrow else ""
    ld = f"<div class='nirf-lead'>{_esc(lead)}</div>" if lead else ""
    st.html(f"<div class='nirf-section-title'>{eb}<div class='nirf-h2'>{_esc(title)}</div>{ld}</div>")


# ---------- empty state ----------

def empty_state(message: str, title: str = "Nothing to show for this selection",
                hint: str = "Try a wider year range, another category, or clear the state and institution filters.",
                icon: str = "?") -> None:
    """A friendly card instead of a blank space or an error: what happened, and what to try next."""
    st.html(f"<div class='nirf-empty'><div class='icon'>{_esc(icon)}</div><div class='title'>{_esc(title)}</div>"
            f"<div class='msg'>{_esc(message)}</div><div class='hint'>{_esc(hint)}</div></div>")


# ---------- running engines ----------

@st.cache_data(show_spinner=False, max_entries=512)
def run_engine(engine: str, function: str, params: dict, states: tuple[str, ...] | None = None,
               types: tuple[str, ...] | None = None) -> tuple[ChartResult | None, str | None]:
    """Call core.engines.<engine>.<function>(**params), cached per parameter set (core/runner.py).

    states: only institutions in these states are analysed; types: only these institute types (IIT, NIT ...).
    Returns (result, None), or (None, message) when the engine explains that the selection cannot be
    answered (NirfInputError); the message is written for the dashboard user.
    """
    try:
        return run(engine, function, params, states=list(states) if states else None,
                   types=list(types) if types else None), None
    except NirfInputError as e:
        return None, str(e)


def _csv(table: pd.DataFrame) -> bytes:
    return table.to_csv(index=False).encode("utf-8")


def chart_card(result: ChartResult, key: str, why: str | None = None) -> None:
    """One answer as a card: chart, insight callout, method and data expanders.

    `key` must be unique on the page. `why` is an optional "why this chart" note shown under the chart.
    """
    with st.container(border=True, key=f"card-{key}"):
        if result.table is None or result.table.empty:
            empty_state("The filters left no rows for this chart.")
            return
        fig = with_surface(result.fig)
        fig = dark_variant(fig) if is_dark() else fig
        st.plotly_chart(fig, width="stretch", theme=None, config=PLOTLY_CONFIG, key=f"chart-{key}")
        st.html(f"<div class='nirf-callout'><div class='label'>The answer</div>"
                f"<div class='text'>{_md_inline(result.insight)}</div></div>")
        meta = f"<span class='nirf-badge'>{_esc(result.chart_type)}</span>"
        if why:
            meta += f"<span class='nirf-why'>{_esc(why)}</span>"
        st.html(f"<div class='nirf-cardmeta'>{meta}</div>")
        with st.expander("How we calculated this", icon=":material/functions:"):
            st.markdown(result.method)
        with st.expander("See the data", icon=":material/table_view:"):
            st.dataframe(_display_table(result.table), hide_index=True, width="stretch")
            st.download_button("Download CSV", _csv(result.table), file_name=f"nirf_atlas_{key}.csv",
                               mime="text/csv", icon=":material/download:", key=f"dl-{key}")


def _display_table(table: pd.DataFrame) -> pd.DataFrame:
    """Friendlier column headers for the on-screen table (the CSV keeps the original names)."""
    names = {c: SHORT.get(c, str(c).replace("_", " ").capitalize()) for c in table.columns}
    return table.rename(columns=names)


def show(engine: str, function: str, key: str, why: str | None = None, scope=None, types=None,
         **params) -> ChartResult | None:
    """Run an engine function with these parameters and draw its chart card (or a friendly empty state).

    scope: limit the analysis to institutions in these states (None = all of India).
    types: limit it to these institute types, e.g. ("IIT",) (None = every institution).
    """
    try:
        with st.spinner("Drawing the chart…"):
            result, error = run_engine(engine, function, params, tuple(scope) if scope else None,
                                       tuple(types) if types else None)
    except Exception as e:  # an unexpected bug must not break the whole page during a demo
        with st.container(border=True, key=f"card-{key}"):
            empty_state("Something went wrong while drawing this chart. The rest of the page still works.",
                        title="This chart could not be drawn",
                        hint="Try another setting, or press Reset filters in the sidebar.", icon="!")
            with st.expander("Technical details"):
                st.code(f"{engine}.{function}({params})\n{type(e).__name__}: {e}", language=None)
        return None
    if error:
        with st.container(border=True, key=f"card-{key}"):
            empty_state(error, title="This selection has no answer")
        return None
    chart_card(result, key, why)
    return result


# ---------- home & reference blocks ----------

def kpi_cards(items: list[tuple[str, str, str]], accents: list[str] | None = None) -> None:
    """A row of KPI cards: (label, value, footnote). `accents`: one colour per card for its top bar
    (e.g. the colour of that state's line in the chart below), switched to its dark step in dark mode."""
    opens = ([f"<div class='nirf-kpi accent' style='--accent:{for_theme(a, is_dark())}'>" for a in accents]
             if accents else ["<div class='nirf-kpi'>"] * len(items))
    cards = "".join(f"{o}<div class='label'>{_esc(l)}</div><div class='value'>{_esc(v)}</div>"
                    f"<div class='foot'>{_esc(n)}</div></div>" for (l, v, n), o in zip(items, opens))
    st.html(f"<div class='nirf-kpis'>{cards}</div>")


def nav_cards(pages, columns: int = 3) -> None:
    """A grid of cards, one per page, each linking to it."""
    cols = st.columns(columns, gap="medium")
    for i, p in enumerate(pages):
        with cols[i % columns]:
            with st.container(border=True, key=f"navcard-{i}"):
                st.page_link(p.path, label=p.title, icon=p.icon)
                st.html(f"<div class='nirf-navdesc'>{_esc(p.description)}</div>")


def year_select(f, label: str = "Year", key: str = "year", years: list[int] | None = None) -> int:
    """A single-year picker for one-year charts, offering the years in the global range (default: the last)."""
    options = years or f.years or [f.end]
    # The key includes the options, so a changed category or year range starts again from its last year.
    return st.selectbox(label, options, index=len(options) - 1, key=f"{key}-{f.category}-{options[0]}-{options[-1]}")
