"""Chart Builder tests (Phase 10): core/builder.py and the Chart Builder page.

Checked:
  * every chart type in the builder draws a complete chart whose chart type is in docs/allowed_charts.md;
  * the numbers match an independent pandas calculation (counts = distinct institutions, means, pie shares,
    rank cut-off, new entrants);
  * combinations that cannot work give a friendly hint (BuilderHint), never a crash;
  * the page runs headless: every quick start draws one chart, and a bad combination shows a hint.

    python -m pytest tests/test_builder.py -v
"""

from pathlib import Path

import numpy as np
import pytest

from core.builder import CHARTS, BuilderHint, build_chart
from core.data import MASTER_PATH, filter_df, load_master
from core.theme import SOURCE_NOTE
from tests.test_engines import CHART_TYPES

if not MASTER_PATH.exists():
    pytest.skip("run `python -m pipeline.clean` first", allow_module_level=True)

HOME = Path(__file__).resolve().parents[1] / "app" / "Home.py"

GOOD = {
    "bar": dict(x="state", agg="count", categories=["Engineering"], years=[2024]),
    "grouped_bar": dict(x="region", y="score", agg="median", color="year", categories=["Overall"], years=[2017, 2025]),
    "stacked_bar": dict(x="year", agg="count", color="region", categories=["Overall"], rank_max=100),
    "line": dict(x="year", y="pr", agg="mean", color="category", categories=["Engineering", "Management"]),
    "scatter": dict(x="go", y="score", color="region", categories=["College"], years=[2025]),
    "bubble": dict(x="tlr", y="rpc", size="pr", categories=["Engineering"], years=[2025], rank_max=50),
    "box": dict(x="region", y="score", categories=["Pharmacy"], years=[2025]),
    "violin": dict(x="year", y="oi", categories=["Overall"]),
    "histogram": dict(x="score", color="region", categories=["Management"], years=[2025]),
    "strip": dict(x="rank_band", y="pr", categories=["Overall"], years=[2025]),
    "heatmap": dict(x="year", agg="count", color="state", categories=["Engineering"], rank_max=100),
    "pie": dict(x="region", agg="count", categories=["Overall"], years=[2025], rank_max=100),
}


@pytest.mark.parametrize("chart", list(CHARTS))
def test_every_chart_type_draws_an_allowed_complete_chart(chart):
    r = build_chart(chart, **GOOD[chart])
    assert r.chart_type in CHART_TYPES
    assert len(r.fig.data) > 0 and r.fig.layout.title.text
    assert any(SOURCE_NOTE in (a.text or "") for a in r.fig.layout.annotations)
    assert not r.table.empty and len(r.insight) > 20 and len(r.method) > 40


def test_facets_make_small_multiples_and_stay_allowed():
    r = build_chart("bar", x="region", y="score", agg="mean", facet="year", categories=["University"])
    assert r.chart_type == "small-multiple bar charts" in CHART_TYPES
    r = build_chart("box", x="state", y="score", facet="category", categories=["Engineering", "Pharmacy"],
                    years=[2025], states=["Tamil Nadu", "Karnataka"])
    assert r.chart_type in CHART_TYPES


def test_count_is_distinct_institutions_per_group():
    r = build_chart("bar", x="state", agg="count", categories=["Engineering"], years=[2024])
    rows = filter_df(load_master(), categories="Engineering", years=2024)
    expected = rows.groupby("state")["institution_key"].nunique()
    got = r.table.set_index("state")["value"]
    assert (got == expected.reindex(got.index)).all() and got.sum() == expected.sum()


def test_mean_matches_pandas():
    r = build_chart("bar", x="region", y="tlr", agg="mean", categories=["Overall"], years=[2025])
    rows = filter_df(load_master(), categories="Overall", years=2025)
    expected = rows.groupby("region")["tlr"].mean()
    got = r.table.set_index("region")["value"]
    assert np.allclose(got.values, expected.reindex(got.index).values)


