"""Question registry tests (Phase 7): all 40 Annexure A questions are registered, use allowed charts and run.

Checks that core/questions.py lists exactly the IDs Q1.1-Q8.5 with the question text copied word for word
from docs/sample_questions.md, that every registered chart_type is a name from docs/allowed_charts.md, and
that every question, run with its default parameters, returns a complete ChartResult with that chart type.

    python -m pytest tests/test_questions.py -v
"""

import inspect
import re
from pathlib import Path

import pandas as pd
import pytest

from core.data import MASTER_PATH
from core.questions import ENGINES, QUESTION_REGISTRY, SECTIONS, engine_function, get_question, run_question
from core.theme import SOURCE_NOTE

if not MASTER_PATH.exists():
    pytest.skip("run `python -m pipeline.clean` first", allow_module_level=True)

DOCS = Path(__file__).resolve().parents[1] / "docs"
CHART_TYPES = set(re.findall(r"^- `([^`]+)`", (DOCS / "allowed_charts.md").read_text(encoding="utf-8"),
                             flags=re.MULTILINE))
SAMPLE = dict(re.findall(r"^\| (Q\d\.\d) \| (.+?) \|$", (DOCS / "sample_questions.md").read_text(encoding="utf-8"),
                         flags=re.MULTILINE))
IDS = list(QUESTION_REGISTRY)


def test_registry_has_all_40_ids_in_order():
    expected = [f"Q{s}.{q}" for s in range(1, 9) for q in range(1, 6)]
    assert IDS == expected


def test_question_text_matches_annexure_word_for_word():
    assert len(SAMPLE) == 40
    for qid, q in QUESTION_REGISTRY.items():
        assert q.text == SAMPLE[qid], qid
        assert q.section == SECTIONS[int(qid[1])]


@pytest.mark.parametrize("qid", IDS)
def test_registered_chart_type_is_allowed(qid):
    q = QUESTION_REGISTRY[qid]
    assert q.chart_type in CHART_TYPES, f"{qid}: '{q.chart_type}' is not in docs/allowed_charts.md"
    assert q.why_this_chart and q.why_this_chart.endswith(".")


@pytest.mark.parametrize("qid", IDS)
def test_registered_call_exists_with_valid_parameters(qid):
    q = QUESTION_REGISTRY[qid]
    assert q.engine in ENGINES
    fn = engine_function(q)
    params = inspect.signature(fn).parameters
    assert set(q.default_params) <= set(params), f"{qid}: unknown parameters {set(q.default_params) - set(params)}"


@pytest.mark.parametrize("qid", IDS)
def test_question_runs_and_draws_its_registered_chart(qid):
    q = QUESTION_REGISTRY[qid]
    r = run_question(qid)
    assert r.chart_type == q.chart_type
    assert r.fig.data and r.fig.layout.title.text
    assert any(SOURCE_NOTE in (a.text or "") for a in r.fig.layout.annotations)
    assert isinstance(r.table, pd.DataFrame) and not r.table.empty
    assert len(r.insight) > 20 and len(r.method) > 40


def test_overrides_change_the_answer():
    """Level 2: the same question with different filters gives a different, still valid answer."""
    a = run_question("Q2.1")
    b = run_question("Q2.1", year=2017, top_n=50)
    assert "2017" in b.insight and b.chart_type == a.chart_type
    assert b.table["institutions"].sum() <= 50


def test_get_question_is_forgiving_and_strict():
    assert get_question(" q5.2 ").id == "Q5.2"
    with pytest.raises(KeyError):
        get_question("Q9.9")
