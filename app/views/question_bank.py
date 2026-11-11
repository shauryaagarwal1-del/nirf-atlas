"""Question Bank (Level 1): the 40 Annexure A questions (Q1.1-Q8.5), each answered live with its registered engine call.

How the page works:
  * the 8 sections are tabs; each lists its 5 questions (from core/questions.py) with their IDs;
  * picking a question draws its chart card with the registered default parameters, and the controls
    for THAT question's parameters sit right above the chart, so a changed year, category, institution
    or parameter (a Level 2 question) is answered on the spot;
  * "Run all 40" runs every question with its defaults and shows a grid with a tick and a mini preview each;
  * deep links: ?q=Q4.3 in the address opens that question directly, and the address always shows the
    open question so it can be copied and shared.
Only the open tab is computed (lazy tabs), and engine results are cached, so switching is fast.
"""

from __future__ import annotations

import html
import time

import plotly.graph_objects as go
import streamlit as st

from app.components import is_dark, page_header, run_engine, show
from app.question_controls import default_params, question_controls, reset_question
from core.questions import QUESTION_REGISTRY, SECTIONS, Question, check_result
from core.theme import themed

TAB_NAMES = {1: "Trends", 2: "Geospatial", 3: "Univariate", 4: "Bivariate", 5: "Multivariate",
             6: "Distribution", 7: "Mobility", 8: "Outliers"}
TAB_LABELS = {s: f"{s} · {name}" for s, name in TAB_NAMES.items()}
LABEL_TO_SECTION = {v: k for k, v in TAB_LABELS.items()}
FIRST_QUESTION = "Q1.1"
MINI_CONFIG = {"staticPlot": True, "displayModeBar": False}


def _section(qid: str) -> int:
    return int(qid[1])


def _questions(section: int) -> list[str]:
    return [qid for qid in QUESTION_REGISTRY if _section(qid) == section]


# ---------- state: the open question, its tab, the deep link ----------

def _open(qid: str) -> None:
    """Make `qid` the open question: select its tab, remember it for that tab, leave the run-all grid."""
    st.session_state["qb_q"] = qid
    st.session_state["qb-tab"] = TAB_LABELS[_section(qid)]
    st.session_state.setdefault("qb_last", {})[_section(qid)] = qid
    st.session_state["qb_mode"] = "questions"


def _init_state() -> None:
    if "qb_q" not in st.session_state:
        _open(FIRST_QUESTION)
    # A ?q= link opens its question once (later reruns keep whatever the user picks next).
    link = st.query_params.get("q")
    if link and link != st.session_state.get("qb_link"):
        st.session_state["qb_link"] = link
        qid = link.strip().upper().replace(" ", "")
        if qid in QUESTION_REGISTRY:
            _open(qid)
        else:
            st.toast(f"There is no question '{link}'. IDs run from Q1.1 to Q8.5.", icon=":material/error:")


def _on_tab() -> None:
    section = LABEL_TO_SECTION[st.session_state["qb-tab"]]
    st.session_state["qb_q"] = st.session_state["qb_last"].get(section, _questions(section)[0])


def _on_pick(section: int) -> None:
    qid = st.session_state[f"qb-pick-{section}"]
    st.session_state["qb_q"] = qid
    st.session_state["qb_last"][section] = qid


def _sync_link(qid: str) -> None:
    """Keep ?q= in the address equal to the open question, so the link can be copied."""
    st.session_state["qb_link"] = qid
    if st.query_params.get("q") != qid:
        st.query_params["q"] = qid


# ---------- one question ----------

def _esc(text) -> str:
    return html.escape(str(text))


def question_header(q: Question) -> None:
    st.html(f"<div class='nirf-q-head'><div class='nirf-q-top'><span class='nirf-q-id'>{q.id}</span>"
            f"<span class='nirf-q-section'>{_esc(q.section)}</span></div>"
            f"<div class='nirf-q-text'>{_esc(q.text)}</div>"
            f"<div class='nirf-q-why'><b>Why this chart?</b> {_esc(q.why_this_chart)}</div></div>")


def render_question(q: Question) -> None:
    question_header(q)
    with st.container(border=True, key=f"qb-controls-{q.id}"):
        params = question_controls(q)
        changed = params != default_params(q)
        left, right = st.columns([5, 1], vertical_alignment="center")
        with left:
            note = ("Changed from the default: the chart below answers your new question."
                    if changed else "Default settings from the question registry. Change any control to ask a "
                                    "new version of this question.")
            st.caption(note)
        with right:
            st.button("Reset", key=f"qb-reset-{q.id}", on_click=reset_question, args=(q.id,),
                      icon=":material/restart_alt:", width="stretch", disabled=not changed)
    show(q.engine, q.function, key=f"qb-{q.id}", **params)


