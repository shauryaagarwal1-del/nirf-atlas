"""Edge-case tests for Ask NIRF (Phase 15c): the chat adapts to what the data actually has and says what it did.

No language model is used: each plan is written by hand, the way the model writes it (names, years and
places copied from the question), and run through the same checks and executor as a live question.
Covered:
  * category auto-pick: IIIT Bangalore with no category -> Engineering 2018-2025, with the reason;
  * the years an institution really has: IIT Dharwad 2017-2025 -> 2023-2025, with the reason;
  * band-only colleges: a rank question becomes the band chart (point plot with error bars); a score
    question says NIRF published no scores and offers the band chart; mixed exact/band years are listed;
  * predictions and opinions: a chart of the past with a notice, and who is ahead in the latest year;
  * vague names ("NIT", "Christian Medical College") -> real institutions to pick from; cities -> states;
    a year a category does not have -> the nearest year; institutions sharing no category -> one chart each;
  * short requests: "NIT ranking" -> the NITs in Engineering (the list most NITs are in); a city's colleges
    in one year -> a list with their ranks; "SDG ranking in 2019" -> the 2025 SDG chart;
  * the Ask NIRF page shows the notice, the pick buttons and the band-chart button.

    python -m pytest tests/test_edge_cases.py -v
"""

from __future__ import annotations

import json

import pytest

from core.data import MASTER_PATH, find_institution
from core.engines import trends
from core.questions import allowed_chart_types
from nlq.executor import execute
from nlq.planner import parse_plan

if not MASTER_PATH.exists():
    pytest.skip("run `python -m pipeline.clean` first", allow_module_level=True)

PREDICTION = "I can't predict future rankings; here is how they have done so far."


def ask(params: dict, function: str = "rank_trajectory", engine: str = "trends", question: str = "", **plan):
    """Run a hand-written engine plan exactly like the chat runs the model's plan."""
    p = parse_plan(json.dumps({"type": "engine", "engine": engine, "function": function, "params": params, **plan}))
    return execute(p, question=question)


def call(answer) -> dict:
    return answer.plan["resolved_call"]


# ---------- 1. category auto-pick ----------

def test_iiit_bangalore_without_a_category_uses_engineering():
    a = ask({"institutions": ["IIIT Bangalore"], "years": "2017-2025"},
            question="Give me the line chart for rankings of IIIT Bangalore from 2017-2025")
    assert a.kind == "chart", a.message
    assert call(a)["function"] == "rank_trajectory"
    assert call(a)["params"]["category"] == "Engineering"
    assert call(a)["params"]["years"] == list(range(2018, 2026))
    assert any("not in the Overall ranking" in s and "so I used Engineering" in s for s in a.assumptions)
    assert any(s.startswith("You asked for 2017-2025") and "2018-2025" in s for s in a.assumptions)


def test_the_models_default_overall_does_not_block_the_pick():
    """The model may still write category Overall; if the question never said 'overall', our code picks."""
    a = ask({"institutions": ["IIIT Bangalore"], "category": "Overall"}, question="IIIT Bangalore rank trend",
            assumptions=["Category: Overall, because none was named."])
    assert a.kind == "chart" and call(a)["params"]["category"] == "Engineering"
    assert "Category: Overall, because none was named." not in a.assumptions


def test_overall_is_kept_when_the_institution_is_there_every_year():
    a = ask({"institutions": ["IIT Madras"]}, question="IIT Madras rank")
    assert call(a)["params"]["category"] == "Overall"
    assert not any("so I used" in s for s in a.assumptions)


def test_two_institutions_get_the_category_they_share():
    a = ask({"institutions": ["IIT Mandi", "IIT Jodhpur"]}, question="IIT Mandi vs IIT Jodhpur")
    assert call(a)["params"]["category"] == "Engineering"          # Overall: Jodhpur only 2023-2025, Mandi not 2018
    assert any("share for the most years" in s for s in a.assumptions)


