"""Engine tests (Phases 6-7): every analysis function runs on the real master table and answers correctly.

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
from core.engines import (bivariate, distribution, geography, mobility, multivariate, outliers, trends,
                          univariate)
from core.result import ChartResult
from core.theme import SOURCE_NOTE

if not MASTER_PATH.exists():
    pytest.skip("run `python -m pipeline.clean` first", allow_module_level=True)

ENGINES = [trends, geography, univariate, bivariate, multivariate, distribution, mobility, outliers]
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
    ("multivariate.parameter_profile(heatmap)", lambda: multivariate.parameter_profile(view="heatmap")),
    ("multivariate.parameter_pca(Research)", lambda: multivariate.parameter_pca(category="Research Institutions")),
    ("distribution.top10_vs_rest(histogram)", lambda: distribution.top10_vs_rest(view="histogram")),
    ("distribution.dispersion_by_year(sd)", lambda: distribution.dispersion_by_year(view="sd")),
    ("distribution.parameter_variability(box)", lambda: distribution.parameter_variability(view="box")),
    ("mobility.band_retention(by_band)", lambda: mobility.band_retention(by_band=True)),
    ("geography.state_counts(ranked)", lambda: geography.state_counts(view="ranked")),
    ("geography.state_share_over_time(lines)", lambda: geography.state_share_over_time(view="lines")),
    ("geography.state_representation_change(ranked)", lambda: geography.state_representation_change(view="ranked")),
    ("geography.compare_states(boxes)", lambda: geography.compare_states(view="boxes")),
    ("geography.new_entrants_by_state(stacked)", lambda: geography.new_entrants_by_state(by_year=True, view="ranked")),
    ("geography.new_entrants_by_state(bars)", lambda: geography.new_entrants_by_state(by_year=False, view="ranked")),
    ("geography.state_vs_state(three states, top 100)",
     lambda: geography.state_vs_state(["Kerala", "Delhi", "Maharashtra"], "Engineering", top_n=100)),
    ("bivariate.scatter_relation(categories pooled)",
     lambda: bivariate.scatter_relation("tlr", "pr", year=2024, category=["Engineering", "Management"],
                                        color_by="category")),
    ("trends.parameter_trends(Research)",
     lambda: trends.parameter_trends("IISc", category="Research Institutions")),
]


@pytest.fixture(scope="module")
def m() -> pd.DataFrame:
    return load_master()


def test_every_requested_function_exists():
    names = {f"{e}.{n}" for e, n, _ in FUNCTIONS}
    expected = {
        "trends.rank_trajectory", "trends.biggest_movers", "trends.average_score_over_time",
        "trends.consistent_top_n", "trends.parameter_trends",
        "geography.state_counts", "geography.state_share_over_time", "geography.state_representation_change",
        "geography.compare_states", "geography.new_entrants_by_state", "geography.state_map",
        "geography.state_vs_state", "geography.state_rank_boxes",
        "univariate.score_distribution", "univariate.rank_distribution", "univariate.summary_stats",
        "univariate.quartile_shares", "univariate.spread_by_category",
        "bivariate.scatter_relation", "bivariate.correlation_with_overall", "bivariate.correlation_over_time",
        "multivariate.parameter_profile", "multivariate.gap_finder", "multivariate.improved_despite_decline",
        "multivariate.strongest_weakest_gap", "multivariate.parameter_pca",
        "distribution.top10_vs_rest", "distribution.dispersion_by_year", "distribution.parameter_variability",
        "distribution.median_iqr_over_time", "distribution.score_by_state",
        "mobility.band_transitions", "mobility.top10_entries_exits", "mobility.band_retention",
        "mobility.biggest_rank_moves", "mobility.up_down_same_counts",
        "outliers.research_vs_overall_outliers", "outliers.research_over_teaching", "outliers.unusual_score_jumps",
        "outliers.strong_param_poor_rank", "outliers.volatility_vs_peers",
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
    assert all(t.mode.startswith("lines+markers") and not t.fill for t in r.fig.data)
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
    r = geography.state_share_over_time("Overall", 100, view="lines")
    t = r.table
    assert np.allclose(t.groupby("year")["share_pct"].sum(), 100, atol=0.6)
    # Multi-series line chart: top 8 states + "Other states", no stacking.
    names = [tr.name for tr in r.fig.data]
    assert len(names) == 9 and names[-1] == "Other states"
    assert all(tr.mode == "lines+markers" and not tr.stackgroup for tr in r.fig.data)
    assert r.chart_type == "multi-series line chart"
    assert r.table.equals(geography.state_share_over_time("Overall", 100).table)     # same numbers as the maps


# ---------- Section 2 on the map (Phase 20) ----------

MAP_CALLS = [
    ("Q2.1", lambda: geography.state_counts(2025, "Overall", 100)),
    ("Q2.2", lambda: geography.state_share_over_time("Overall", 100)),
    ("Q2.3", lambda: geography.state_representation_change("Overall", 2017, 2025, 100)),
    ("Q2.4", lambda: geography.compare_states(["Karnataka", "Tamil Nadu"], "Overall")),
    ("Q2.5", lambda: geography.new_entrants_by_state("Overall")),
]


def _maps(fig):
    return [t for t in fig.data if t.type == "choropleth"]


@pytest.mark.parametrize("qid,call", MAP_CALLS, ids=[c[0] for c in MAP_CALLS])
def test_section2_maps_paint_every_state_in_the_data(m, qid, call):
    from core.geo import state_polygons
    polys, data_states = state_polygons(), set(m["state"].dropna())
    maps = _maps(call().fig)
    assert maps, f"{qid} draws no map"
    for t in maps:
        locations = set(t.locations)
        for s in data_states:
            assert set(polys[s]) <= locations, (qid, s)
        assert len(t.locations) == len(t.z) == len(t.text)


@pytest.mark.parametrize("qid,call", MAP_CALLS, ids=[c[0] for c in MAP_CALLS])
def test_section2_maps_show_india_only(qid, call):
    fig = call().fig
    geos = [k for k in fig.layout if str(k).startswith("geo")]
    assert geos
    for k in geos:
        g = fig.layout[k]
        assert g.visible is False and g.showframe is False            # no world map, no other countries
        assert 60 <= g.lonaxis.range[0] <= 68 and g.lonaxis.range[1] == 98 and g.lataxis.range == (6, 37.5)


def _on_state_labels(fig):
    return [t for t in fig.data if t.type == "scattergeo" and t.meta == "map-label"]


def _callouts(fig):
    return [str(t.text[0]) for t in fig.data if t.type == "scattergeo" and t.mode == "text" and t.meta != "map-label"]


def test_state_counts_map_matches_the_table_and_marks_delhi():
    r = geography.state_counts(2025, "Overall", 100)
    assert r.chart_type == "choropleth map"
    t = r.table.set_index("state")["institutions"]
    z = dict(zip(r.fig.data[0].locations, r.fig.data[0].z))
    assert z["Tamil Nadu"] == t["Tamil Nadu"] and z["Delhi"] == t["Delhi"] and z["Lakshadweep"] == 0
    assert r.fig.data[0].zmin == 0 and r.fig.data[0].zmax == t.max()
    assert r.fig.data[0].colorscale[0][1] == r.fig.data[0].colorscale[1][1]       # 0 has its own grey
    labels = _on_state_labels(r.fig)
    assert labels and 5 <= len(labels[0].text) <= 8                              # numbers on the leading states
    assert f"Delhi: {t['Delhi']}" in _callouts(r.fig)                            # Delhi is written beside the map
    hover = dict(zip(r.fig.data[0].locations, r.fig.data[0].text))
    assert hover["Tamil Nadu"] == f"Tamil Nadu: {t['Tamil Nadu']} institutions in the top 100 (2025)"
    assert "none (grey)" in "".join(r.fig.data[0].colorbar.ticktext)
    ranked = geography.state_counts(2025, "Overall", 100, view="ranked")
    assert ranked.chart_type == "bar chart" and ranked.table.equals(r.table)


def test_state_share_map_is_two_years_on_one_scale():
    r = geography.state_share_over_time("Overall", 100)
    maps = _maps(r.fig)
    assert len(maps) == 2 and maps[0].zmax == maps[1].zmax and maps[0].zmin == maps[1].zmin == 0
    assert maps[0].showscale is False and maps[1].showscale is not False          # one shared colour bar
    first = geography.state_counts(2017, "Overall", 100).table.set_index("state")["institutions"]
    last = geography.state_counts(2025, "Overall", 100).table.set_index("state")["institutions"]
    assert dict(zip(maps[0].locations, maps[0].z))["Tamil Nadu"] == first["Tamil Nadu"]
    assert dict(zip(maps[1].locations, maps[1].z))["Tamil Nadu"] == last["Tamil Nadu"]
    assert maps[0].zmax == max(first.max(), last.max())
    titles = [a.text for a in r.fig.layout.annotations]
    assert "2017" in titles and "2025" in titles


def test_representation_change_map_is_two_directional():
    r = geography.state_representation_change("Overall", 2017, 2025, 100)
    assert r.chart_type == "choropleth map"
    t = r.table.set_index("state")["change"]
    tr = r.fig.data[0]
    z = dict(zip(tr.locations, tr.z))
    assert z["Tamil Nadu"] == t["Tamil Nadu"] and z["Jammu & Kashmir"] == t["Jammu and Kashmir"]
    assert tr.zmid == 0 and tr.zmin == -tr.zmax and tr.zmax == t.abs().max()
    assert "no change" in "".join(tr.colorbar.ticktext)
    labels = _on_state_labels(r.fig)[0]
    assert all(x[0] in "+−" for x in labels.text)                              # "+3", "-2" (real minus sign)
    ranked = geography.state_representation_change("Overall", 2017, 2025, 100, view="ranked")
    assert ranked.chart_type == "bar chart" and ranked.table.equals(r.table)


def test_compare_states_dots_never_place_band_only_institutions(m):
    r = geography.compare_states(["Karnataka", "Tamil Nadu"], "Overall")
    assert r.chart_type == "jittered strip chart"
    rows = m[(m["category_std"] == "Overall") & (m["year"] == 2025) & m["state"].isin(["Karnataka", "Tamil Nadu"])]
    dots = {t.name: t for t in r.fig.data if t.type == "scatter" and t.mode == "markers" and t.marker.symbol != "square"}
    squares = {t.name: t for t in r.fig.data if t.type == "scatter" and t.mode == "markers" and t.marker.symbol == "square"}
    for s in ("Karnataka", "Tamil Nadu"):
        exact = rows[rows["state"].eq(s) & rows["rank"].notna()]
        band = rows[rows["state"].eq(s) & rows["rank"].isna()]
        assert sorted(dots[s].y) == sorted(exact["rank"].astype(float))            # one dot per exact rank
        assert len(squares[s].y) == len(band) and len(set(squares[s].y)) == 1      # band-only: a strip, no rank
        assert max(squares[s].y) > rows["rank"].max()                              # below every real rank
    assert any("counted, not placed" in (a.text or "") for a in r.fig.layout.annotations)
    assert r.fig.layout.yaxis.range[0] > r.fig.layout.yaxis.range[1]              # rank 1 at the top
    assert len(_maps(r.fig)) == 1                                                 # the small map of the two states
    boxes = geography.compare_states(["Karnataka", "Tamil Nadu"], "Overall", view="boxes")
    assert boxes.chart_type == "box-and-whisker plot" and boxes.table.equals(r.table)
    with pytest.raises(NirfInputError, match="dots can only show"):
        geography.compare_states(["Karnataka", "Tamil Nadu"], "Overall", years=[2020, 2021], dots_year=2025)


def test_new_entrants_map_matches_the_totals():
    r = geography.new_entrants_by_state("Overall")
    assert r.chart_type == "choropleth map"
    totals = r.table.set_index("state")["total"]
    z = dict(zip(r.fig.data[0].locations, r.fig.data[0].z))
    assert all(z[p] == totals[s] for s in totals.index for p in geography.state_polygons()[s])
    assert r.fig.data[0].zmax == totals.max()


def test_unknown_view_is_refused():
    with pytest.raises(NirfInputError, match="view must be"):
        geography.state_counts(view="pie")


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


def test_state_map_counts_match_state_counts_and_zero_states_are_grey():
    r = geography.state_map(2025, "Overall", 100)
    bars = geography.state_counts(2025, "Overall", 100).table.set_index("state")["institutions"]
    t = r.table[r.table["year"].eq(2025)].set_index("state")["institutions"]
    assert t.sort_index().equals(bars.sort_index().astype(t.dtype))
    tr = r.fig.data[0]
    z = dict(zip(tr.locations, tr.z))
    assert z["Tamil Nadu"] == bars["Tamil Nadu"] and z["Ladakh"] == 0 and z["Lakshadweep"] == 0
    assert tr.colorscale[0][1] == tr.colorscale[1][1]                   # 0 has its own (grey) colour
    assert tr.zmin == 0 and tr.zmax == r.table["institutions"].max()    # one fixed scale for every year


def test_state_map_animates_every_year_and_opens_on_the_chosen_one():
    r = geography.state_map(2020, "Overall", 50)
    years = list(range(2017, 2026))
    assert [f.name for f in r.fig.frames] == [str(y) for y in years]
    slider = r.fig.layout.sliders[0]
    assert slider.active == years.index(2020) and [s.label for s in slider.steps] == [str(y) for y in years]
    assert [b.label for b in r.fig.layout.updatemenus[0].buttons] == ["▶ Play", "❚❚ Pause"]
    assert "2020" in r.fig.layout.title.text and all(str(y) in f.layout.title.text for y, f in zip(years, r.fig.frames))
    one = r.fig.frames[years.index(2017)].data[0]
    direct = geography.state_counts(2017, "Overall", 50).table.set_index("state")["institutions"]
    assert dict(zip(r.fig.data[0].locations, one.z))["Tamil Nadu"] == direct["Tamil Nadu"]


def test_state_map_single_year_category_has_no_slider():
    r = geography.state_map(category="SDG", top_n=10)
    assert not r.fig.frames and not r.fig.layout.sliders


def test_state_map_paints_both_polygons_of_the_merged_ut():
    tr = geography.state_map(2025, "Overall", 100).fig.data[0]
    assert {"Dadra & Nagar Haveli", "Daman & Diu"} <= set(tr.locations)


def test_state_vs_state_matches_direct_counts_and_medians(m):
    r = geography.state_vs_state(["Karnataka", "Tamil Nadu"], "Overall")
    rows = m[(m["category_std"] == "Overall") & m["state"].isin(["Karnataka", "Tamil Nadu"])]
    direct = rows.groupby(["year", "state"]).size()
    med = rows.groupby(["year", "state"])["rank"].median()
    t = r.table.set_index(["year", "state"])
    assert t["institutions"].equals(direct.reindex(t.index).astype(t["institutions"].dtype))
    assert np.allclose(t["median_rank"], med.reindex(t.index).astype(float))
    assert r.chart_type == "vertically aligned time-series charts"
    assert r.fig.layout.yaxis2.autorange == "reversed"                    # median rank: 1 at the top


def test_state_vs_state_needs_two_different_states():
    with pytest.raises(NirfInputError, match="two different states"):
        geography.state_vs_state(["Kerala", "Kerala"])


def test_state_rank_boxes_quartiles_match_pandas(m):
    t = geography.state_rank_boxes(["Karnataka", "Tamil Nadu"], "Overall").table.set_index("state")
    ranks = m[(m["category_std"] == "Overall") & m["state"].eq("Karnataka")]["rank"].dropna().astype(float)
    assert t.at["Karnataka", "median_rank"] == round(ranks.median(), 1)
    assert t.at["Karnataka", "q1"] == round(ranks.quantile(0.25), 1)
    assert t.at["Karnataka", "institution_years"] == len(ranks)


def test_new_entrants_plain_bars_match_the_stacked_totals():
    stacked = geography.new_entrants_by_state("Overall", view="ranked").table.set_index("state")["total"]
    assert geography.new_entrants_by_state("Overall", view="ranked").chart_type == "stacked bar chart"
    bars = geography.new_entrants_by_state("Overall", by_year=False, view="ranked")
    assert bars.chart_type == "bar chart" and len(bars.fig.data) == 1
    assert dict(zip(bars.fig.data[0].y, bars.fig.data[0].x)) == stacked.to_dict()


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
    assert {a.text.split()[0] for a in r.fig.layout.annotations if a.text} >= {"Average", "Middle"}


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


# ---------- multivariate ----------

def _overall(m: pd.DataFrame, year: int = 2025) -> pd.DataFrame:
    return m[(m["category_std"] == "Overall") & (m["year"] == year)]


def test_parameter_profile_defaults_to_top5_with_published_values(m):
    t = multivariate.parameter_profile(year=2025, category="Overall").table
    direct = _overall(m).dropna(subset=["tlr"]).sort_values(["rank", "canonical_name"]).head(5)
    assert t["full_name"].tolist() == direct["canonical_name"].tolist()
    assert t["TLR"].tolist() == pytest.approx(direct["tlr"].tolist())
    with pytest.raises(NirfInputError, match="view must be"):
        multivariate.parameter_profile(view="radar")


def test_gap_finder_quadrant_uses_medians(m):
    r = multivariate.gap_finder("rpc", "tlr", 2025, "Overall")
    d = _overall(m).dropna(subset=["rpc", "tlr"])
    expected = d[(d["rpc"] > d["rpc"].median()) & (d["tlr"] < d["tlr"].median())]
    assert len(r.table) == len(expected)
    assert set(r.table["full_name"]) == set(expected["canonical_name"])
    assert r.table["z_gap"].is_monotonic_decreasing


def test_improved_despite_decline_rule():
    t = multivariate.improved_despite_decline("Overall", 2024, 2025).table
    assert (t["score_change"] > 0).all()
    changes = t[[c for c in t.columns if c.endswith("_change") and c != "score_change"]]
    assert (changes.min(axis=1) < 0).all()
    assert (t["n_declined"] == (changes < 0).sum(axis=1)).all()


def test_strongest_weakest_gap_is_max_minus_min(m):
    t = multivariate.strongest_weakest_gap(2025, "Overall").table
    vals = _overall(m).dropna(subset=["tlr"])[["tlr", "rpc", "go", "oi", "pr"]]
    assert t["gap"].iloc[0] == pytest.approx((vals.max(axis=1) - vals.min(axis=1)).max(), abs=0.01)
    assert t["gap"].is_monotonic_decreasing


def test_pca_variance_shares_and_pc1_tracks_score():
    t = multivariate.parameter_pca(2025, "Overall").table
    ev = t.attrs["explained_variance"]
    assert len(ev) == 5 and sum(ev) == pytest.approx(1, abs=1e-3)
    assert ev == sorted(ev, reverse=True)
    assert np.corrcoef(t["pc1"], t["score"])[0, 1] > 0.8


# ---------- distribution ----------

def test_top10_vs_rest_groups(m):
    t = distribution.top10_vs_rest(2025, "Overall").table.set_index("group")
    scores = _overall(m).dropna(subset=["score"])
    top = scores[scores["rank"] <= 10]["score"]
    assert t.loc["Top 10", "n"] == len(top)
    assert t.loc["Top 10", "median"] == pytest.approx(top.median(), abs=0.01)
    assert t["n"].sum() == len(scores)


def test_dispersion_by_year_sd_matches_pandas(m):
    t = distribution.dispersion_by_year("Overall").table.set_index("year")
    direct = m[m["category_std"] == "Overall"].groupby("year")["score"].std()
    assert np.allclose(t["std"], direct.loc[t.index], atol=1e-3)


def test_parameter_variability_cv(m):
    t = distribution.parameter_variability(2025, "Overall").table.set_index("parameter")
    pr = _overall(m)["pr"].dropna()
    assert t.at["PR", "cv"] == pytest.approx(pr.std() / pr.mean(), abs=1e-3)
    assert t["cv"].is_monotonic_decreasing


def test_median_iqr_point_plot():
    r = distribution.median_iqr_over_time("Overall")
    assert r.chart_type == "point plot with error bars"
    assert np.allclose(r.table["iqr"], r.table["q3"] - r.table["q1"], atol=0.02)
    assert r.table["year"].tolist() == list(range(2017, 2026))


def test_score_by_state_respects_min_institutions():
    r = distribution.score_by_state(2025, "Overall", min_institutions=3)
    drawn = {tr.name.rsplit(" (", 1)[0] for tr in r.fig.data}
    assert drawn == set(r.table.loc[r.table["n"] >= 3, "state"])


# ---------- mobility ----------

def test_mobility_bands_follow_nirf_bands():
    s = pd.Series([1, 10, 11, 50, 51, 75, 100, 101, 150, np.nan])
    assert mobility._mobility_band(s).tolist() == ["1-10", "1-10", "11-50", "11-50", "51-100", "51-100", "51-100",
                                                   "101+", "101+", "Not ranked"]


def test_band_transitions_counts_51_100_into_top50(m):
    r = mobility.band_transitions("Overall", 2017, 2025)
    o = m[m["category_std"] == "Overall"]
    a = o[(o["year"] == 2017) & o["rank_upper"].between(51, 100)]["institution_key"]
    b = o[(o["year"] == 2025) & o["rank_upper"].le(50)]["institution_key"]
    expected = len(set(a) & set(b))
    t = r.table.set_index("band")
    assert t.loc["2017: 51-100", ["2025: 1-10", "2025: 11-50"]].sum() == expected
    assert f"{expected} Overall institutions moved from the 51-100 band" in r.insight
    # Every institution listed in either year is counted exactly once.
    assert t["total"].sum() == o[o["year"].isin([2017, 2025])]["institution_key"].nunique()


def test_top10_entries_exits_balance_when_top10_is_full():
    t = mobility.top10_entries_exits("Overall").table
    per_year = t.groupby(["year", "change"]).size().unstack(fill_value=0)
    assert (per_year["entered"] == per_year["exited"]).all()      # the top 10 always has 10 places


def test_band_retention_is_a_percentage():
    t = mobility.band_retention("Overall").table
    assert t["retention_pct"].between(0, 100).all()
    assert (t["stayed"] <= t["ranked_both"]).all()
    assert t["year_to"].tolist() == list(range(2018, 2026))


def test_biggest_rank_moves_both_directions():
    r = mobility.biggest_rank_moves("Overall", 2017, 2025, n=5)
    assert r.chart_type == "lollipop chart"
    assert (r.table["improvement"] > 0).sum() == 5 and (r.table["improvement"] < 0).sum() == 5
    assert (r.table["improvement"] == r.table["rank_start"] - r.table["rank_end"]).all()


def test_up_down_same_counts_add_up(m):
    t = mobility.up_down_same_counts("Overall").table
    assert (t["moved_up"] + t["same"] + t["moved_down"] == t["compared"]).all()
    o = m[(m["category_std"] == "Overall") & m["rank"].notna()]
    a = o[o["year"] == 2024].set_index("institution_key")["rank"]
    b = o[o["year"] == 2025].set_index("institution_key")["rank"]
    both = a.index.intersection(b.index)
    row = t.set_index("year_to").loc[2025]
    assert row["moved_up"] == int((a[both] - b[both] > 0).sum())
    assert row["compared"] == len(both)


# ---------- outliers ----------

def test_research_outliers_residual_z(m):
    t = outliers.research_vs_overall_outliers(2025, "Overall").table
    d = _overall(m).dropna(subset=["rpc", "score"])
    slope, intercept = np.polyfit(d["score"], d["rpc"], 1)
    resid = d["rpc"] - (intercept + slope * d["score"])
    assert t["residual_z"].max() == pytest.approx((resid / resid.std()).max(), abs=0.01)
    assert (t["unusual"] == (t["residual_z"] > 2)).all()


def test_research_over_teaching_difference(m):
    t = outliers.research_over_teaching(2025, "Overall").table
    assert np.allclose(t["difference"], t["RPC"] - t["TLR"], atol=0.02)
    d = _overall(m).dropna(subset=["rpc", "tlr"])
    assert t["difference"].iloc[0] == pytest.approx((d["rpc"] - d["tlr"]).max(), abs=0.01)


def test_unusual_score_jumps_are_beyond_two_sd():
    r = outliers.unusual_score_jumps("Overall")
    assert r.chart_type == "jittered strip chart"
    assert (r.table["z"].abs() > 2).all()


def test_strong_param_poor_rank_rule(m):
    t = outliers.strong_param_poor_rank("go", 2025, "Overall").table
    d = _overall(m).dropna(subset=["go", "rank"])
    assert (t["GO"] >= d["go"].quantile(0.75) - 0.01).all()
    assert (t["rank"] > d["rank"].astype(float).median()).all()


def test_volatility_vs_peers_uses_box_plot_rule():
    t = outliers.volatility_vs_peers("Overall").table
    assert (t["unusual"] == (t["rank_sd"] > t["peer_fence_sd"])).all()
    assert (t["years"] >= 4).all()


# ---------- Phase 10 additions ----------

def test_parameter_trends_matches_the_master_table(m):
    r = trends.parameter_trends("IIT Madras", category="Overall")
    key = find_institution("IIT Madras")
    rows = m[m["institution_key"].eq(key) & m["category_std"].eq("Overall")].sort_values("year")
    assert r.table["year"].tolist() == rows["year"].tolist()
    assert np.allclose(r.table["tlr"], rows["tlr"]) and np.allclose(r.table["score"], rows["score"])
    assert len(r.fig.data) == 6                                   # five parameters + the overall score
    gain = rows["pr"].iloc[-1] - rows["pr"].iloc[0]
    assert f"{abs(gain):.1f}" in r.insight


def test_parameter_trends_friendly_errors():
    with pytest.raises(NirfInputError, match="not ranked in Law"):
        trends.parameter_trends("IIT Madras", category="Law")
    with pytest.raises(NirfInputError, match="no parameter scores"):
        trends.parameter_trends(find_innovation_institution(), category="Innovation")


def find_innovation_institution() -> str:
    df = filter_df(load_master(), categories="Innovation")
    return df["institution_key"].iloc[0]


def test_scatter_rank_axis_keeps_both_rank_columns_apart():
    r = bivariate.scatter_relation(x="rank", y="score")
    assert len(set(r.table.columns)) == len(r.table.columns)       # no duplicate 'rank' column
    assert {"published_rank", "rank"} <= set(r.table.columns)
    assert r.table.attrs["stats"]["pearson_r"] < 0                  # higher score, better (smaller) rank


def test_scatter_top_n_keeps_only_certain_top_ranks(m):
    r = bivariate.scatter_relation(x="go", y="score", year=2025, category="Overall", top_n=50)
    expected = filter_df(m, categories="Overall", years=2025, rank_max=50)
    expected = expected[expected["go"].notna() & expected["score"].notna()]
    assert r.table.attrs["stats"]["n"] == len(expected)
    assert "top 50" in r.insight


def test_scatter_pooled_categories_note_and_counts(m):
    r = bivariate.scatter_relation("tlr", "pr", year=2024, category=["Engineering", "Management"],
                                   color_by="category")
    rows = filter_df(m, categories=["Engineering", "Management"], years=2024)
    assert len(r.table) == int((rows["tlr"].notna() & rows["pr"].notna()).sum())
    assert set(r.table["category"]) == {"Engineering", "Management"}
    notes = " ".join(a.text for a in r.fig.layout.annotations)
    assert "comparable only within a category" in notes
