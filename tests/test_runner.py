"""State scope tests (Phase 10): core/runner.py and core.data.only_states().

Checked:
  * inside only_states() every load_master() returns only that state's rows, and the scope ends after the block;
  * a scoped analysis equals the same analysis computed by hand on that state's rows;
  * the answer names the states (subtitle, insight, method), so a "Kerala only" chart is never mistaken for India;
  * friendly messages when a state has no institution in a category; only engine functions can be run.

    python -m pytest tests/test_runner.py -v
"""

import pytest

from core.data import MASTER_PATH, NirfInputError, current_states, filter_df, load_master, only_states
from core.runner import run

if not MASTER_PATH.exists():
    pytest.skip("run `python -m pipeline.clean` first", allow_module_level=True)


def test_only_states_limits_load_master_and_resets():
    with only_states(["kerala"]) as scope:                 # spelling is checked and standardised
        assert scope == ("Kerala",)
        assert current_states() == ("Kerala",)
        assert set(load_master()["state"]) == {"Kerala"}
    assert current_states() is None
    assert load_master()["state"].nunique() > 20


def test_scoped_biggest_movers_matches_a_manual_calculation():
    r = run("trends", "biggest_movers", dict(category="Engineering", start_year=2017, end_year=2025, n=5),
            states=["Tamil Nadu"])
    m = filter_df(load_master(), categories="Engineering", states="Tamil Nadu", years=[2017, 2025],
                  exact_ranks_only=True)
    ranks = m.pivot_table(index="institution_key", columns="year", values="rank").dropna()
    best = (ranks[2017] - ranks[2025]).max()
    assert f"+{int(best)} places" in r.insight
    assert len(r.table) <= len(ranks)                      # only Tamil Nadu institutions can be in the table


def test_scoped_answer_names_the_states():
    r = run("univariate", "score_distribution", dict(category="Overall", year=2025),
            states=["Karnataka", "Tamil Nadu"])
    assert r.insight.startswith("Among institutions in Karnataka and Tamil Nadu:")
    assert r.fig.layout.title.subtitle.text.startswith("Only institutions in Karnataka and Tamil Nadu")
    assert "national NIRF ranks" in r.method


def test_scope_is_ignored_by_functions_with_their_own_states():
    a = run("geography", "compare_states", dict(states=["Kerala", "Goa"]), states=["Delhi"])
    assert "Delhi" not in a.insight


def test_scoped_friendly_messages():
    with pytest.raises(NirfInputError, match="No institution in Goa is ranked in Law"):
        run("trends", "biggest_movers", dict(category="Law"), states=["Goa"])
    with pytest.raises(NirfInputError, match="Only institutions in Kerala are included"):
        run("trends", "consistent_top_n", dict(category="Overall", n=10, min_years=5), states=["Kerala"])


def test_only_engine_functions_can_run():
    with pytest.raises(NirfInputError):
        run("os", "system", {})
    with pytest.raises(NirfInputError):
        run("trends", "_where_ranked", {})
    with pytest.raises(NirfInputError):
        run("trends", "load_master", {})                     # imported helper, not an analysis
