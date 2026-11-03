"""Question Bank page tests (Phase 9): every one of the 40 questions opens and draws its chart in the real app.

Uses Streamlit's AppTest, which runs app/Home.py headless (no browser), so the page is tested exactly as
the dashboard runs it. Checked:
  * each deep link ?q=Q1.1 ... ?q=Q8.5 opens that question with no error, one chart and its controls;
  * changing a control (Level 2) redraws the chart and offers a reset;
  * picking another question updates the address, so the link can be copied;
  * "Run all 40" shows 40 ticks and 40 mini previews;
  * an unknown ID in the link falls back to Q1.1 without an error.

    python -m pytest tests/test_question_bank.py -v
"""

from pathlib import Path

import pytest

from core.data import MASTER_PATH
from core.questions import QUESTION_REGISTRY

if not MASTER_PATH.exists():
    pytest.skip("run `python -m pipeline.clean` first", allow_module_level=True)

from streamlit.testing.v1 import AppTest  # noqa: E402

HOME = Path(__file__).resolve().parents[1] / "app" / "Home.py"
PAGE = "pages/question_bank.py"


def open_page(qid: str | None = None) -> AppTest:
    at = AppTest.from_file(str(HOME), default_timeout=180)
    at.switch_page(PAGE)
    if qid:
        at.query_params["q"] = qid
    return at.run()


def html_text(at: AppTest) -> str:
    return " ".join(h.proto.body for h in at.get("html"))


def charts(at: AppTest) -> list:
    return at.get("plotly_chart")


@pytest.mark.parametrize("qid", list(QUESTION_REGISTRY))
def test_deep_link_opens_question_with_chart(qid):
    at = open_page(qid)
    q = QUESTION_REGISTRY[qid]
    assert not at.exception, [e.value for e in at.exception]
    assert len(charts(at)) == 1
    page = html_text(at)
    assert f"<span class='nirf-q-id'>{qid}</span>" in page
    assert "Why this chart?" in page
    assert "nirf-empty" not in page                      # the default parameters always give an answer
    assert f"<span class='nirf-badge'>{q.chart_type}</span>" in page
    assert at.query_params["q"] == qid
    picked = [r.value for r in at.radio if r.key and r.key.startswith("qb-pick-")]
    assert picked == [qid]


def test_controls_match_the_question():
    at = open_page("Q7.1")
    assert [s.label for s in at.selectbox] == ["Category", "From year", "To year"]
    at = open_page("Q5.2")
    assert [s.label for s in at.selectbox] == ["Category", "Year", "High parameter", "Low parameter"]
    at = open_page("Q1.1")
    assert [m.label for m in at.multiselect if m.key and m.key.startswith("qb-")] == ["Institutions"]


def test_changing_a_control_redraws_and_offers_reset():
    at = open_page("Q7.1")
    reset = at.button(key="qb-reset-Q7.1")
    assert reset.disabled
    at.selectbox(key="qb-Q7.1-year_a-Overall").set_value(2019).run()
    assert not at.exception
    assert len(charts(at)) == 1
    assert "2019" in html_text(at)
    assert not at.button(key="qb-reset-Q7.1").disabled
    at.button(key="qb-reset-Q7.1").click().run()
    assert at.selectbox(key="qb-Q7.1-year_a-Overall").value == 2017


def test_changing_category_keeps_the_page_working():
    at = open_page("Q4.1")
    at.selectbox(key="qb-Q4.1-category").set_value("Research Institutions").run()
    assert not at.exception
    assert at.selectbox(key="qb-Q4.1-x-Research Institutions").value == "qnr"   # RPC does not exist there
    assert len(charts(at)) == 1


def test_picking_a_question_updates_the_link():
    at = open_page("Q4.3")
    at.radio(key="qb-pick-4").set_value("Q4.5").run()
    assert not at.exception
    assert at.query_params["q"] == "Q4.5"
    assert "<span class='nirf-q-id'>Q4.5</span>" in html_text(at)


def test_unknown_link_falls_back_to_first_question():
    at = open_page("Q9.9")
    assert not at.exception
    assert at.query_params["q"] == "Q1.1"


def test_run_all_40_grid():
    at = open_page()
    at.button(key="qb-runall").click().run()
    assert not at.exception
    page = html_text(at)
    assert "<b>40 / 40</b>" in page
    assert page.count("nirf-tick ok") == 40
    assert len(charts(at)) == 40
    at.button(key="qb-open-Q6.4").click().run()
    assert at.query_params["q"] == "Q6.4"
    assert len(charts(at)) == 1
