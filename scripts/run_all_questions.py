"""Run all 40 Annexure A questions, save every chart as HTML and print a pass/fail table.

For each question in core/questions.py we call its engine function with the default parameters and
check that the answer is complete: a Plotly figure with data and a title, the NIRF source note, a
non-empty table, an insight, a method text, and a chart type that is listed in
docs/allowed_charts.md and matches the registry. Each figure is written to docs/previews/<id>.html
(Plotly loaded from its CDN, so the files stay small). The script exits with code 1 if any fails.

    python -m scripts.run_all_questions
"""

from __future__ import annotations

import re
import sys
import textwrap
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

from core.questions import QUESTION_REGISTRY, engine_function  # noqa: E402
from core.result import ChartResult  # noqa: E402
from core.theme import SOURCE_NOTE  # noqa: E402

PREVIEWS = ROOT / "docs" / "previews"
ALLOWED_CHARTS = ROOT / "docs" / "allowed_charts.md"


def allowed_chart_types() -> set[str]:
    """The chart-type names in docs/allowed_charts.md (the backticked name at the start of each list item)."""
    return set(re.findall(r"^- `([^`]+)`", ALLOWED_CHARTS.read_text(encoding="utf-8"), flags=re.MULTILINE))


def check(result, expected_chart: str, allowed: set[str]) -> list[str]:
    """Everything that is wrong with one answer (empty list = pass)."""
    problems = []
    if not isinstance(result, ChartResult):
        return [f"returned {type(result).__name__}, not ChartResult"]
    if not isinstance(result.fig, go.Figure) or not result.fig.data:
        problems.append("figure has no data")
    if not result.fig.layout.title.text:
        problems.append("no title")
    if not any(SOURCE_NOTE in (a.text or "") for a in result.fig.layout.annotations):
        problems.append("no source note")
    if not isinstance(result.table, pd.DataFrame) or result.table.empty:
        problems.append("empty table")
    if not result.insight or len(result.insight) < 20:
        problems.append("no insight")
    if not result.method or len(result.method) < 40:
        problems.append("no method")
    if result.chart_type not in allowed:
        problems.append(f"chart type '{result.chart_type}' not in docs/allowed_charts.md")
    elif result.chart_type != expected_chart:
        problems.append(f"chart type '{result.chart_type}' differs from registry '{expected_chart}'")
    return problems


def main() -> int:
    allowed = allowed_chart_types()
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    rows = []
    for qid, q in QUESTION_REGISTRY.items():
        start = time.perf_counter()
        try:
            r = engine_function(q)(**q.default_params)
            problems = check(r, q.chart_type, allowed)
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