def test_institutions_sharing_no_category_get_one_chart_each():
    a = ask({"institutions": ["IIT Madras", "NLSIU"]}, question="IIT Madras and NLSIU ranks")
    assert a.kind == "chart", a.message
    assert call(a)["params"]["category"] == "Overall" and len(a.more) == 1
    assert "Law" in a.more[0].fig.layout.title.subtitle.text
    assert any("share no NIRF ranking list" in s and "not comparable" in s for s in a.assumptions)


# ---------- 2. the years an institution actually has ----------

def test_iit_dharwad_shows_only_the_years_it_is_ranked():
    a = ask({"institutions": ["IIT Dharwad"], "category": "Engineering", "years": "2017-2025"})
    assert a.kind == "chart", a.message
    assert call(a)["params"]["years"] == [2023, 2024, 2025]
    assert ("You asked for 2017-2025; IIT Dharwad is ranked in Engineering only in 2023-2025, so the chart shows "
            "those years.") in a.assumptions


def test_a_year_the_category_does_not_have_moves_to_the_nearest():
    a = ask({"category": "SDG", "year": 2019}, function="state_counts", engine="geography")
    assert a.kind == "chart", a.message
    assert call(a)["params"]["year"] == 2025
    assert any(s.startswith("SDG rankings exist only for 2025, so 2025 is shown") for s in a.assumptions)
    a = ask({"category": "Dental", "year": 2018}, function="score_distribution", engine="univariate")
    assert call(a)["params"]["year"] == 2020 and any("nearest to 2018" in s for s in a.assumptions)


def test_a_range_partly_before_a_category_started_is_cut_and_said():
    a = ask({"category": "Research Institutions", "years": "2017-2025"}, function="top_n_race")
    assert call(a)["params"]["years"] == [2021, 2022, 2023, 2024, 2025]
    assert any("Research Institutions rankings exist only for 2021-2025" in s for s in a.assumptions)


# ---------- 3. band-only colleges ----------

def test_a_band_only_college_gets_the_band_chart():
    a = ask({"institutions": ["Bangalore Institute of Technology"]}, question="Bangalore Institute of Technology rank")
    assert a.kind == "chart", a.message
    assert call(a)["function"] == "band_history" and call(a)["params"]["category"] == "Engineering"
    assert a.result.chart_type == "point plot with error bars"
    assert "201-250 in 2020" in a.result.insight and "251-300 in 2021" in a.result.insight
    assert any("only rank bands" in s for s in a.assumptions)


def test_band_history_draws_bars_not_lines():
    r = trends.band_history("Bangalore Institute of Technology", category="Engineering")
    assert r.chart_type in allowed_chart_types()
    assert all("lines" not in (t.mode or "") for t in r.fig.data)       # no line through a band
    bars = [t for t in r.fig.data if t.error_y and t.error_y.array is not None]
    assert bars and list(bars[0].y - bars[0].error_y.array) == [201, 251]       # bar = band's best to worst rank
    assert r.fig.layout.yaxis.range[0] > r.fig.layout.yaxis.range[1]           # reversed: rank 1 on top
    assert set(r.table["band"]) == {"201-250", "251-300"}
    assert "an exact rank line cannot be drawn" in r.insight


def test_band_history_shows_exact_ranks_as_points():
    r = trends.band_history("IIT Dharwad", category="Engineering")
    assert "101-150 in 2024" in r.insight and "93 in 2023 and 77 in 2025" in r.insight
    assert sorted(r.table.loc[r.table["shown_as"].eq("exact rank"), "year"]) == [2023, 2025]


def test_rank_line_lists_the_band_only_years():
    a = ask({"institutions": ["IIT Dharwad"], "category": "Engineering"})
    assert call(a)["function"] == "rank_trajectory"
    assert "In 2024 it was placed only in the 101-150 band." in a.result.insight
    r = trends.rank_trajectory(["IIT Dharwad", "IIT Mandi"], category="Engineering")
    assert "Years placed only in a NIRF band: IIT Dharwad 2024 (101-150)" in r.insight


