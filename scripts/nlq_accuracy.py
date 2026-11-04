"""Send the 33 test questions of tests/nlq_questions.py to the live model and print the accuracy report.

For each question: the plan the model wrote ("engine.function", or custom / clarify / out_of_scope),
whether it is one of the expected analyses, whether our executor drew it, and the reason for any miss
(the wrong analysis, an invalid plan after the retry, or the model error). Accuracy = correct plans / 33.
A prediction or opinion question (N29-N31) only counts as correct when the plan also carries the notice
("I can't predict future rankings ..."), because without it the chart could be read as a forecast.
Needs GEMINI_API_KEY in .env (each question is one model call, two if the first plan is invalid). The
free tier allows about 20 requests per model per day and a few per minute, so the questions are sent a
few seconds apart, and the report shows which model answered each one.

    python -m scripts.nlq_accuracy
    python -m scripts.nlq_accuracy N26 N27 N28      # only these questions (saves the free quota)
"""

from __future__ import annotations

import sys
import time

PAUSE_S = 6          # seconds between questions, to stay under the free tier's per-minute limit
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # Windows consoles default to cp1252 (no −, →, ρ)

from nlq import llm  # noqa: E402
from nlq.executor import execute  # noqa: E402
from nlq.planner import PlanError, plan_question  # noqa: E402
from tests.nlq_questions import NLQ_QUESTIONS, plan_label  # noqa: E402


def main() -> int:
    if not llm.settings().keys:
        print("No GEMINI_API_KEY found: copy .env.example to .env and add your key.")
        return 2
    only = {a.upper() for a in sys.argv[1:]}
    questions = [q for q in NLQ_QUESTIONS if not only or q.id in only]
    correct, misses = 0, []
    for i, q in enumerate(questions):
        if i:
            time.sleep(PAUSE_S)
        start = time.perf_counter()
        llm.LAST_MODEL = None
        notice_ok = True
        try:
            plan = plan_question(q.question)
            got = plan_label(plan)
            notice_ok = not q.golden.get("notice") or bool(getattr(plan, "notice", ""))
            answer = execute(plan, question=q.question)
            drawn = answer.kind != "error"
            reason = "" if drawn else f"executor: {answer.message[:90]}"
        except (llm.LLMError, PlanError) as e:
            got, drawn, reason = "ERROR", False, str(e)[:120]
        ok = got in q.expected and notice_ok
        correct += ok
        if not ok:
            reason = reason or (f"planned {got}, expected {' or '.join(q.expected)}" if got not in q.expected
                                else "no notice on a prediction / opinion question")
            misses.append((q, got, reason))
        print(f"{'OK  ' if ok else 'MISS'} {q.id} [{q.style:<12}] {got:<38} {'drawn' if drawn else 'not drawn':<9} "
              f"{llm.LAST_MODEL or '-':<24} {time.perf_counter() - start:4.1f}s  {q.question}")
    print(f"\nAccuracy: {correct}/{len(questions)} = {100 * correct / len(questions):.0f}%")
    for q, got, reason in misses:
        print(f"  {q.id} {q.question!r}: {reason}")
    return 0 if correct == len(questions) else 1


if __name__ == "__main__":
    sys.exit(main())
