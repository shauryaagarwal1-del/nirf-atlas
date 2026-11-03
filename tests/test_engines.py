"""Engine tests (Phase 6): every analysis function runs on the real master table and answers correctly.

Three kinds of checks:
  1. Every public engine function, called with its defaults, returns a complete ChartResult: a Plotly
     figure with data, a title and the NIRF source note, a non-empty table, an insight, a method
     and a chart type.
  2. Every chart type an engine returns (defaults and other views) is one of the names listed in
     docs/allowed_charts.md, the chart types taught in the course.
  3. Spot checks of the numbers against an independent calculation on the master table (counts,
     means, correlations, improvement = old rank - new rank) and of the friendly error messages.

    python -m pytest tests/test_engines.py -v
"""

import inspect
import re
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from core.data import MASTER_PATH, NirfInputError, filter_df, find_institution, load_master
from core.engines import bivariate, geography, trends, univariate
from core.result import ChartResult
from core.theme import SOURCE_NOTE

if not MASTER_PATH.exists():
    pytest.skip("run `python -m pipeline.clean` first", allow_module_level=True)

ENGINES = [trends, geography, univariate, bivariate]
FUNCTIONS = [
    (module.__name__.split(".")[-1], name, fn)
    for module in ENGINES
    for name, fn in inspect.getmembers(module, inspect.isfunction)
    if fn.__module__ == module.__name__ and not name.startswith("_")
]
ALLOWED_CHARTS_PATH = Path(__file__).resolve().parents[1] / "docs" / "allowed_charts.md"


def allowed_chart_types() -> set[str]:
    """The chart-type names in docs/allowed_charts.md: the backticked name at the start of each list item."""
    text = ALLOWED_CHARTS_PATH.read_text(encoding="utf-8")
    return set(re.findall(r"^- `([^`]+)`", text, flags=re.MULTILINE))


CHART_TYPES = allowed_chart_types()

# Non-default views, so the allowed-chart check also covers every chart type an engine can draw.
VARIANTS = [
    ("trends.rank_trajectory(one institution)", lambda: trends.rank_trajectory("IIT Madras")),
    ("trends.average_score_over_time(show_spread)", lambda: trends.average_score_over_time(show_spread=True)),
    ("trends.average_score_over_time(two categories)",
     lambda: trends.average_score_over_time(["Engineering", "Management"], stat="median")),
    ("bivariate.correlation_with_overall(bar)", lambda: bivariate.correlation_with_overall(view="bar")),
    ("bivariate.scatter_relation(color_by)", lambda: bivariate.scatter_relation(color_by="region")),
    ("univariate.quartile_shares(statistical)", lambda: univariate.quartile_shares(mode="statistical")),
]


@pytest.fixture(scope="module")
def m() -> pd.DataFrame:
    return load_master()


def test_every_requested_function_exists():
    names = {f"{e}.{n}" for e, n, _ in FUNCTIONS}
    expected = {
        "trends.rank_trajectory", "trends.biggest_movers", "trends.average_score_over_time",
        "trends.consistent_top_n",
        "geography.state_counts", "geography.state_share_over_time", "geography.state_representation_change",
        "geography.compare_states", "geography.new_entrants_by_state",
        "univariate.score_distribution", "univariate.rank_distribution", "univariate.summary_stats",
        "univariate.quartile_shares", "univariate.spread_by_category",
        "bivariate.scatter_relation", "bivariate.correlation_with_overall", "bivariate.correlation_over_time",
    }
    assert expected <= names


@pytest.mark.parametrize("engine,name,fn", FUNCTIONS, ids=[f"{e}.{n}" for e, n, _ in FUNCTIONS])
def test_defaults_return_complete_chart_result(engine, name, fn):
    assert fn.__doc__ and fn.__doc__.strip().startswith("Answers questions like:")
    r = fn()
    assert isinstance(r, ChartResult)
    assert isinstance(r.fig, go.Figure) and len(r.fig.data) > 0
    assert r.fig.layout.title.text
    assert any(SOURCE_NOTE in (a.text or "") for a in r.fig.layout.annotations)
    assert isinstance(r.table, pd.DataFrame) and not r.table.empty
    assert isinstance(r.insight, str) and len(r.insight) > 20
    assert isinstance(r.method, str) and len(r.method) > 40
    assert r.chart_type in CHART_TYPES


