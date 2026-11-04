"""Ask NIRF (Level 3): type a question in plain English (or Hinglish) and get the chart that answers it.

How a question is answered (code in nlq/):
  1. the Gemini model reads the question and the catalog of our analyses and writes ONLY a small JSON
     plan: which analysis, with which category, years, states, institutions and parameters
     (nlq/planner.py, checked with pydantic; one retry if the JSON is invalid);
  2. our code translates the names ("iitb", "TN", "research", "last 3 years"), checks the plan and runs
     it with the same engines as the rest of the atlas (nlq/resolve.py, nlq/executor.py);
  3. the page shows the chart card with its one-line answer, an "Assumed:" box right under it (every
     assumption as a plain sentence, e.g. "There's no IIT Bangalore in the NIRF rankings, so I assumed you
     meant IIIT Bangalore ..."), one-click "Use IISc instead" buttons for the other institutions the person
     may have meant (they re-run the same plan, without the model), "How I understood your question" (the
     assumptions again + the plan JSON) and three follow-up questions as buttons. An institution that took
     part in NIRF but was never ranked gets a clear message and buttons for similar ranked institutions.
The model never sees the data and never calculates a number. If the model cannot be reached (no
internet, wrong key, quota), the page says what went wrong and how to fix it, and offers the closest
sample question, which runs without the model. The sidebar shows whether the Gemini key works.
"""

from __future__ import annotations

import html
import json

import streamlit as st

from app.components import chart_card, page_header, run_engine
from core.data import NirfInputError
from nlq import llm
from nlq.catalog import closest_questions, page_for
from nlq.executor import Answer, execute, registry_plan, with_institution
from nlq.planner import PLAN, PlanError, plan_question

HISTORY = "ask_history"     # list of turns: {"question": str, "answer": Answer | None, "error": dict | None}
PENDING = "ask_pending"     # the next question: {"question": str}, {"qid": "Q1.1"} or {"question", "plan"}
EXAMPLES = [
    "How has IIT Bombay's rank changed since 2017?",
    "Which states have the most top-100 institutions in 2025?",
    "Karnataka vs TN engineering colleges",
    "Kaun se institutes hamesha top 10 mein rahe?",
    "Does research score drive the overall score?",
    "Which pharmacy colleges climbed the most in the last 3 years?",
]
ERROR_TITLES = {"no_key": "No Gemini API key", "offline": "No internet connection",
                "invalid_key": "The Gemini key was rejected", "quota": "Gemini quota used up for now",
                "model": "Unknown Gemini model", "server": "Gemini had a problem", "plan": "I could not read that",
                "unknown": "The question could not be sent"}


def _esc(text) -> str:
    return html.escape(str(text))


# ---------- the model call and the analysis (both cached) ----------

@st.cache_data(show_spinner=False, max_entries=256)
def _plan(question: str, history_json: str) -> dict:
    """The checked plan for a question (cached: the same question in the same context is not re-sent)."""
    return plan_question(question, json.loads(history_json)).model_dump()


@st.cache_data(show_spinner=False, ttl=300)
def _status() -> tuple[bool, str]:
    try:
        return llm.check_connection()
    except Exception:
        return False, "Status check failed."


def _run(engine: str, function: str, params: dict, states):
    result, error = run_engine(engine, function, params, tuple(states) if states else None)
    if error:
        raise NirfInputError(error)
    return result


def _context() -> list[tuple[str, dict]]:
    """Earlier questions and their plans (without our resolved call), so follow-ups can refer to them."""
    out = []
    for turn in st.session_state[HISTORY][-3:]:
        if turn["answer"] is not None and turn["answer"].kind != "error":
            out.append((turn["question"], {k: v for k, v in turn["answer"].plan.items() if k != "resolved_call"}))
    return out


def _answer(pending: dict) -> dict:
    """One new turn: run a sample question directly, or plan a typed one with the model and run the plan."""
    if "qid" in pending:
        plan = registry_plan(pending["qid"])
        return {"question": plan.title, "answer": execute(plan, run_fn=_run, question=plan.title), "error": None}
    question = pending["question"]
    if "plan" in pending:      # "Use IISc instead": the same plan with another institution, no model call
        plan = PLAN.validate_python(pending["plan"])
        return {"question": question, "answer": execute(plan, run_fn=_run, question=question), "error": None}
    try:
        plan = PLAN.validate_python(_plan(question, json.dumps(_context())))
    except llm.LLMError as e:
        return {"question": question, "answer": None, "error": {"kind": e.kind, "message": e.message, "fix": e.fix}}
    except PlanError:
        return {"question": question, "answer": None, "error": {
            "kind": "plan", "message": "The model answered twice, but not with a plan our code could check.",
            "fix": "Ask again in other words, naming the category, the years or the institution."}}
    except Exception as e:  # never let the page crash
        return {"question": question, "answer": None, "error": {
            "kind": "unknown", "message": f"Something unexpected happened ({type(e).__name__}).",
            "fix": "Ask again; the Question Bank and Explore pages always work."}}
    return {"question": question, "answer": execute(plan, run_fn=_run, question=question), "error": None}