def render_section(section: int, open_qid: str) -> None:
    ids = _questions(section)
    st.session_state[f"qb-pick-{section}"] = open_qid
    st.radio(SECTIONS[section], ids, key=f"qb-pick-{section}", on_change=_on_pick, args=(section,),
             format_func=lambda qid: f"{qid} · {QUESTION_REGISTRY[qid].text}")
    render_question(QUESTION_REGISTRY[open_qid])


# ---------- run all 40 ----------

def run_all() -> list[dict]:
    """Run every question with its default parameters and check each answer (same checks as the test script)."""
    rows = []
    bar = st.progress(0.0, text="Running the 40 questions…")
    for i, (qid, q) in enumerate(QUESTION_REGISTRY.items(), start=1):
        start = time.perf_counter()
        try:
            result, error = run_engine(q.engine, q.function, q.default_params)
            problems = [error] if error else check_result(result, q)
        except Exception as exc:                       # one failure must not hide the others
            result, problems = None, [f"{type(exc).__name__}: {exc}"]
        rows.append(dict(id=qid, q=q, result=result, problems=problems, seconds=time.perf_counter() - start))
        bar.progress(i / len(QUESTION_REGISTRY), text=f"Ran {qid}")
    bar.empty()
    return rows


def mini_figure(fig: go.Figure) -> go.Figure:
    """A thumbnail of a chart: same marks and colours, no titles, axes, legends, labels or notes."""
    mini = go.Figure(themed(fig, is_dark()))
    mini.update_layout(height=150, margin=dict(l=4, r=4, t=4, b=4), showlegend=False, title=None,
                       annotations=[], hovermode=False)
    mini.update_xaxes(visible=False)
    mini.update_yaxes(visible=False)
    if "coloraxis" in mini.layout:
        mini.layout.coloraxis.showscale = False
    for trace in mini.data:
        for prop, value in (("showscale", False), ("texttemplate", None), ("text", None)):
            if prop in trace:
                trace[prop] = value
        if "mode" in trace and trace.mode and "text" in trace.mode:
            trace.mode = trace.mode.replace("+text", "").replace("text+", "") or "markers"
    return mini


def render_grid() -> None:
    rows = run_all()
    passed = sum(not r["problems"] for r in rows)
    total = sum(r["seconds"] for r in rows)
    tone = "ok" if passed == len(rows) else "bad"
    st.html(f"<div class='nirf-runall-summary {tone}'><b>{passed} / {len(rows)}</b> questions answered with a "
            f"complete chart · {total:.1f} s (repeat runs are cached). Each tile shows the default answer; "
            f"open it to see the full chart and change its settings.</div>")
    for section in SECTIONS:
        st.html(f"<div class='nirf-grid-section'>{section} · {_esc(SECTIONS[section])}</div>")
        cols = st.columns(5, gap="small")
        for col, r in zip(cols, [r for r in rows if _section(r["id"]) == section]):
            with col, st.container(border=True, key=f"qb-tile-{r['id']}"):
                ok = not r["problems"]
                st.html(f"<div class='nirf-tile-head'><span class='nirf-tick {'ok' if ok else 'bad'}'>"
                        f"{'✓' if ok else '✗'}</span><b>{r['id']}</b>"
                        f"<span class='nirf-tile-time'>{r['seconds']:.1f} s</span></div>"
                        f"<div class='nirf-tile-text'>{_esc(r['q'].text)}</div>")
                if r["result"] is not None and r["result"].fig.data:
                    st.plotly_chart(mini_figure(r["result"].fig), width="stretch", theme=None, config=MINI_CONFIG,
                                    key=f"mini-{r['id']}")
                if not ok:
                    st.caption("; ".join(r["problems"]))
                st.button("Open", key=f"qb-open-{r['id']}", on_click=_open, args=(r["id"],), width="stretch",
                          icon=":material/open_in_full:")


# ---------- page ----------

_init_state()
page_header("Question Bank", "The 40 sample questions from the project statement, eight sections of five. Pick a "
            "question to see its chart, the one-line answer, the method and the data; the controls above each "
            "chart change its parameters live.", eyebrow="Level 1 · Annexure A")

grid = st.session_state.get("qb_mode") == "grid"
tip, action = st.columns([4, 1], vertical_alignment="center")
with tip:
    st.caption("Each question has its own controls above its chart (the sidebar filters are for the Explore "
               "pages). Direct link to any question: add **?q=Q4.3** to this page's address.")
with action:
    if grid:
        st.button("Back to the questions", key="qb-back", width="stretch", icon=":material/arrow_back:",
                  on_click=lambda: st.session_state.update(qb_mode="questions"))
    else:
        st.button("Run all 40", key="qb-runall", type="primary", width="stretch", icon=":material/done_all:",
                  on_click=lambda: st.session_state.update(qb_mode="grid"))

if grid:
    render_grid()
else:
    qid = st.session_state["qb_q"]
    _sync_link(qid)
    tabs = st.tabs(list(TAB_LABELS.values()), key="qb-tab", on_change=_on_tab)
    for section, tab in zip(TAB_LABELS, tabs):
        if tab.open:
            with tab:
                render_section(section, qid)