# ---------- allowed chart types (docs/allowed_charts.md) ----------

def test_allowed_charts_file_lists_the_taught_types():
    assert len(CHART_TYPES) == 38
    for name in ("bar chart", "multi-series line chart", "correlogram", "histogram with density curve",
                 "point plot with error bars", "box-and-whisker plot", "matrix heatmap", "choropleth map"):
        assert name in CHART_TYPES
    for banned in ("sankey", "radar", "spider", "treemap", "sunburst", "waterfall", "funnel", "slope", "dumbbell",
                   "parallel"):
        assert not any(banned in t.lower() for t in CHART_TYPES)


@pytest.mark.parametrize("engine,name,fn", FUNCTIONS, ids=[f"{e}.{n}" for e, n, _ in FUNCTIONS])
def test_default_chart_type_is_allowed(engine, name, fn):
    r = fn()
    assert r.chart_type in CHART_TYPES, (f"{engine}.{name} returns chart_type {r.chart_type!r}, which is not "
                                         f"listed in docs/allowed_charts.md")


@pytest.mark.parametrize("label,call", VARIANTS, ids=[v[0] for v in VARIANTS])
def test_variant_chart_type_is_allowed(label, call):
    r = call()
    assert r.chart_type in CHART_TYPES, (f"{label} returns chart_type {r.chart_type!r}, which is not listed in "
                                         f"docs/allowed_charts.md")


def test_no_banned_plotly_trace_types():
    """No engine draws a trace type that only exists for charts outside the allowed list."""
    banned = {"sankey", "scatterpolar", "parcoords", "parcats", "treemap", "sunburst", "waterfall",
              "funnel", "funnelarea", "icicle"}
    for _, _, fn in FUNCTIONS:
        assert not {t.type for t in fn().fig.data} & banned
    for _, call in VARIANTS:
        assert not {t.type for t in call().fig.data} & banned


# ---------- data helpers ----------

def test_find_institution_handles_short_forms_and_typos():
    madras = find_institution("Indian Institute of Technology Madras")
    assert find_institution("IIT Madras") == madras
    assert find_institution("iit madras") == madras
    assert find_institution("Vellore Institute of Technolgy") == find_institution("Vellore Institute of Technology")
    with pytest.raises(NirfInputError, match="Please be more specific"):
        find_institution("IIT")
    with pytest.raises(NirfInputError, match="No institution called"):
        find_institution("Hogwarts School of Witchcraft")


def test_filter_rank_max_counts_bands_only_when_certain(m):
    # Management 2017: exact ranks 1-50 plus NIRF band 51-75 -> all 75 are certainly in the top 75,
    # while the 76-100 band is not.
    top75 = filter_df(m, years=2017, categories="Management", rank_max=75)
    assert len(top75) == 75
    assert set(top75["rank_band_nirf"].dropna()) == {"51-75"}
    exact = filter_df(m, years=2017, categories="Management", exact_ranks_only=True)
    assert exact["rank"].notna().all()


# ---------- trends ----------

def test_rank_trajectory_iit_madras(m):
    r = trends.rank_trajectory("IIT Madras")
    ranks = dict(zip(r.table["year"], r.table["rank"]))
    assert ranks[2025] == 1 and ranks[2017] == 2
    assert "rank 2 in 2017" in r.insight and "rank 1 in 2025" in r.insight
    assert r.fig.layout.yaxis.range[0] > r.fig.layout.yaxis.range[1]      # reversed: rank 1 on top


def test_rank_trajectory_friendly_errors():
    with pytest.raises(NirfInputError, match="not ranked in Law"):
        trends.rank_trajectory("IIT Madras", category="Law")
    with pytest.raises(NirfInputError, match="no Dental ranking for 2017"):
        trends.rank_trajectory("Maulana Azad Institute of Dental Sciences", category="Dental", years=[2017, 2025])