# ---------- actions ----------

def _ask(question: str) -> None:
    st.session_state[PENDING] = {"question": question}


def _ask_sample(qid: str) -> None:
    st.session_state[PENDING] = {"qid": qid}


def _pick_example() -> None:
    choice = st.session_state.get("ask-examples")
    if choice:
        st.session_state[PENDING] = {"question": choice}
    st.session_state["ask-examples"] = None


def _use_instead(i: int, choice: dict) -> None:
    """Re-run turn i's plan with the institution the person picked (no model call)."""
    turn = st.session_state[HISTORY][i]
    plan, question = with_institution(turn["answer"].plan, turn["question"], choice["typed"], choice["key"],
                                      choice["label"])
    st.session_state[PENDING] = {"question": question, "plan": plan}


def _clear() -> None:
    st.session_state[HISTORY] = []


# ---------- drawing ----------

def _assumed(answer: Answer) -> None:
    """Every assumption as a plain sentence, in a box directly under the answer (not hidden in the expander)."""
    if answer.assumptions:
        items = "".join(f"<li>{_esc(a)}</li>" for a in answer.assumptions)
        st.html(f"<div class='nirf-ask-assumed'><div class='title'>Assumed:</div><ul>{items}</ul></div>")


def _instead(answer: Answer, i: int) -> None:
    """One button per other institution the person may have meant; a click re-runs the question with it."""
    if not answer.alternatives:
        return
    cols = st.columns(max(len(answer.alternatives), 2))
    for j, choice in enumerate(answer.alternatives):
        cols[j].button(f"Use {choice['label']} instead", key=f"ask-alt-inst-{i}-{j}", on_click=_use_instead,
                       args=(i, choice), icon=":material/swap_horiz:", width="stretch")


def _understood(answer: Answer) -> None:
    with st.expander("How I understood your question", icon=":material/psychology:"):
        if answer.assumptions:
            st.markdown("\n".join(f"- {a}" for a in answer.assumptions))
        else:
            st.markdown("- No extra assumptions: the question named everything the analysis needs.")
        st.caption("The plan as JSON (written by the model, or taken from the Question Bank for a sample question). "
                   "`resolved_call` is the exact call our code checked and ran.")
        st.json(answer.plan, expanded=False)


def _follow_ups(questions: list[str], i: int) -> None:
    if not questions:
        return
    st.html("<div class='nirf-ask-next'>Ask next</div>")
    for j, q in enumerate(questions):     # one per line, so long questions are never cut off
        st.button(q, key=f"ask-fu-{i}-{j}", on_click=_ask, args=(q,), icon=":material/arrow_forward:")


def _note(kind: str, title: str, message: str, fix: str | None = None) -> None:
    fix_html = f"<div class='fix'><b>How to fix it:</b> {_esc(fix)}</div>" if fix else ""
    st.html(f"<div class='nirf-ask-note {kind}'><div class='title'>{_esc(title)}</div>"
            f"<div class='msg'>{_esc(message)}</div>{fix_html}</div>")


def _alternatives(question: str, i: int, engine: str | None = None) -> None:
    """Ready-made answers that work without the model: the closest sample questions and their pages.

    After a data problem the analysis is known (engine), so only sample questions of that analysis are offered.
    """
    matches = closest_questions(question, k=8 if engine else 2)
    if engine:
        matches = [q for q in matches if q.engine == engine][:2]
    st.html("<div class='nirf-ask-next'>Meanwhile, these work without the AI</div>")
    for q in matches:
        c1, c2, c3 = st.columns([3, 1.1, 1.1], vertical_alignment="center")
        c1.button(f"Run {q.id} here: {q.text}", key=f"ask-alt-{i}-{q.id}", on_click=_ask_sample, args=(q.id,),
                  icon=":material/play_arrow:", width="stretch")
        c2.page_link("views/question_bank.py", label=f"{q.id} in Question Bank", icon=":material/quiz:",
                     query_params={"q": q.id})
        path, title = page_for(q.engine)
        c3.page_link(path, label=f"Open {title}", icon=":material/explore:")
    if not matches:
        path, title = page_for(engine or "builder")
        c1, c2 = st.columns(2)
        c1.page_link("views/question_bank.py", label="Open the Question Bank", icon=":material/quiz:")
        c2.page_link(path, label=f"Open {title}", icon=":material/explore:")


def _user(question: str) -> None:
    with st.chat_message("user", avatar=":material/person:"):
        st.markdown(question)


