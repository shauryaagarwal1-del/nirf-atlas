"""Level 2 tests (Phase 10): 15 new examiner-style questions, each answered in the real app using only the UI.

For every question in tests/level2_questions.py the test opens the page, picks the view, sets the listed
controls exactly as a person would, and checks that the app draws one chart with no error and that the
chart is the same answer as the analysis those settings stand for (same title as the direct call).

    python -m pytest tests/test_level2.py -v
"""

import pytest

from core.builder import build_chart
from core.data import MASTER_PATH
from core.runner import run
from tests.app_helpers import PICKER_TAB, chart_titles, html_text, open_page, set_widget, widget
from tests.level2_questions import LEVEL2

if not MASTER_PATH.exists():
    pytest.skip("run `python -m pipeline.clean` first", allow_module_level=True)

PREFIX = {"views/trends.py": "trends", "views/geography.py": "geography", "views/distributions.py": "distributions",
          "views/relationships.py": "relationships", "views/multi_parameter.py": "multi",
          "views/mobility.py": "mobility", "views/outliers.py": "outliers"}


def expected_title(q) -> str:
    if q.call[0] == "builder":
        return build_chart(**q.call[1]).fig.layout.title.text
    engine, function, params, states = q.call
    return run(engine, function, params, states=states).fig.layout.title.text


def test_fifteen_new_questions():
    assert len(LEVEL2) == 15 and len({q.id for q in LEVEL2}) == 15


@pytest.mark.parametrize("q", LEVEL2, ids=[q.id for q in LEVEL2])
def test_question_is_answered_through_the_ui(q):
    at = open_page(q.page, PICKER_TAB.get(q.page))
    if q.view:
        at = set_widget(at, "selectbox", f"x-{PREFIX[q.page]}-view", q.view)
    for kind, key, value in q.widgets:
        at = set_widget(at, kind, key, value)
        assert not at.exception, (key, [e.value for e in at.exception])
    assert len(at.get("plotly_chart")) == 1
    assert "nirf-empty" not in html_text(at)
    assert chart_titles(at) == [expected_title(q)]


def test_e07_compares_two_categories_by_switching_one_control():
    """E07 is answered by reading Pearson r for Engineering, then changing only the category."""
    q = next(q for q in LEVEL2 if q.id == "E07")
    at = open_page(q.page)
    for kind, key, value in q.widgets:
        at = set_widget(at, kind, key, value)
    engineering = chart_titles(at)[0]
    at = set_widget(at, "selectbox", "x-relationships-category", "Management")
    assert widget(at, "selectbox", "x-relationships-x").value == "pr"
    management = chart_titles(at)[0]
    assert "Engineering 2024" in engineering and "Management 2024" in management
