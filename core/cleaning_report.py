"""Reads docs/cleaning_report.md (written by pipeline/report.py) into tables for the Data & Method page.

Why: the page shows the cleaning steps with their row counts before and after, what each step changed
and why, and the data dictionary. Reading them from the report (instead of typing the numbers into the
page) means the page always matches the last pipeline run: re-run the pipeline and the page follows.

What is read:
  * the summary table "| step | what | rows before | rows after |";
  * for every "## Step N: title" section, its "**What changed:**" and "**Why:**" paragraphs;
  * the summary bullet points (master table size, institutions, rank types ...);
  * the data dictionary table of data/processed/nirf_master.parquet (column, meaning, type, example).
If the report is missing or its layout changes, the functions return empty tables, and the page says so
instead of failing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

REPORT = Path(__file__).resolve().parents[1] / "docs" / "cleaning_report.md"


@dataclass
class CleaningReport:
    generated: str = ""                                          # e.g. "03 November 2026"
    summary: list[str] = field(default_factory=list)             # the summary bullets, markdown stripped
    steps: pd.DataFrame = field(default_factory=pd.DataFrame)    # step, what, rows_before, rows_after, change, ...
    dictionary: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def ok(self) -> bool:
        return not self.steps.empty


def _plain(md: str) -> str:
    """Markdown inline formatting removed: **bold**, `code` and [text](link) become plain text."""
    md = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", md)
    return re.sub(r"\*\*|`", "", md).strip()


def _table_rows(lines: list[str], start: int) -> list[list[str]]:
    """The cells of the markdown table whose header is lines[start] (the |---| line is skipped)."""
    rows = []
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    return rows


def _number(text: str) -> int:
    return int(text.replace(",", ""))


def read_cleaning_report(path: Path = REPORT) -> CleaningReport:
    """Parse the cleaning report; an empty CleaningReport when the file is missing or unreadable."""
    if not path.exists():
        return CleaningReport()
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    report = CleaningReport()

    m = re.search(r"on (\d{1,2} \w+ \d{4})", text)
    report.generated = m.group(1) if m else ""

    # Summary bullets: the "- **Label:** text" lines under "## Summary".
    if "## Summary" in lines:
        for line in lines[lines.index("## Summary") + 1:]:
            if line.startswith("## ") or line.startswith("| "):
                break
            if line.startswith("- "):
                report.summary.append(_plain(line[2:]))

    # Step table with rows before / after.
    head = next((i for i, l in enumerate(lines) if l.startswith("| step | what | rows before | rows after")), None)
    if head is None:
        return report
    steps = pd.DataFrame(_table_rows(lines, head), columns=["step", "what", "rows_before", "rows_after"])
    steps["rows_before"] = steps["rows_before"].map(_number)
    steps["rows_after"] = steps["rows_after"].map(_number)
    steps["change"] = steps["rows_after"] - steps["rows_before"]

    # "What changed" and "Why" of each "## Step N: title" section.
    changed, why = {}, {}
    sections = re.split(r"^## Step ", text, flags=re.MULTILINE)[1:]
    for sec in sections:
        step = sec.split(":", 1)[0].strip()
        m = re.search(r"^\*\*What changed:\*\* (.+)$", sec, flags=re.MULTILINE)
        changed[step] = _plain(m.group(1)) if m else ""
        m = re.search(r"^\*\*Why:\*\* (.+)$", sec, flags=re.MULTILINE)
        why[step] = _plain(m.group(1)) if m else ""
    steps["what_changed"] = steps["step"].map(changed).fillna("")
    steps["why"] = steps["step"].map(why).fillna("")
    report.steps = steps

    # Data dictionary of the master table (the first column/meaning/type/example table after its heading).
    start = next((i for i, l in enumerate(lines) if l.startswith("### `data/processed/nirf_master.parquet`")), None)
    if start is not None:
        head = next((i for i in range(start, len(lines)) if lines[i].startswith("| column | meaning")), None)
        if head is not None:
            rows = [[_plain(c) for c in r] for r in _table_rows(lines, head)]
            report.dictionary = pd.DataFrame(rows, columns=["column", "meaning", "type", "example"])
    return report


def find_count(text: str, pattern: str) -> int | None:
    """The first number matched by `pattern` (a regex with one group) in `text`, e.g. '2,288' -> 2288."""
    m = re.search(pattern, text)
    return _number(m.group(1)) if m else None