def test_a_score_question_about_a_band_only_college_says_no_scores():
    a = ask({"institution": "Bangalore Institute of Technology"}, function="parameter_trends",
            question="Bangalore Institute of Technology parameter scores")
    assert a.kind == "no_scores"
    assert "NIRF did not publish scores" in a.message and "201-250 in 2020" in a.message
    assert a.next_plan["function"] == "band_history" and a.next_label
    follow = execute(parse_plan(json.dumps(a.next_plan)), question=a.next_plan["title"])
    assert follow.kind == "chart" and follow.result.chart_type == "point plot with error bars"


# ---------- 4. predictions and opinions ----------

def test_a_prediction_gets_the_past_and_a_notice():
    a = ask({"institutions": ["IIT Mandi", "IIT Jodhpur"]}, question="Will IIT Mandi overtake IIT Jodhpur?",
            notice=PREDICTION)
    assert a.kind == "chart", a.message
    assert a.notice == PREDICTION
    assert "In 2025, IIT Mandi (rank 26) was ahead of IIT Jodhpur (rank 27) by 1 place" in a.result.insight
    assert a.result.table["year"].max() <= 2025                       # no forecast year


def test_an_opinion_question_gets_the_comparison():
    a = ask({"institutions": ["IIT Madras", "IIT Bombay"]}, question="Which is better, IIT Madras or IIT Bombay?",
            notice="I can't judge which is better; here is how they compare in the NIRF rankings.")
    assert a.kind == "chart" and a.notice.startswith("I can't judge")
    assert "IIT Madras (rank 1) was ahead of IIT Bombay" in a.result.insight


# ---------- 5. vague names, cities ----------

def test_a_family_name_alone_asks_which_one():
    a = ask({"institutions": ["NIT"]}, question="NIT rank trend")
    assert a.kind == "clarify" and "31 institutions" in a.message
    assert 2 <= len(a.alternatives) <= 4
    assert a.alternatives[0]["key"] == find_institution("NIT Trichy")         # best known first
    assert all(c["picked"] and c["typed"] == "NIT" for c in a.alternatives)


def test_two_campuses_with_one_name_ask_which_one():
    a = ask({"institutions": ["Christian Medical College"]})
    assert a.kind == "clarify"
    labels = [c["label"] for c in a.alternatives]
    assert len(labels) == 2 and len(set(labels)) == 2 and "Christian Medical College (Vellore)" in labels


def test_a_city_is_read_as_its_state():
    a = ask({"states": ["Bangalore"]}, question="How have Bangalore colleges' ranks changed?")
    assert a.kind == "chart", a.message
    assert call(a)["states"] == ["Karnataka"]
    assert "'Bangalore' = Karnataka (we filter by state, not city)." in a.assumptions
    a = ask({"states": ["Pune"]}, function="state_counts", engine="geography")
    assert call(a)["params"].get("states") is None and "'Pune' = Maharashtra" in " ".join(a.assumptions)


# ---------- 6. short requests (Phase 15f live check) ----------

@pytest.mark.parametrize("types, category", [(["NIT"], "Engineering"), (["IIM"], "Management"),
                                             (["NLU"], "Law"), (["AIIMS"], "Medical")])
def test_a_type_of_institute_alone_uses_the_list_most_of_them_are_in(types, category):
    a = ask({"institute_types": types}, function="top_n_race", question=f"{types[0]} ranking")
    assert a.kind == "chart", a.message
    assert call(a)["params"]["category"] == category and call(a)["institute_types"] == types
    assert any(s.endswith(f"so I used {category}.") for s in a.assumptions)
    assert a.result.insight.startswith("Among")


def test_a_named_category_beats_the_type_pick():
    a = ask({"institute_types": ["NIT"], "category": "Overall"}, function="top_n_race",
            question="NIT ranking in the overall list")
    assert call(a)["params"]["category"] == "Overall"


def test_colleges_of_a_city_in_one_year_are_listed_with_their_ranks():
    a = ask({"states": ["Bangalore"], "category": "Engineering", "years": [2025]}, function="top_n_race",
            question="Bangalore colleges in engineering 2025")
    assert a.kind == "chart", a.message
    assert call(a)["states"] == ["Karnataka"]
    n = len(a.result.table)
    assert 0 < n < 10
    title = a.result.fig.layout.title.text
    assert f"{n} Engineering institutions with an exact rank" in title and "top 10" not in title
    assert a.result.insight.count("(") >= n          # every institution is listed with its rank


