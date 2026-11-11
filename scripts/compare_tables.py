"""Prove that a drawing change did not change any number: save the 40 result tables, then compare.

Every question in core/questions.py returns a table (the numbers its chart is drawn from) and an
insight sentence. Before a change to how charts look, save them; after the change, compare: the
script prints every table whose shape, columns or values differ, and exits with code 1 if any does.

    python scripts/compare_tables.py save    <folder>      -> writes <folder>/Q1.1.pkl ... Q8.5.pkl
    python scripts/compare_tables.py compare <folder>      -> compares the current tables with the saved ones
"""

from __future__ import annotations

import pickle
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from core.questions import QUESTION_REGISTRY, run_question  # noqa: E402


def current() -> dict[str, tuple[pd.DataFrame, str]]:
    return {qid: (r.table, r.insight) for qid in QUESTION_REGISTRY for r in [run_question(qid)]}


def main(mode: str, folder: str) -> int:
    out = Path(folder)
    if mode == "save":
        out.mkdir(parents=True, exist_ok=True)
        for qid, (table, insight) in current().items():
            with open(out / f"{qid}.pkl", "wb") as fh:
                pickle.dump({"table": table, "insight": insight}, fh)
        print(f"saved {len(QUESTION_REGISTRY)} tables to {out}")
        return 0
    if mode != "compare":
        print(__doc__)
        return 2
    differences = 0
    for qid, (table, insight) in current().items():
        with open(out / f"{qid}.pkl", "rb") as fh:
            saved = pickle.load(fh)
        problems = []
        try:
            pd.testing.assert_frame_equal(saved["table"], table, check_dtype=True)
        except AssertionError as exc:
            problems.append("table: " + str(exc).strip().splitlines()[0])
        if saved["insight"] != insight:
            problems.append(f"insight changed:\n    before: {saved['insight']}\n    after:  {insight}")
        if problems:
            differences += 1
            print(f"{qid}: " + "\n  ".join(problems))
    print(f"{differences} of {len(QUESTION_REGISTRY)} tables differ")
    return 1 if differences else 0


if __name__ == "__main__":
    sys.exit(main(*(sys.argv[1:3] + [""] * (3 - len(sys.argv)))[:2]) if len(sys.argv) >= 3 else (print(__doc__) or 2))
