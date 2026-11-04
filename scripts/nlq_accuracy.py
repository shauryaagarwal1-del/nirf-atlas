"""Send the 25 test questions of tests/nlq_questions.py to the live model and print the accuracy report.

For each question: the plan the model wrote ("engine.function", or custom / clarify / out_of_scope),
whether it is one of the expected analyses, whether our executor drew it, and the reason for any miss
(the wrong analysis, an invalid plan after the retry, or the model error). Accuracy = correct plans / 25.
Needs GEMINI_API_KEY in .env (each question is one model call, two if the first plan is invalid).

    python -m scripts.nlq_accuracy
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nlq import llm  # noqa: E402
from nlq.executor import execute  # noqa: E402
from nlq.planner import PlanError, plan_question  # noqa: E402
from tests.nlq_questions import NLQ_QUESTIONS, plan_label  # noqa: E402


def main() -> int:
    if not llm.settings().keys:
        print("No GEMINI_API_KEY found: copy .env.example to .env and add your key.")
        return 2
    correct, misses = 0, []
    for q in NLQ_QUESTIONS:
        start = time.perf_counter()
        try:
            plan = plan_question(q.question)
            got = plan_label(plan)
            answer = execute(plan, question=q.question)
            drawn = answer.kind != "error"
            reason = "" if drawn else f"executor: {answer.message[:90]}"
        except (llm.LLMError, PlanError) as e:
            got, drawn, reason = "ERROR", False, str(e)[:120]
        ok = got in q.expected
        correct += ok
        if not ok:
            reason = reason or f"planned {got}, expected {' or '.join(q.expected)}"
            misses.append((q, got, reason))
        print(f"{'OK  ' if ok else 'MISS'} {q.id} [{q.style:<12}] {got:<40} {'drawn' if drawn else 'not drawn':<9} "
              f"{time.perf_counter() - start:4.1f}s  {q.question}")
    print(f"\nAccuracy: {correct}/{len(NLQ_QUESTIONS)} = {100 * correct / len(NLQ_QUESTIONS):.0f}%")
    for q, got, reason in misses:
        print(f"  {q.id} {q.question!r}: {reason}")
    return 0 if correct == len(NLQ_QUESTIONS) else 1


if __name__ == "__main__":
    sys.exit(main())