def test_top_n_every_year_counts_within_the_list_and_never_a_missing_year():
    from core.runner import run
    r = run("trends", "top_n_race", {"category": "Overall"}, states=["Karnataka"])
    year_cols = [c for c in r.table.columns if str(c).isdigit()]
    every_year = int(r.table[year_cols].notna().all(axis=1).sum())   # all of them are in Karnataka's top 10
    assert 0 < every_year < len(r.table) < 10
    assert f"{every_year} of these {len(r.table)} were among the list's top 10" in r.insight
    r = run("trends", "top_n_race", {"category": "Engineering"}, types=["NIT"])
    assert "0 of these 10" not in r.insight                          # the top 10 NITs, not the national top 10


def test_sdg_2019_is_a_chart_of_2025():
    a = ask({"category": "SDG", "years": [2019]}, function="top_n_race", question="SDG ranking in 2019")
    assert a.kind == "chart", a.message
    assert call(a)["params"]["years"] == [2025]
    assert any(s.startswith("SDG rankings exist only for 2025") for s in a.assumptions)


def test_the_planner_rules_cover_short_requests_and_two_questions():
    from nlq.planner import RULES
    for text in ("NIT ranking", "Bangalore colleges in engineering 2025", "SDG ranking in 2019",
                 "Your message asks two things"):
        assert text in RULES


# ---------- the page ----------

def _page(monkeypatch, plan_dict):
    from streamlit.testing.v1 import AppTest

    import nlq.planner
    import streamlit as st
    from nlq import llm
    from tests.app_helpers import HOME

    st.cache_data.clear()
    plan = parse_plan(json.dumps(plan_dict))
    monkeypatch.setattr(nlq.planner, "plan_question", lambda q, history=None: plan)
    monkeypatch.setattr(llm, "check_connection", lambda: (True, "Key loaded and working · test"))
    at = AppTest.from_file(str(HOME), default_timeout=180)
    at.switch_page("views/ask_nirf.py")
    return at.run()


def _html(at) -> str:
    return " ".join(h.proto.body for h in at.get("html") if not h.proto.body.lstrip().startswith("<style>"))


def test_page_shows_the_notice_above_the_chart(monkeypatch):
    at = _page(monkeypatch, {"type": "engine", "engine": "trends", "function": "rank_trajectory",
                             "params": {"institutions": ["IIT Mandi", "IIT Jodhpur"]}, "notice": PREDICTION})
    at.chat_input[0].set_value("Will IIT Mandi overtake IIT Jodhpur?").run()
    assert not at.exception
    assert "Please note" in _html(at) and "predict future rankings" in _html(at)
    assert len(at.get("plotly_chart")) == 1


def test_page_offers_real_institutions_for_a_vague_name(monkeypatch):
    at = _page(monkeypatch, {"type": "engine", "engine": "trends", "function": "rank_trajectory",
                             "params": {"institutions": ["NIT"]}})
    at.chat_input[0].set_value("NIT rank trend").run()
    assert not at.exception and not at.get("plotly_chart")
    pick = [b for b in at.button if b.label == "NIT Tiruchirappalli"]
    assert pick, [b.label for b in at.button]
    pick[0].click().run()
    assert not at.exception and len(at.get("plotly_chart")) == 1
    assert "You picked NIT Tiruchirappalli for &#x27;NIT&#x27;." in _html(at) or \
        "You picked NIT Tiruchirappalli for 'NIT'." in _html(at)


def test_page_offers_the_band_chart_when_there_are_no_scores(monkeypatch):
    at = _page(monkeypatch, {"type": "engine", "engine": "trends", "function": "parameter_trends",
                             "params": {"institution": "Bangalore Institute of Technology"}})
    at.chat_input[0].set_value("Bangalore Institute of Technology parameter scores").run()
    assert not at.exception and "NIRF published no scores here" in _html(at)
    button = [b for b in at.button if b.label == "Show the rank bands chart"]
    assert button
    button[0].click().run()
    assert not at.exception and len(at.get("plotly_chart")) == 1
