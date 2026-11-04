"""33 varied questions for the Ask NIRF chat, with the analysis each one should be planned as.

Mixed on purpose: typos ("imporved", "corelation"), informal and Hinglish phrasing ("Kaun se institutes
hamesha top 10 mein rahe?"), short forms (iitb, TN, engg, yrs), a custom group-and-summarise question
and an out-of-scope one. N26-N33 are the edge cases of Phase 15c: an institution not in the Overall
ranking, years before an institution existed, a band-only college, predictions and opinions, a vague name
and a city used as a place. For each:
  expected   the acceptable plans: "engine.function" names, or "custom" / "out_of_scope" / "clarify";
  golden     a correct plan as the model should write it (names and phrases copied from the question),
             used offline to check that our resolver and executor answer it;
  answer     what our code answers with it: "chart" (default), "clarify" or "out_of_scope".
tests/test_nlq.py runs the golden plans always, and the live model on every question when a Gemini key
is available; scripts/nlq_accuracy.py prints the accuracy report.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NLQ:
    id: str
    question: str
    expected: tuple[str, ...]
    golden: dict
    style: str          # what makes the question hard: typo, hinglish, abbreviation, informal, plain ...
    answer: str = "chart"


def _e(engine_function: str, notice: str = "", **params) -> dict:
    engine, function = engine_function.split(".")
    return {"type": "engine", "engine": engine, "function": function, "params": params, "notice": notice}


PREDICT = "I can't predict future rankings; here is how they have done so far."
OPINION = "I can't judge which is better; here is how they compare in the NIRF rankings."


NLQ_QUESTIONS = [
    NLQ("N01", "How has IIT Bombay's rank changed from 2017 to 2025?", ("trends.rank_trajectory",),
        _e("trends.rank_trajectory", institutions=["IIT Bombay"], years="2017-2025"), "plain"),
    NLQ("N02", "iitb vs iitd ranking trend", ("trends.rank_trajectory",),
        _e("trends.rank_trajectory", institutions=["iitb", "iitd"]), "abbreviation"),
    NLQ("N03", "which institutes imporved the most in rank since 2017", ("trends.biggest_movers",
        "mobility.biggest_rank_moves"), _e("trends.biggest_movers", start_year="since 2017", direction="up"), "typo"),
    NLQ("N04", "biggest fallers in engg rankings in the last 3 years", ("trends.biggest_movers",
        "mobility.biggest_rank_moves"),
        _e("trends.biggest_movers", category="engg", years="last 3 years", direction="down"), "abbreviation"),
    NLQ("N05", "avg score of universities over the yrs", ("trends.average_score_over_time",),
        _e("trends.average_score_over_time", categories="universities"), "informal"),
    NLQ("N06", "Kaun se institutes hamesha top 10 mein rahe?", ("trends.consistent_top_n",),
        _e("trends.consistent_top_n", n=10), "hinglish"),
    NLQ("N07", "which state has the most top 100 colleges in 2024", ("geography.state_counts",
        "geography.state_map"), _e("geography.state_counts", year=2024, top_n=100), "plain"),
    NLQ("N08", "Karnataka vs TN rankings comparison", ("geography.compare_states", "geography.state_vs_state",
        "geography.state_rank_boxes"), _e("geography.compare_states", states=["Karnataka", "TN"]), "abbreviation"),
    NLQ("N09", "Which states added the most new institutes to the rankings?", ("geography.new_entrants_by_state",),
        _e("geography.new_entrants_by_state"), "plain"),
    NLQ("N10", "show me the distribution of NIRF scores in 2023", ("univariate.score_distribution",),
        _e("univariate.score_distribution", year=2023), "plain"),
    NLQ("N11", "mean median min max score of management institutes 2022", ("univariate.summary_stats",),
        _e("univariate.summary_stats", category="management", year=2022), "informal"),
    NLQ("N12", "how strongly is research related to overall score?", ("bivariate.scatter_relation",),
        _e("bivariate.scatter_relation", x="research", y="overall score"), "plain"),
    NLQ("N13", "which parameter has the biggest corelation with total score", ("bivariate.correlation_with_overall",),
        _e("bivariate.correlation_with_overall"), "typo"),
    NLQ("N14", "has the research vs overall score correlation changed over time?",
        ("bivariate.correlation_over_time",), _e("bivariate.correlation_over_time", param="research"), "plain"),
    NLQ("N15", "compare top 5 institutes on TLR RPC GO OI PR", ("multivariate.parameter_profile",),
        _e("multivariate.parameter_profile"), "abbreviation"),
    NLQ("N16", "colleges with high research but low teaching scores", ("multivariate.gap_finder",
        "outliers.research_over_teaching"), _e("multivariate.gap_finder", param_high="research", param_low="teaching"),
        "informal"),
    NLQ("N17", "top 10 vs baaki sab ka score distribution kaisa hai", ("distribution.top10_vs_rest",),
        _e("distribution.top10_vs_rest"), "hinglish"),
    NLQ("N18", "which parameter varies the most across institutions?", ("distribution.parameter_variability",),
        _e("distribution.parameter_variability"), "plain"),
    NLQ("N19", "how many institutes moved from 51-100 into the top 50 between 2018 and 2024",
        ("mobility.band_transitions",), _e("mobility.band_transitions", year_a=2018, year_b=2024), "plain"),
    NLQ("N20", "who entered or dropped out of the top 10 in pharmacy", ("mobility.top10_entries_exits",),
        _e("mobility.top10_entries_exits", category="pharmacy"), "informal"),
    NLQ("N21", "how many institutions moved up, down or stayed the same each yr?", ("mobility.up_down_same_counts",),
        _e("mobility.up_down_same_counts"), "abbreviation"),
    NLQ("N22", "any institutes with crazy big score jumps from one year to the next?",
        ("outliers.unusual_score_jumps",), _e("outliers.unusual_score_jumps"), "informal"),
    NLQ("N23", "pichhle 5 saal mein Kerala ke top colleges ka rank kaise badla?", ("trends.rank_trajectory",),
        _e("trends.rank_trajectory", states=["Kerala"], years="pichhle 5 saal"), "hinglish"),
    NLQ("N24", "average score by region in 2025 as a bar chart", ("custom",),
        {"type": "custom", "filters": {"categories": ["Overall"], "years": 2025}, "group_by": ["region"],
         "metric": "score", "agg": "mean", "chart": "bar"}, "custom"),
    NLQ("N25", "what's the weather in Delhi today?", ("out_of_scope",),
        {"type": "out_of_scope", "message": "The weather is not part of the NIRF data."}, "out of scope"),
    # ---------- edge cases (Phase 15c) ----------
    NLQ("N26", "Give me the line chart for rankings of IIIT Bangalore from 2017-2025", ("trends.rank_trajectory",),
        _e("trends.rank_trajectory", institutions=["IIIT Bangalore"], years="2017-2025"), "not in Overall"),
    NLQ("N27", "IIT Dharwad engineering rank from 2017 to 2025", ("trends.rank_trajectory",),
        _e("trends.rank_trajectory", institutions=["IIT Dharwad"], category="engineering", years="2017-2025"),
        "years missing"),
    NLQ("N28", "How has Bangalore Institute of Technology's rank changed?", ("trends.rank_trajectory",
        "trends.band_history"), _e("trends.rank_trajectory", institutions=["Bangalore Institute of Technology"]),
        "band only"),
    NLQ("N29", "Will IIT Mandi overtake IIT Jodhpur?", ("trends.rank_trajectory",),
        _e("trends.rank_trajectory", notice=PREDICT, institutions=["IIT Mandi", "IIT Jodhpur"]), "prediction"),
    NLQ("N30", "Who will be #1 in 2026?", ("trends.top_n_race", "trends.rank_trajectory", "trends.consistent_top_n"),
        _e("trends.top_n_race", notice=PREDICT, n=5), "prediction"),
    NLQ("N31", "Which is better, IIT Madras or IIT Bombay?", ("trends.rank_trajectory",
        "multivariate.parameter_profile"),
        _e("trends.rank_trajectory", notice=OPINION, institutions=["IIT Madras", "IIT Bombay"]), "opinion"),
    NLQ("N32", "rank trend of NIT", ("trends.rank_trajectory", "clarify"),
        _e("trends.rank_trajectory", institutions=["NIT"]), "vague name", answer="clarify"),
    NLQ("N33", "How have Bangalore colleges' ranks changed?", ("trends.rank_trajectory",),
        _e("trends.rank_trajectory", states=["Bangalore"]), "city as place"),
]


def plan_label(plan) -> str:
    """'engine.function' for an engine plan, otherwise the plan type ('custom', 'out_of_scope', 'clarify')."""
    return f"{plan.engine}.{plan.function}" if plan.type == "engine" else plan.type