def _assistant(turn: dict, i: int) -> None:
    if turn["error"]:
        e = turn["error"]
        _note("bad", ERROR_TITLES.get(e["kind"], ERROR_TITLES["unknown"]), e["message"], e["fix"])
        _alternatives(turn["question"], i)
        return
    a: Answer = turn["answer"]
    if a.kind == "chart":
        if a.title and a.title.strip().lower() != turn["question"].strip().lower():
            st.html(f"<div class='nirf-ask-title'>{_esc(a.title)}</div>")
        chart_card(a.result, key=f"ask-{i}")
        _assumed(a)
        _instead(a, i)
        _understood(a)
        _follow_ups(a.follow_ups, i)
    elif a.kind == "not_ranked":
        _note("info", "Took part in NIRF, but never ranked", a.message)
        _assumed(a)
        if a.alternatives:
            st.html("<div class='nirf-ask-next'>Similar ranked institutions, same state and category</div>")
        _instead(a, i)
        _understood(a)
    elif a.kind == "error":
        _note("warn", "The data cannot answer it this way", a.message,
              "Change the institution, years or category in your question, or use the page below.")
        _assumed(a)
        _instead(a, i)
        _understood(a)
        _alternatives(turn["question"], i, a.engine)
    elif a.kind == "clarify":
        _note("info", "Could you say a bit more?", a.message)
        cols = st.columns(max(len(a.options), 1))
        for j, option in enumerate(a.options):
            cols[j].button(option, key=f"ask-opt-{i}-{j}", on_click=_ask,
                           args=(f"{turn['question']} ({option})",), width="stretch")
    else:
        _note("info", "That is outside the NIRF data", a.message)
        _follow_ups(a.follow_ups, i)


def _intro() -> None:
    st.html("""
<div class="nirf-steps nirf-ask-steps">
  <div class="nirf-step"><div class="num">01</div><div class="head">You ask</div>
    <div class="body">Any question about NIRF 2017–2025, in English or Hinglish: typos and short forms such as
    "iitb", "TN" or "engg" are fine.</div></div>
  <div class="nirf-step"><div class="num">02</div><div class="head">Gemini writes a plan</div>
    <div class="body">The model picks the analysis, category, years, states and institutions as a small JSON plan.
    It never sees the data and never calculates a number.</div></div>
  <div class="nirf-step"><div class="num">03</div><div class="head">Our engines answer</div>
    <div class="body">Our code checks the plan, translates the names and runs the same analysis as the rest of the
    atlas: chart, one-line answer, method and data.</div></div>
</div>""")


def _sidebar() -> None:
    ok, text = _status()
    with st.sidebar:
        st.html(f"<div class='nirf-ai-status {'ok' if ok else 'bad'}'><span class='dot'></span>"
                f"<span><b>Gemini</b> · {_esc(text)}</span></div>")
        st.button("Check the key again", on_click=_status.clear, icon=":material/refresh:", width="stretch",
                  key="ask-recheck")
        st.caption("The chat reads category, years and states from your question; the global filters above "
                   "are not used here.")


# ---------- page ----------

st.session_state.setdefault(HISTORY, [])
_sidebar()
typed = st.chat_input("Ask about NIRF rankings, e.g. Which IITs improved the most since 2019?", key="ask-input")
if typed and typed.strip():
    _ask(typed.strip())

HEADER = ("Ask NIRF", "Type a question in plain words and get the chart that answers it. The Gemini API reads the "
          "question; our engines do every calculation.")
if st.session_state[HISTORY]:
    head, side = st.columns([5, 1], vertical_alignment="bottom")
    with head:
        page_header(*HEADER, eyebrow="Build & ask · Natural language")
    with side:
        st.button("New chat", on_click=_clear, icon=":material/add_comment:", key="ask-clear", width="stretch")
else:   # no button yet: the header (and its rule) spans the page like on every other page
    page_header(*HEADER, eyebrow="Build & ask · Natural language")

if not st.session_state[HISTORY] and PENDING not in st.session_state:
    _intro()
for i, turn in enumerate(st.session_state[HISTORY]):
    _user(turn["question"])
    with st.chat_message("assistant", avatar=":material/insights:"):
        _assistant(turn, i)

pending = st.session_state.pop(PENDING, None)
if pending:
    i = len(st.session_state[HISTORY])
    _user(pending.get("question") or registry_plan(pending["qid"]).title)
    with st.chat_message("assistant", avatar=":material/insights:"):
        with st.spinner("Reading your question, then running our analysis…" if "question" in pending else
                        "Running the sample question…"):
            turn = _answer(pending)
        st.session_state[HISTORY].append(turn)
        _assistant(turn, i)

st.pills("Try an example", EXAMPLES, key="ask-examples", on_change=_pick_example, label_visibility="collapsed")
