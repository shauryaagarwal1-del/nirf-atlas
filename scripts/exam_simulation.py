"""Phase 14 exam simulation: answer the 30 new examiner questions via the UI path AND via the Ask NIRF chat.

For every question in tests/exam_questions.py:
  * UI path: the real app is opened headless (Streamlit AppTest), the view is picked and the controls are
    set as a person would; it passes when the app draws the expected chart (or the expected message);
  * Ask NIRF: the question is planned by the live Gemini model (with --live) and the plan is recorded in
    tests/exam_chat_plans.json, so it can be replayed offline; our executor then runs the recorded plan
    (or the golden plan, if the model has not planned it yet). It passes when the plan is an acceptable
    analysis with the settings the question asks for, or gives the expected explanation.
The results are written to docs/exam_simulation.md (between the results markers; the hand-written parts
of that file are kept) and printed. Exit code 1 if anything fails.

    python -m scripts.exam_simulation               # replay the recorded plans (no internet needed)
    python -m scripts.exam_simulation --live        # ask the model for questions not recorded yet first
    python -m scripts.exam_simulation --live --refresh   # ask the model again for every question
The free Gemini tier allows about 20 requests per model per day, so --live pauses between questions and
stops asking (keeping what it has) when every model's quota is used up.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # Windows consoles default to cp1252 (no −, →, ρ)
os.environ.setdefault("STREAMLIT_LOGGER_LEVEL", "error")      # hide "missing ScriptRunContext" noise of headless runs

from nlq import llm  # noqa: E402
from nlq.planner import PlanError, plan_question  # noqa: E402
from tests.exam_check import Outcome, chat_answer, ui_answer  # noqa: E402
from tests.exam_questions import EXAM, PAGE_TITLES, SECTIONS  # noqa: E402

PLANS = ROOT / "tests" / "exam_chat_plans.json"
DOC = ROOT / "docs" / "exam_simulation.md"
START, END = "<!-- results:start -->", "<!-- results:end -->"
PAUSE_S = 6


def load_plans() -> dict:
    return json.loads(PLANS.read_text(encoding="utf-8")) if PLANS.exists() else {}


def record_live_plans(refresh: bool) -> dict:
    """Ask the model for every question not recorded yet (all with refresh); save after each answer."""
    plans = load_plans()
    if not llm.settings().keys:
        print("No GEMINI_API_KEY found: replaying recorded plans only.")
        return plans
    todo = [q for q in EXAM if refresh or q.id not in plans]
    for i, q in enumerate(todo):
        if i:
            time.sleep(PAUSE_S)
        llm.LAST_MODEL = None
        try:
            plan = plan_question(q.question)
        except llm.LLMError as e:
            print(f"{q.id}: model not reachable ({e.kind}): {e.message}")
            if e.kind in ("quota", "offline", "invalid_key", "no_key"):
                print("Stopping live planning; the remaining questions use their golden plans for now.")
                break
            continue
        except PlanError as e:
            plans[q.id] = {"plan": None, "model": llm.LAST_MODEL, "error": str(e)[:300], "date": str(date.today())}
        else:
            plans[q.id] = {"plan": plan.model_dump(), "model": llm.LAST_MODEL, "date": str(date.today())}
        print(f"{q.id}: planned by {llm.LAST_MODEL}")
        PLANS.write_text(json.dumps(plans, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return plans


def simulate(plans: dict) -> list[dict]:
    rows = []
    for q in EXAM:
        start = time.perf_counter()
        try:
            ui = ui_answer(q)
        except Exception as e:                       # one crash must not hide the other answers
            ui = Outcome(False, "", problem=f"{type(e).__name__}: {str(e)[:200]}")
        rec = plans.get(q.id) or {}
        if rec.get("plan"):
            source, plan = f"live model ({rec.get('model')}, {rec.get('date')})", rec["plan"]
        elif rec.get("error"):
            source, plan = f"live model ({rec.get('model')}): no valid plan", None
        else:
            source, plan = "golden plan (not yet asked live)", q.golden
        if plan is None:
            chat = Outcome(False, "", problem=rec["error"])
        else:
            try:
                chat = chat_answer(q, plan)
            except Exception as e:
                chat = Outcome(False, "", problem=f"{type(e).__name__}: {str(e)[:200]}")
        rows.append(dict(q=q, ui=ui, chat=chat, source=source, seconds=time.perf_counter() - start))
        print(f"{q.id} UI {'PASS' if ui.ok else 'FAIL'}  chat {'PASS' if chat.ok else 'FAIL'} "
              f"({chat.plan or '-'})  {time.perf_counter() - start:4.1f}s  {q.question}")
        for side, o in (("UI", ui), ("chat", chat)):
            if not o.ok:
                print(f"      {side} problem: {o.problem}")
    return rows


def _mark(ok: bool) -> str:
    return "PASS" if ok else "**FAIL**"


def _same_chart(r: dict) -> str:
    """Did the chat draw the very chart the UI path drew (same title)? Different settings can still be correct."""
    if not (r["ui"].ok and r["chat"].ok):
        return "–"
    if r["q"].expect != "chart":
        return "same message" if r["chat"].shown and r["q"].expect in r["chat"].shown else "–"
    return "yes" if r["chat"].shown in r["ui"].shown.split(" | ") else "no (other valid settings)"


def results_markdown(rows: list[dict]) -> str:
    ui_ok = sum(r["ui"].ok for r in rows)
    chat_ok = sum(r["chat"].ok for r in rows)
    live = sum(r["source"].startswith("live model (") and "no valid" not in r["source"] for r in rows)
    out = [f"_Last run: {date.today():%d %B %Y}. UI path: **{ui_ok}/{len(rows)} pass**. Ask NIRF chat: "
           f"**{chat_ok}/{len(rows)} pass** ({live} of {len(rows)} planned by the live Gemini model"
           + (", the others by their golden plan" if live < len(rows) else "")
           + "). Regenerate with `python -m scripts.exam_simulation`._", "",
           "| ID | Section | Tricky case | UI path | Chat | Chat plan | Chat chart = UI chart |",
           "|---|---|---|---|---|---|---|"]
    for r in rows:
        q = r["q"]
        out.append(f"| {q.id} | {q.section}. {SECTIONS[q.section]} | {q.tricky or '–'} | {_mark(r['ui'].ok)} | "
                   f"{_mark(r['chat'].ok)} | `{r['chat'].plan or '-'}` | {_same_chart(r)} |")
    for r in rows:
        q, ui, chat = r["q"], r["ui"], r["chat"]
        where = PAGE_TITLES[q.page] + (f" → *{q.view}*" if q.view else "")
        out += ["", f"### {q.id}. {q.question}",
                f"- **Section:** {q.section}. {SECTIONS[q.section]}" + (f" · **tricky case:** {q.tricky}" if q.tricky
                                                                          else ""),
                f"- **UI path:** {where}; {q.controls} → {_mark(ui.ok)}",
                f"  - shown: {ui.shown or '(nothing)'}"]
        if ui.insight:
            out.append(f"  - answer: {ui.insight}")
        if ui.problem:
            out.append(f"  - problem: {ui.problem}")
        out += [f"- **Ask NIRF:** {r['source']} → `{chat.plan or '-'}` → {_mark(chat.ok)}",
                f"  - shown: {chat.shown or '(nothing)'}"]
        if chat.notes:
            out.append("  - how it understood the question: " + "; ".join(n.rstrip(". ") for n in chat.notes) + ".")
        if chat.problem:
            out.append(f"  - problem: {chat.problem}")
    return "\n".join(out)


def write_doc(rows: list[dict]) -> None:
    body = results_markdown(rows)
    text = DOC.read_text(encoding="utf-8") if DOC.exists() else f"# Exam simulation\n\n{START}\n{END}\n"
    head, rest = text.split(START, 1)
    tail = rest.split(END, 1)[1]
    DOC.write_text(f"{head}{START}\n{body}\n{END}{tail}", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--live", action="store_true", help="ask the live model for questions not recorded yet")
    ap.add_argument("--refresh", action="store_true", help="with --live: ask again for every question")
    ap.add_argument("--no-doc", action="store_true", help="print only; do not rewrite docs/exam_simulation.md")
    args = ap.parse_args()
    plans = record_live_plans(args.refresh) if args.live else load_plans()
    rows = simulate(plans)
    if not args.no_doc:
        write_doc(rows)
    ui_ok, chat_ok = sum(r["ui"].ok for r in rows), sum(r["chat"].ok for r in rows)
    print(f"\nUI path {ui_ok}/{len(rows)} · Ask NIRF {chat_ok}/{len(rows)}"
          + ("" if args.no_doc else f" · written to {DOC.relative_to(ROOT)}"))
    return 0 if ui_ok == chat_ok == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