def test_biggest_movers_uses_old_minus_new(m):
    r = trends.biggest_movers("Overall", 2017, 2025, direction="up", n=10)
    t = r.table
    assert (t["improvement"] == t["rank_start"] - t["rank_end"]).all()
    assert (t["improvement"] > 0).all() and t["improvement"].is_monotonic_decreasing
    down = trends.biggest_movers("Overall", 2017, 2025, direction="down", n=5).table
    assert (down["improvement"] < 0).all()


def test_average_score_matches_direct_mean(m):
    r = trends.average_score_over_time("Overall")
    direct = m[(m["category_std"] == "Overall") & (m["year"] == 2025)]["score"].mean()
    got = r.table.set_index("year").loc[2025, "mean"]
    assert got == pytest.approx(direct, abs=0.01)
    # A plain line with markers: no shaded band (no fill), Q1/Q3 only in the hover.
    assert all(t.mode == "lines+markers" and not t.fill for t in r.fig.data)
    assert "Q1 to Q3" in r.fig.data[0].hovertemplate


def test_average_score_point_plot_error_bars_run_from_q1_to_q3():
    r = trends.average_score_over_time("Overall", stat="median", show_spread=True)
    assert r.chart_type == "point plot with error bars"
    tr, t = r.fig.data[0], r.table
    assert tr.mode == "markers"
    assert np.allclose(np.array(tr.y) + np.array(tr.error_y.array), t["q3"])
    assert np.allclose(np.array(tr.y) - np.array(tr.error_y.arrayminus), t["q1"])


def test_consistent_top_10_includes_iit_madras_every_year():
    t = trends.consistent_top_n("Overall", n=10, min_years=9).table
    assert "IIT Madras" in set(t["institution"])
    assert (t["years_in_top_n"] == 9).all()


# ---------- geography ----------

def test_state_counts_agree_with_pipeline_top100_flag(m):
    r = geography.state_counts(2025, "Overall", 100)
    direct = m[(m["year"] == 2025) & (m["category_std"] == "Overall") & m["in_top100"]].groupby("state").size()
    got = r.table.set_index("state")["institutions"]
    assert got.sort_index().equals(direct.sort_index().astype(got.dtype))


def test_state_shares_add_up_to_100():
    r = geography.state_share_over_time("Overall", 100)
    t = r.table
    assert np.allclose(t.groupby("year")["share_pct"].sum(), 100, atol=0.6)
    # Multi-series line chart: top 8 states + "Other states", no stacking.
    names = [tr.name for tr in r.fig.data]
    assert len(names) == 9 and names[-1] == "Other states"
    assert all(tr.mode == "lines+markers" and not tr.stackgroup for tr in r.fig.data)


def test_representation_change_is_end_minus_start():
    t = geography.state_representation_change("Overall", 2017, 2025).table
    assert (t["change"] == t["count_2025"] - t["count_2017"]).all()


def test_new_entrants_total_matches_flag(m):
    t = geography.new_entrants_by_state("Overall").table
    direct = m[(m["category_std"] == "Overall") & m["is_new_entrant"]].shape[0]
    assert t["total"].sum() == direct


def test_compare_states_rejects_unknown_state():
    with pytest.raises(NirfInputError, match="not a state"):
        geography.compare_states(["Karnataka", "Atlantis"])


# ---------- univariate ----------

def test_summary_stats_match_pandas(m):
    scores = m[(m["category_std"] == "Overall") & (m["year"] == 2025)]["score"].dropna()
    t = univariate.summary_stats(2025, "Overall").table.set_index("statistic")["value"]
    assert t["Mean"] == pytest.approx(scores.mean(), abs=1e-3)
    assert t["Median"] == pytest.approx(scores.median(), abs=1e-3)
    assert t["Minimum"] == pytest.approx(scores.min()) and t["Maximum"] == pytest.approx(scores.max())


@pytest.mark.parametrize("mode", ["score_range", "statistical"])
def test_quartile_shares_add_up(mode):
    t = univariate.quartile_shares(2025, "Overall", mode=mode).table
    assert t["share_pct"].sum() == pytest.approx(100, abs=0.2)
    if mode == "statistical":
        assert t["share_pct"].between(20, 30).all()


