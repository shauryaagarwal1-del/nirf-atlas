"""Run all 40 Annexure A questions, save every chart as HTML and print a pass/fail table.

For each question in core/questions.py we call its engine function with the default parameters and
check that the answer is complete: a Plotly figure with data and a title, the NIRF source note, a
non-empty table, an insight, a method text, and a chart type that is listed in
docs/allowed_charts.md and matches the registry. Each figure is written to docs/previews/<id>.html
(Plotly loaded from its CDN, so the files stay small). The script exits with code 1 if any fails.

    python -m scripts.run_all_questions
"""

from __future__ import annotations

import sys
import textwrap
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.questions import QUESTION_REGISTRY, check_result, engine_function  # noqa: E402

PREVIEWS = ROOT / "docs" / "previews"


def main() -> int:
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    rows = []
    for qid, q in QUESTION_REGISTRY.items():
        start = time.perf_counter()
        try:
            r = engine_function(q)(**q.default_params)
            problems = check_result(r, q)
            r.fig.write_html(PREVIEWS / f"{qid}.html", include_plotlyjs="cdn", full_html=True)
            insight = r.insight
        except Exception as exc:                       # report and keep going: one failure must not hide others
            problems = [f"{type(exc).__name__}: {exc}"]
            insight = traceback.format_exc(limit=2).strip().splitlines()[-1]
        rows.append(dict(id=qid, call=f"{q.engine}.{q.function}", chart_type=q.chart_type,
                         status="PASS" if not problems else "FAIL", seconds=time.perf_counter() - start,
                         problems="; ".join(problems), insight=insight))

    width = 110
    print(f"\n{'ID':<6} {'Status':<6} {'Engine function':<44} {'Chart type':<28} {'s':>5}")
    print("-" * 93)
    for r in rows:
        print(f"{r['id']:<6} {r['status']:<6} {r['call']:<44} {r['chart_type']:<28} {r['seconds']:>5.1f}")
        if r["problems"]:
            print(textwrap.indent(textwrap.fill("PROBLEM: " + r["problems"], width), " " * 7))
        print(textwrap.indent(textwrap.fill(r["insight"], width), " " * 7))
    passed = sum(r["status"] == "PASS" for r in rows)
    print("-" * 93)
    print(f"{passed}/{len(rows)} questions passed · previews in {PREVIEWS.relative_to(ROOT)}")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