def test_pie_shares_and_rank_cut_off():
    r = build_chart("pie", x="region", agg="count", categories=["Overall"], years=[2025], rank_max=100)
    rows = filter_df(load_master(), categories="Overall", years=2025, rank_max=100)
    assert r.table["institutions"].sum() == rows["institution_key"].nunique()
    shares = r.fig.data[0].values / r.fig.data[0].values.sum()
    assert abs(shares.sum() - 1) < 1e-9


def test_new_entrant_groups_match_the_pipeline_flag():
    r = build_chart("stacked_bar", x="year", agg="count", color="new_entrant", categories=["Overall"])
    rows = filter_df(load_master(), categories="Overall")
    new = r.table[r.table["new_entrant"].eq("New entrant")].set_index("year")["value"]
    expected = rows[rows["is_new_entrant"]].groupby("year")["institution_key"].nunique()
    assert (new == expected.reindex(new.index)).all()
    assert r.fig.layout.title.text.startswith("Most new entrants")


def test_limit_keeps_the_largest_groups():
    r = build_chart("bar", x="institution", y="rpc", agg="max", categories=["Overall"], years=[2025], limit=10)
    assert len(r.table) == 10
    rows = filter_df(load_master(), categories="Overall", years=2025)
    assert np.isclose(r.table["value"].min(), rows["rpc"].nlargest(10).min())


def test_cross_category_scores_get_the_note():
    r = build_chart("line", x="year", y="pr", agg="mean", color="category", categories=["Engineering", "Pharmacy"])
    assert any("comparable only within a category" in (a.text or "") for a in r.fig.layout.annotations)


@pytest.mark.parametrize("spec,words", [
    (dict(chart="pie", x="region", agg="mean"), "only works with Count"),
    (dict(chart="line", x="state", y="score"), "X must be Year"),
    (dict(chart="histogram", x="state"), "needs a number on the X axis"),
    (dict(chart="scatter", x="score", y="score"), "two different numbers"),
    (dict(chart="grouped_bar", x="state", y="score"), "needs a second grouping"),
    (dict(chart="stacked_bar", x="state", y="score", color="region", agg="mean"), "grouped bar chart"),
    (dict(chart="box", x="score", y="pr"), "needs groups on the X axis"),
    (dict(chart="bar", x="state", y="tlr", categories=["Innovation"]), "published no TLR"),
    (dict(chart="bar", x="state", color="state", agg="count"), "must be different groups"),
    (dict(chart="bar", x="state", agg="count", categories=["Law"], states=["Goa"]), "No rows match"),
    (dict(chart="bubble", x="tlr", y="rpc", size=None), "bubble size"),
])
def test_bad_combinations_give_friendly_hints(spec, words):
    with pytest.raises(BuilderHint, match=words):
        build_chart(**spec)


def test_unused_options_are_ignored_with_a_note():
    r = build_chart("pie", x="region", agg="count", color="state", facet="year", categories=["Overall"])
    notes = " ".join(r.table.attrs["notes"])
    assert "Colour is not used" in notes and "Facets are not available" in notes


# ---------- the page ----------

def _page():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(HOME), default_timeout=180)
    at.switch_page("pages/chart_builder.py")
    return at.run()


def _html(at) -> str:
    return " ".join(h.proto.body for h in at.get("html"))


def test_page_quick_starts_each_draw_a_chart():
    at = _page()
    assert not at.exception and len(at.get("plotly_chart")) == 1
    for key in [b.key for b in at.button if (b.key or "").startswith("cb-q-")]:
        at.button(key=key).click().run()
        assert not at.exception, key
        assert len(at.get("plotly_chart")) == 1, key
        assert "nirf-empty" not in _html(at), key


def test_page_shows_a_hint_for_a_bad_combination():
    at = _page()
    at.selectbox(key="cb-chart").set_value("line").run()
    at.selectbox(key="cb-x").set_value("state").run()
    assert not at.exception
    assert len(at.get("plotly_chart")) == 0
    assert "X must be Year" in _html(at)