def test_rank_distribution_counts_every_ranked_row(m):
    t = univariate.rank_distribution(2025, "Overall").table
    direct = m[(m["category_std"] == "Overall") & (m["year"] == 2025) & m["rank_band"].notna()].shape[0]
    assert t["total"].sum() == direct


def test_score_distribution_has_density_curve_in_count_units(m):
    r = univariate.score_distribution(2025, "Overall")
    assert r.chart_type == "histogram with density curve"
    hist, kde = r.fig.data[0], r.fig.data[1]
    assert hist.type == "histogram" and kde.type == "scatter" and "KDE" in kde.name
    # The scaled curve's area equals the area of the bars: n institutions x bar width.
    n = m[(m["category_std"] == "Overall") & (m["year"] == 2025)]["score"].notna().sum()
    area = np.trapezoid(kde.y, kde.x)
    assert area == pytest.approx(n * hist.xbins.size, rel=0.03)
    assert {a.text.split()[0] for a in r.fig.layout.annotations if a.text} >= {"Mean", "Median"}


def test_categories_without_scores_are_explained():
    with pytest.raises(NirfInputError, match="no overall scores"):
        univariate.score_distribution(2025, "Innovation")


# ---------- bivariate ----------

def test_scatter_correlation_matches_numpy(m):
    r = bivariate.scatter_relation("rpc", "score", 2025, "Overall")
    d = m[(m["category_std"] == "Overall") & (m["year"] == 2025)][["rpc", "score"]].dropna()
    expected = np.corrcoef(d["rpc"], d["score"])[0, 1]
    assert r.table.attrs["stats"]["pearson_r"] == pytest.approx(expected, abs=1e-9)
    assert f"r = {expected:.2f}" in r.insight


def test_scatter_rejects_parameter_not_published():
    with pytest.raises(NirfInputError, match="did not publish TLR"):
        bivariate.scatter_relation("tlr", "score", 2025, "Research Institutions")


def test_correlation_with_overall_bar_view_is_sorted():
    r = bivariate.correlation_with_overall(2025, "Overall", view="bar")
    assert r.chart_type == "bar chart"
    t = r.table
    assert t["pearson_r"].is_monotonic_decreasing
    assert set(t["parameter"]) == {"TLR", "RPC", "GO", "OI", "PR"}


def test_correlogram_is_a_symmetric_matrix_matching_the_bars(m):
    r = bivariate.correlation_with_overall(2025, "Overall")
    assert r.chart_type == "correlogram"
    t = r.table.set_index("variable")
    names = ["Overall score", "TLR", "RPC", "GO", "OI", "PR"]
    assert list(t.index) == names and list(t.columns) == names
    assert np.allclose(np.diag(t.values), 1) and np.allclose(t.values, t.values.T)
    heat = r.fig.data[0]
    assert heat.type == "heatmap" and heat.texttemplate and heat.zmin == -1 and heat.zmax == 1
    bars = bivariate.correlation_with_overall(2025, "Overall", view="bar").table.set_index("parameter")["pearson_r"]
    for p in ["TLR", "RPC", "GO", "OI", "PR"]:
        assert t.at["Overall score", p] == pytest.approx(bars[p], abs=1e-3)
    d = m[(m["category_std"] == "Overall") & (m["year"] == 2025)][["tlr", "pr"]].dropna()
    assert t.at["TLR", "PR"] == pytest.approx(np.corrcoef(d["tlr"], d["pr"])[0, 1], abs=1e-3)
    with pytest.raises(NirfInputError, match="view must be"):
        bivariate.correlation_with_overall(view="pie")


def test_correlogram_uses_research_parameters():
    t = bivariate.correlation_with_overall(2025, "Research Institutions").table
    assert set(t["variable"]) == {"Overall score", "QnR", "QlR", "SFC", "OI", "PR"}


def test_correlation_over_time_covers_every_year():
    t = bivariate.correlation_over_time("rpc", "Overall").table
    assert t["year"].tolist() == list(range(2017, 2026))
