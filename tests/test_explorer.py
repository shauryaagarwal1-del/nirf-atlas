"""Explorer page tests (Phase 10): every engine page exposes ALL the knobs of each analysis, and every view runs.

Checked:
  * every public engine function is offered on a page (the two-variable scatter on Relationships, the coverage
    heatmap on Data & Method, every other one as a "What do you want to see?" view);
  * each view has a control for every parameter of its engine function, and no control for anything else;
  * in the real app (AppTest, headless), every view of every page draws one chart with no error;
  * the controls shared with the sidebar stay in sync both ways, and the state filter shows on the chart;
  * the Relationships two-variable interface shows Pearson r, Spearman rho, R squared, p and n with a
    one-line interpretation, and colour-by-category pools several categories.

    python -m pytest tests/test_explorer.py -v
"""

import inspect
from pathlib import Path

import pytest

from core.data import MASTER_PATH
from core.runner import ENGINES, engine_function
from tests.app_helpers import chart_notes, chart_titles, html_text, open_page, set_widget, widget

if not MASTER_PATH.exists():
    pytest.skip("run `python -m pipeline.clean` first", allow_module_level=True)

PAGES_DIR = Path(__file__).resolve().parents[1] / "app" / "pages"
PAGES = {"trends": "trends", "geography": "geography", "distributions": "distributions",
         "multi_parameter": "multi", "mobility": "mobility", "outliers": "outliers", "relationships": "relationships"}
ELSEWHERE = {("bivariate", "scatter_relation"), ("univariate", "coverage_by_category_year")}


def page_views(name: str) -> list:
    """The View list of a page, read without running Streamlit (everything above its page_header() call)."""
    source = (PAGES_DIR / f"{name}.py").read_text(encoding="utf-8").split("\npage_header(")[0]
    ns: dict = {}
    exec(compile(source, f"app/pages/{name}.py", "exec"), ns)
    return ns.get("VIEWS") or ns["OTHER_VIEWS"]


ALL_VIEWS = [(name, v) for name in PAGES for v in page_views(name)]


def covered(view) -> set[str]:
    """The engine parameters a view's controls (and fixed values) set."""
    out = set(view.fixed)
    for c in view.controls:
        if c.kind == "period":
            out |= set(c.params)
        elif c.kind != "scope":
            out.add(c.name or c.kind)
    return out


def test_every_engine_function_is_on_a_page():
    import importlib
    public = {(e, n) for e in ENGINES for n, f in inspect.getmembers(importlib.import_module(f"core.engines.{e}"),
                                                                     inspect.isfunction)
              if f.__module__ == f"core.engines.{e}" and not n.startswith("_")}
    offered = {(v.engine, v.function) for _, v in ALL_VIEWS} | ELSEWHERE
    assert public == offered


@pytest.mark.parametrize("page,view", ALL_VIEWS, ids=[f"{p}:{v.id}" for p, v in ALL_VIEWS])
def test_view_has_a_control_for_every_parameter(page, view):
    params = set(inspect.signature(engine_function(view.engine, view.function)).parameters)
    assert covered(view) == params


@pytest.mark.parametrize("page", list(PAGES))
def test_every_view_draws_a_chart_in_the_app(page):
    prefix = PAGES[page]
    at = open_page(f"pages/{page}.py")
    picker = widget(at, "selectbox", f"x-{prefix}-view")
    for option in picker.options:
        at = set_widget(at, "selectbox", f"x-{prefix}-view", option)
        assert not at.exception, (option, [e.value for e in at.exception])
        assert len(at.get("plotly_chart")) == 1, option
        assert "nirf-empty" not in html_text(at), option


def test_page_category_and_sidebar_stay_in_sync():
    at = open_page("pages/trends.py")
    at = set_widget(at, "selectbox", "x-trends-category", "Pharmacy")
    assert at.session_state["f_category"] == "Pharmacy"
    # The sidebar's widget is keyed f_category; AppTest does not list sidebar widgets of st.navigation apps,
    # so the sidebar change is made through the same session-state value the sidebar widget edits.
    at.session_state["f_category"] = "Management"
    at.session_state["f_years"] = (2017, 2025)
    at.run()
    assert widget(at, "selectbox", "x-trends-category").value == "Management"
    assert "Management" in chart_titles(at)[0]


def test_local_choices_survive_a_category_change():
    at = open_page("pages/distributions.py")
    at = set_widget(at, "selectbox", "x-distributions-score_distribution-year", 2019)
    at = set_widget(at, "selectbox", "x-distributions-category", "Engineering")
    assert widget(at, "selectbox", "x-distributions-score_distribution-year").value == 2019
    at = set_widget(at, "selectbox", "x-distributions-category", "SDG")         # SDG exists only in 2025
    assert widget(at, "selectbox", "x-distributions-score_distribution-year").value == 2025
    assert not at.exception


def test_years_control_writes_the_sidebar_range():
    at = open_page("pages/trends.py")
    at = set_widget(at, "selectbox", "x-trends-view", "Biggest climbers between two years")
    at = set_widget(at, "select_slider", "x-trends-biggest_movers-up-period", (2019, 2023))
    assert tuple(at.session_state["f_years"]) == (2019, 2023)
    assert "2019" in chart_titles(at)[0] or "2019" in html_text(at)


def test_state_filter_is_applied_and_shown():
    at = open_page("pages/mobility.py")
    at = set_widget(at, "multiselect", "x-mobility-states", ["Karnataka"])
    assert at.session_state["f_states"] == ["Karnataka"]
    assert "Among institutions in Karnataka" in html_text(at)


def test_relationships_two_variable_interface():
    at = open_page("pages/relationships.py")
    page = html_text(at)
    for label in ("Pearson r", "Spearman rho", "R²", "p-value", "institutions with both values"):
        assert label in page
    assert any("relationship" in m.value for m in at.markdown)
    at = set_widget(at, "selectbox", "x-relationships-y", "rank")
    assert "better (smaller) rank" in " ".join(m.value for m in at.markdown)
    at = set_widget(at, "selectbox", "x-relationships-color", "category")
    cats = widget(at, "multiselect", "x-relationships-categories")
    assert len(cats.value) == 2
    assert not at.exception and len(at.get("plotly_chart")) == 1
    assert "comparable only within a category" in chart_notes(at)
    at = set_widget(at, "selectbox", "x-relationships-x", "score")
    at = set_widget(at, "selectbox", "x-relationships-y", "score")
    assert "Choose two different numbers" in html_text(at)
