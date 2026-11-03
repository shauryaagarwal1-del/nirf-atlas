"""Engine tests (Phase 6): every analysis function runs on the real master table and answers correctly.

Two kinds of checks:
  1. Every public engine function, called with its defaults, returns a complete ChartResult: a Plotly
     figure with data, a title and the NIRF source note, a non-empty table, an insight, a method
     and a chart type.
  2. Spot checks of the numbers against an independent calculation on the master table (counts,
     means, correlations, improvement = old rank - new rank) and of the friendly error messages.

    python -m pytest tests/test_engines.py -v
"""

import inspect

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
CHART_TYPES = {"line", "bar", "area", "box", "heatmap", "histogram", "scatter"}


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
    t = geography.state_share_over_time("Overall", 100).table
    assert np.allclose(t.groupby("year")["share_pct"].sum(), 100, atol=0.6)


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


def test_correlation_with_overall_is_sorted():
    t = bivariate.correlation_with_overall(2025, "Overall").table
    assert t["pearson_r"].is_monotonic_decreasing
    assert set(t["parameter"]) == {"TLR", "RPC", "GO", "OI", "PR"}


def test_correlation_over_time_covers_every_year():
    t = bivariate.correlation_over_time("rpc", "Overall").table
    assert t["year"].tolist() == list(range(2017, 2026))
