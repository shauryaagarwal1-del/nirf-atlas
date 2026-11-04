"""Answer one exam question (tests/exam_questions.py) through the UI path or the Ask NIRF chat, and judge it.

ui_answer(q)          opens the page headless (Streamlit AppTest), picks the view, sets the controls as a
                      person would, and passes when the app draws exactly the expected chart(s) with no
                      error (same chart titles as the direct engine calls), or, for a question the data
                      cannot answer, shows a friendly message card that explains why.
chat_answer(q, plan)  runs a chat plan (the live model's recorded plan, or the golden one) through our
                      executor, and passes when it is an acceptable analysis run with the settings the
                      question asks for (`must`), or gives the expected explanation.
Both also check `check`: a phrase the one-line answer must contain to show the tricky case was handled.
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass

from core.data import category_years, check_states, find_institution
from core.runner import run
from nlq.catalog import functions
from nlq.executor import execute
from nlq.planner import PLAN
from tests.app_helpers import PICKER_TAB, chart_titles, html_text, open_page, set_widget, widget
from tests.exam_questions import PREFIX, Exam
from tests.nlq_questions import plan_label


@dataclass
class Outcome:
    ok: bool
    shown: str            # what the person sees: the chart title(s) or the message
    insight: str = ""     # the one-line answer (charts only)
    problem: str = ""     # why it failed (empty when ok)
    plan: str = ""        # chat only: the plan the model chose ("engine.function", custom ...)
    notes: tuple = ()     # chat only: how the question was understood (assumptions)


def expected_results(q: Exam) -> list:
    return [run(engine, function, params, states=states) for engine, function, params, states in q.calls]


def ui_answer(q: Exam) -> Outcome:
    at = open_page(q.page, q.state or PICKER_TAB.get(q.page))
    if q.view:
        at = set_widget(at, "selectbox", f"x-{PREFIX[q.page]}-view", q.view)
    for kind, key, value in q.widgets:
        at = set_widget(at, kind, key, value)
        if at.exception:
            return Outcome(False, "", problem=f"error after setting {key}: {at.exception[0].value[:200]}")
    html = html_text(at)
    problems = []
    if q.options:
        kind, key, allowed = q.options
        offered = list(widget(at, kind, key).options)
        if offered != [str(v) for v in allowed]:
            problems.append(f"{key} offers {offered}, expected only {allowed}")

    if not q.calls:                                   # no chart answer: a message card must explain why
        message = html if "nirf-empty" in html else ""
        if not message:
            problems.append("no message card")
        elif q.expect not in message:
            problems.append(f"the message does not say '{q.expect}'")
        if at.get("plotly_chart"):
            problems.append("a chart was drawn")
        return Outcome(not problems, _message_text(at), problem="; ".join(problems))

    expected = expected_results(q)
    titles = chart_titles(at)
    want = [r.fig.layout.title.text for r in expected]
    if titles != want:
        problems.append(f"charts {titles} differ from the expected {want}")
    if "nirf-empty" in html:
        problems.append("an empty-state card is shown")
    insight = expected[0].insight
    if q.check and q.check not in insight:
        problems.append(f"the answer does not mention '{q.check}'")
    return Outcome(not problems, " | ".join(titles), insight, "; ".join(problems))


def _message_text(at) -> str:
    """The text of the empty-state card (title and explanation), without its HTML tags."""
    cards = [h.proto.body for h in at.get("html") if "nirf-empty" in h.proto.body]
    return " ".join(re.sub(r"<[^>]+>", " ", " ".join(cards)).split())


# ---------- chat ----------

def _same(a, b) -> bool:
    """Equal after treating a one-item list as its item and ignoring the order of lists."""
    def norm(v):
        if isinstance(v, (list, tuple)):
            v = list(v)
            return norm(v[0]) if len(v) == 1 else sorted(map(str, v))
        return v
    return norm(a) == norm(b)


def must_problems(q: Exam, answer) -> list[str]:
    """The `must` settings the chat's resolved call does not have (only parameters the chosen function takes)."""
    call = answer.plan.get("resolved_call", {})
    if "engine" not in call:
        return ["not an engine analysis"]
    sig = inspect.signature(functions()[(call["engine"], call["function"])]).parameters
    params, scope = call["params"], call.get("states")
    problems = []
    for key, want in q.must.items():
        if key == "states":
            got = params.get("states") or scope or []
            if set(check_states(got)) != set(check_states(want)):
                problems.append(f"states {got} instead of {want}")
            continue
        if key not in sig:
            continue
        got = params.get(key, sig[key].default)
        if key == "institutions":
            got, want = set(got or []), {find_institution(n) for n in want}
        elif key == "min_years":                     # the engine caps it at the years the category has
            got = min(int(got), len(category_years(params.get("category", "Overall"))))
        elif got is None and key in ("year", "end_year", "year_b", "start_year", "year_a"):
            years = category_years(params.get("category", "Overall"))       # None = the engine's default year
            got = years[0] if key in ("start_year", "year_a") else years[-1]
        if not _same(got, want):
            problems.append(f"{key} = {got!r} instead of {want!r}")
    return problems


def chat_answer(q: Exam, plan_dict: dict) -> Outcome:
    plan = PLAN.validate_python(plan_dict)
    label = plan_label(plan)
    answer = execute(plan, question=q.question)
    notes = tuple(answer.assumptions)
    if q.expect != "chart":                           # the data cannot answer as asked: the reply must say why
        said = answer.message if answer.kind != "chart" else ""
        ok = bool(said) and q.expect in said
        return Outcome(ok, said or (answer.result.fig.layout.title.text if answer.result else ""),
                       problem="" if ok else f"expected a message saying '{q.expect}', got {answer.kind}",
                       plan=label, notes=notes)
    if answer.kind != "chart":
        return Outcome(False, answer.message, problem=f"no chart ({answer.kind}): {answer.message[:200]}",
                       plan=label, notes=notes)
    problems = [] if label in q.chat_ok else [f"planned {label}, expected {' or '.join(q.chat_ok)}"]
    problems += must_problems(q, answer)
    insight = answer.result.insight
    if q.check and q.check not in insight:
        problems.append(f"the answer does not mention '{q.check}'")
    return Outcome(not problems, answer.result.fig.layout.title.text, insight, "; ".join(problems), label, notes)
