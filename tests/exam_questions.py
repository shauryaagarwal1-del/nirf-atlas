"""Phase 14 exam simulation: 30 NEW examiner questions (not in Annexure A), across all 8 sections.

Written the way a strict examiner asks, with the tricky cases on purpose: an institution missing in
some years, a category that only exists from 2023, a state with only one institution, a start year
after the end year, tied ranks and band-only ranks. Each question is answered twice:

  UI path    the page, the view and the controls a person sets (`widgets`, set in the real app by
             tests/test_exam.py and scripts/exam_simulation.py); the app must draw the same chart as
             `calls` (or show the friendly message in `expect`, when the question has no chart answer);
  Ask NIRF   the typed `question` goes through the chat. `golden` is a correct plan written the way the
             model writes one (names and phrases copied from the question), used offline; the live
             model's own plan is recorded in tests/exam_chat_plans.json. A chat answer passes when it is
             one of the `chat_ok` analyses and runs with the `must` settings (or gives the same message).

expect: "chart" (draw the answer) or a text the answer must contain, for questions the data cannot
answer as asked (e.g. a year before the category existed); `check` is a text the chart's one-line
answer must contain, to show the tricky case was handled (e.g. "101" for a tie at rank 100).
"""

from __future__ import annotations

from dataclasses import dataclass, field

AGRI = "Agriculture & Allied Sectors"
ALL_YEARS = list(range(2017, 2026))


@dataclass(frozen=True)
class Exam:
    id: str
    section: int
    question: str
    tricky: str                         # which tricky case it tests ("" = a plain new question)
    page: str                           # app page file under app/
    view: str | None                    # "What do you want to see?" option (None: the page has a fixed view / tab)
    controls: str                       # the controls in plain words, for docs/exam_simulation.md
    widgets: list                       # (widget type, key prefix, value) set in the app, in this order
    calls: list                         # [(engine, function, params, states)]: the chart(s) the UI must draw
    chat_ok: tuple[str, ...]            # acceptable chat plans ("engine.function")
    golden: dict                        # a correct chat plan
    must: dict = field(default_factory=dict)   # settings the chat's resolved call must have
    expect: str = "chart"
    check: str = ""
    state: dict | None = None           # session state preset before the page opens (e.g. a Geography tab)
    options: tuple | None = None        # (widget type, key prefix, the only values it may offer)


def _e(engine_function: str, **params) -> dict:
    engine, function = engine_function.split(".")
    return {"type": "engine", "engine": engine, "function": function, "params": params}


SECTIONS = {1: "Trends", 2: "Geography", 3: "Univariate", 4: "Bivariate", 5: "Multivariate", 6: "Distribution",
            7: "Mobility", 8: "Outliers"}
MORE = {"geography-tab": "More views"}

EXAM = [
    # ---------- 1. Time series and trends ----------
    Exam("X01", 1, "How has IIM Calcutta's Overall rank changed from 2017 to 2025?", "missing in some years",
         "views/trends.py", "Rank of chosen institutions, year by year", "Institutions = IIM Calcutta",
         [("multiselect", "x-trends-institutions", ["IIM Calcutta"])],
         [("trends", "rank_trajectory", dict(institutions=["IIM Calcutta"], category="Overall", years=ALL_YEARS), None)],
         ("trends.rank_trajectory",), _e("trends.rank_trajectory", institutions=["IIM Calcutta"], years="2017-2025"),
         must={"institutions": ["IIM Calcutta"], "category": "Overall"}, check="not in the Overall list in"),
    Exam("X02", 1, "Show the biggest Overall climbers with start year 2024 and end year 2019.", "start year after end year",
         "views/trends.py", "Biggest climbers between two years", "From year → to year dragged to 2024 → 2019",
         [("select_slider", "x-trends-biggest_movers-up-period", (2024, 2019))],
         [("trends", "biggest_movers", dict(category="Overall", start_year=2019, end_year=2024, direction="up", n=10),
           None)],
         ("trends.biggest_movers", "mobility.biggest_rank_moves"),
         _e("trends.biggest_movers", start_year=2024, end_year=2019, direction="up"),
         must={"start_year": 2019, "end_year": 2024, "year_a": 2019, "year_b": 2024}),
    Exam("X03", 1, "Which Agriculture institutions stayed in the top 10 in every year they were ranked?",
         "category only from 2023", "views/trends.py", "Who stayed in the top N for many years",
         "Category = Agriculture & Allied Sectors (the 'at least … years' slider now stops at 3)",
         [("selectbox", "x-trends-category", AGRI)],
         [("trends", "consistent_top_n", dict(category=AGRI, n=10, min_years=3), None)],
         ("trends.consistent_top_n",), _e("trends.consistent_top_n", category="Agriculture", n=10),
         must={"category": AGRI, "n": 10, "min_years": 3}),
    Exam("X04", 1, "How has the median score of Engineering institutions changed over the years?", "",
         "views/trends.py", "Average or median score per year", "Categories = Engineering; Statistic = Median",
         [("multiselect", "x-trends-average_score_over_time-categories", ["Engineering"]),
          ("segmented_control", "x-trends-average_score_over_time-stat", "median")],
         [("trends", "average_score_over_time", dict(categories=["Engineering"], stat="median"), None)],
         ("trends.average_score_over_time", "distribution.median_iqr_over_time"),
         _e("trends.average_score_over_time", categories="Engineering", stat="median"),
         must={"categories": "Engineering", "category": "Engineering"}),

    # ---------- 2. Geography ----------
    Exam("X05", 2, "How do Mizoram's institutions compare with Meghalaya's in the Overall ranking?",
         "state with one institution; band-only ranks", "views/geography.py", None,
         "Tab State vs State; State A = Mizoram; State B = Meghalaya",
         [("selectbox", "x-geography-state_vs_state-state_a", "Mizoram"),
          ("selectbox", "x-geography-state_vs_state-state_b", "Meghalaya")],
         [("geography", "state_vs_state", dict(states=["Mizoram", "Meghalaya"], category="Overall", years=ALL_YEARS),
           None),
          ("geography", "state_rank_boxes", dict(states=["Mizoram", "Meghalaya"], category="Overall", years=ALL_YEARS),
           None)],
         ("geography.state_vs_state", "geography.compare_states", "geography.state_rank_boxes"),
         _e("geography.state_vs_state", states=["Mizoram", "Meghalaya"]),
         must={"states": ["Mizoram", "Meghalaya"]}, state={"geography-tab": "State vs State"}),
    Exam("X06", 2, "Which states had the most institutions in the Overall top 100 in 2020?", "tied ranks at the cut-off",
         "views/geography.py", "States with the most institutions in the top list",
         "Tab More views; Year = 2020; Top list = 100",
         [("selectbox", "x-geography-state_counts-year", 2020)],
         [("geography", "state_counts", dict(year=2020, category="Overall", top_n=100), None)],
         ("geography.state_counts", "geography.state_map"), _e("geography.state_counts", year=2020, top_n=100),
         must={"year": 2020, "top_n": 100}, check="share rank 100", state=MORE),
    Exam("X07", 2, "Which states gained or lost the most places in the Agriculture top 25 between 2023 and 2025?",
         "category only from 2023", "views/geography.py", "States that gained or lost places in the top list",
         "Tab More views; Category = Agriculture & Allied Sectors; Top list = 25 (years start at 2023 by themselves)",
         [("selectbox", "x-geography-category", AGRI),
          ("select_slider", "x-geography-state_representation_change-top_n", 25)],
         [("geography", "state_representation_change", dict(category=AGRI, start_year=2023, end_year=2025, top_n=25),
           None)],
         ("geography.state_representation_change",),
         _e("geography.state_representation_change", category="agriculture", start_year=2023, end_year=2025,
            top_n=25),
         must={"category": AGRI, "start_year": 2023, "end_year": 2025, "top_n": 25}, state=MORE),
    Exam("X08", 2, "Which states produced the most new Medical institutions in the rankings since 2019?", "",
         "views/geography.py", None, "Tab New entrants; Category = Medical; Years = 2019-2025",
         [("selectbox", "x-geography-category", "Medical"),
          ("select_slider", "x-geography-new_entrants_by_state-years", (2019, 2025))],
         [("geography", "new_entrants_by_state", dict(category="Medical", years=list(range(2019, 2026)),
                                                      by_year=False), None)],
         ("geography.new_entrants_by_state",),
         _e("geography.new_entrants_by_state", category="Medical", years="since 2019"),
         must={"category": "Medical", "years": list(range(2019, 2026))}, state={"geography-tab": "New entrants"}),

    # ---------- 3. Univariate ----------
    Exam("X09", 3, "What are the mean, median, minimum and maximum Overall scores of Goa's institutions in 2018?",
         "state with one institution", "views/distributions.py", "Average, median, minimum and maximum score",
         "Year = 2018; Only states = Goa",
         [("selectbox", "x-distributions-summary_stats-year", 2018), ("multiselect", "x-distributions-states", ["Goa"])],
         [("univariate", "summary_stats", dict(year=2018, category="Overall"), ["Goa"])],
         ("univariate.summary_stats",), _e("univariate.summary_stats", year=2018, states=["Goa"]),
         must={"year": 2018, "states": ["Goa"]}, check="only one institution"),
    Exam("X10", 3, "How many Engineering institutions sit in each rank band in 2024, including those NIRF lists "
                   "only as a band?", "band-only ranks", "views/distributions.py",
         "How many institutions sit in each rank band", "Category = Engineering; Year = 2024",
         [("selectbox", "x-distributions-category", "Engineering"),
          ("selectbox", "x-distributions-rank_distribution-year", 2024)],
         [("univariate", "rank_distribution", dict(year=2024, category="Engineering"), None)],
         ("univariate.rank_distribution",), _e("univariate.rank_distribution", category="engg", year=2024),
         must={"category": "Engineering", "year": 2024}, check="only within bands"),
    Exam("X11", 3, "Show the score distribution of Agriculture institutions in 2020.", "year before the category existed",
         "views/distributions.py", "Score distribution in one year",
         "Category = Agriculture & Allied Sectors: the Year list offers only 2023, 2024, 2025",
         [("selectbox", "x-distributions-category", AGRI)],
         [("univariate", "score_distribution", dict(year=2025, category=AGRI), None)],
         ("univariate.score_distribution",), _e("univariate.score_distribution", category="Agriculture", year=2020),
         expect="2023", options=("selectbox", "x-distributions-score_distribution-year", [2023, 2024, 2025])),
    Exam("X12", 3, "What share of Management institutions falls in each statistical quartile in 2022?", "",
         "views/distributions.py", "Share of institutions in each score quartile",
         "Category = Management; Year = 2022; Quartiles = Statistical Q1/Q2/Q3",
         [("selectbox", "x-distributions-category", "Management"),
          ("selectbox", "x-distributions-quartile_shares-year", 2022),
          ("segmented_control", "x-distributions-quartile_shares-mode", "statistical")],
         [("univariate", "quartile_shares", dict(year=2022, category="Management", mode="statistical"), None)],
         ("univariate.quartile_shares",),
         _e("univariate.quartile_shares", category="Management", year=2022, mode="statistical"),
         must={"category": "Management", "year": 2022, "mode": "statistical"}),

    # ---------- 4. Bivariate ----------
    Exam("X13", 4, "In Medical 2025, how strongly is Perception related to the overall score?", "",
         "views/relationships.py", "Any two numbers: scatterplot and correlation",
         "Category = Medical; Year = 2025; X axis = PR; Y axis = Overall score",
         [("selectbox", "x-relationships-category", "Medical"), ("selectbox", "x-relationships-year", 2025),
          ("selectbox", "x-relationships-x", "pr")],
         [("bivariate", "scatter_relation", dict(x="pr", y="score", year=2025, category="Medical"), None)],
         ("bivariate.scatter_relation",),
         _e("bivariate.scatter_relation", x="perception", y="overall score", category="Medical", year=2025),
         must={"x": "pr", "y": "score", "category": "Medical", "year": 2025}),
    Exam("X14", 4, "Which parameter is most correlated with the overall score in Pharmacy 2019?", "",
         "views/relationships.py", "Which parameter is most linked to the overall score",
         "Category = Pharmacy; Year = 2019",
         [("selectbox", "x-relationships-category", "Pharmacy"),
          ("selectbox", "x-relationships-correlation_with_overall-year", 2019)],
         [("bivariate", "correlation_with_overall", dict(year=2019, category="Pharmacy"), None)],
         ("bivariate.correlation_with_overall",),
         _e("bivariate.correlation_with_overall", category="pharma", year=2019),
         must={"category": "Pharmacy", "year": 2019}),
    Exam("X15", 4, "How is research related to the overall score for institutions in Goa in 2018?",
         "state with one institution", "views/relationships.py", "Any two numbers: scatterplot and correlation",
         "Year = 2018; Only states = Goa (X = RPC, Y = Overall score are the defaults)",
         [("selectbox", "x-relationships-year", 2018), ("multiselect", "x-relationships-states", ["Goa"])],
         [], ("bivariate.scatter_relation",),
         _e("bivariate.scatter_relation", x="research", y="overall score", year=2018, states=["Goa"]),
         expect="at least 3 are needed"),
    Exam("X16", 4, "Has the link between Perception and the overall score in Engineering changed since 2017?", "",
         "views/relationships.py", "How one parameter's link to the overall score changed over the years",
         "Category = Engineering; Parameter = PR",
         [("selectbox", "x-relationships-category", "Engineering"),
          ("selectbox", "x-relationships-correlation_over_time-param", "pr")],
         [("bivariate", "correlation_over_time", dict(param="pr", category="Engineering"), None)],
         ("bivariate.correlation_over_time",),
         _e("bivariate.correlation_over_time", param="perception", category="Engineering"),
         must={"param": "pr", "category": "Engineering"}),

    # ---------- 5. Multivariate ----------
    Exam("X17", 5, "Compare the parameter scores of IIT Indore and KIIT, which were tied at rank 27 in Overall 2025.",
         "tied ranks", "views/multi_parameter.py", "Parameter profile of chosen institutions",
         "Year = 2025; Institutions = IIT Indore, Kalinga Institute of Industrial Technology",
         [("multiselect", "x-multi-institutions", ["IIT Indore", "Kalinga Institute of Industrial Technology"])],
         [("multivariate", "parameter_profile", dict(institutions=["IIT Indore", "Kalinga Institute of Industrial "
                                                                   "Technology"], year=2025, category="Overall"), None)],
         ("multivariate.parameter_profile",),
         _e("multivariate.parameter_profile", institutions=["IIT Indore", "KIIT"], year=2025),
         must={"institutions": ["IIT Indore", "Kalinga Institute of Industrial Technology"], "year": 2025},
         check="share rank 27"),
    Exam("X18", 5, "Which Engineering institutions in 2024 have high Graduation Outcomes but low Research scores?", "",
         "views/multi_parameter.py", "High on one parameter, low on another",
         "Category = Engineering; Year = 2024; High on = GO; Low on = RPC",
         [("selectbox", "x-multi-category", "Engineering"), ("selectbox", "x-multi-gap_finder-year", 2024),
          ("selectbox", "x-multi-gap_finder-param_high", "go"), ("selectbox", "x-multi-gap_finder-param_low", "rpc")],
         [("multivariate", "gap_finder", dict(param_high="go", param_low="rpc", year=2024, category="Engineering"),
           None)],
         ("multivariate.gap_finder",),
         _e("multivariate.gap_finder", param_high="graduation outcomes", param_low="research", year=2024,
            category="Engineering"),
         must={"param_high": "go", "param_low": "rpc", "year": 2024, "category": "Engineering"}),
    Exam("X19", 5, "Which University institutions raised their overall score even though a parameter fell, with start "
                   "year 2022 and end year 2018?", "start year after end year", "views/multi_parameter.py",
         "Overall score rose although a parameter fell",
         "Category = University; From year → to year dragged to 2022 → 2018",
         [("selectbox", "x-multi-category", "University"),
          ("select_slider", "x-multi-improved_despite_decline-period", (2022, 2018))],
         [("multivariate", "improved_despite_decline", dict(category="University", start_year=2018, end_year=2022,
                                                            n=10), None)],
         ("multivariate.improved_despite_decline",),
         _e("multivariate.improved_despite_decline", category="University", start_year=2022, end_year=2018),
         must={"category": "University", "start_year": 2018, "end_year": 2022}),
    Exam("X20", 5, "Which Law institutions have the biggest gap between their strongest and weakest parameter in 2025?",
         "", "views/multi_parameter.py", "Biggest gap between strongest and weakest parameter",
         "Category = Law; Year = 2025; How many institutions = 15",
         [("selectbox", "x-multi-category", "Law"), ("select_slider", "x-multi-strongest_weakest_gap-n", 15)],
         [("multivariate", "strongest_weakest_gap", dict(year=2025, category="Law", n=15), None)],
         ("multivariate.strongest_weakest_gap",),
         _e("multivariate.strongest_weakest_gap", category="Law", year=2025),
         must={"category": "Law", "year": 2025}),

    # ---------- 6. Distributions ----------
    Exam("X21", 6, "How does the score distribution of the top 5 Dental colleges differ from the rest in 2024?", "",
         "views/distributions.py", "Top N versus the rest", "Category = Dental; Year = 2024; Top N group = 5",
         [("selectbox", "x-distributions-category", "Dental"),
          ("selectbox", "x-distributions-top10_vs_rest-year", 2024),
          ("select_slider", "x-distributions-top10_vs_rest-top", 5)],
         [("distribution", "top10_vs_rest", dict(year=2024, category="Dental", top=5), None)],
         ("distribution.top10_vs_rest",), _e("distribution.top10_vs_rest", category="Dental", year=2024, top=5),
         must={"category": "Dental", "year": 2024, "top": 5}),
    Exam("X22", 6, "Among only the top 50, were Overall scores more spread out in 2017 than in 2025?", "",
         "views/distributions.py", "Spread of scores in each year", "Only ranks 1 to … = 50",
         [("select_slider", "x-distributions-dispersion_by_year-top_n", 50)],
         [("distribution", "dispersion_by_year", dict(category="Overall", top_n=50), None)],
         ("distribution.dispersion_by_year", "distribution.median_iqr_over_time"),
         _e("distribution.dispersion_by_year", top_n=50), must={"top_n": 50, "category": "Overall"}),
    Exam("X23", 6, "How do Overall scores differ across states in 2025, including states with only one institution?",
         "state with one institution", "views/distributions.py", "Scores by state",
         "States with at least … institutions = 1",
         [("slider", "x-distributions-score_by_state-min_institutions", 1)],
         [("distribution", "score_by_state", dict(year=2025, category="Overall", min_institutions=1), None)],
         ("distribution.score_by_state",), _e("distribution.score_by_state", year=2025, min_institutions=1),
         must={"year": 2025, "min_institutions": 1}),

    # ---------- 7. Mobility ----------
    Exam("X24", 7, "How many Engineering institutions climbed from outside the top 100 into the top 100 between 2020 "
                   "and 2025?", "band-only ranks", "views/mobility.py",
         "Moves between rank bands from one year to another", "Category = Engineering; From year → to year = 2020 → 2025",
         [("selectbox", "x-mobility-category", "Engineering"),
          ("select_slider", "x-mobility-band_transitions-period", (2020, 2025))],
         [("mobility", "band_transitions", dict(category="Engineering", year_a=2020, year_b=2025), None)],
         ("mobility.band_transitions",),
         _e("mobility.band_transitions", category="engineering", year_a=2020, year_b=2025),
         must={"category": "Engineering", "year_a": 2020, "year_b": 2025}, check="climbed from 101+"),
    Exam("X25", 7, "Which Overall institutions made the largest rank moves between 2025 and 2019?",
         "start year after end year", "views/mobility.py", "Largest climbs and falls between two years",
         "From year → to year dragged to 2025 → 2019",
         [("select_slider", "x-mobility-biggest_rank_moves-period", (2025, 2019))],
         [("mobility", "biggest_rank_moves", dict(category="Overall", year_a=2019, year_b=2025, n=10), None)],
         ("mobility.biggest_rank_moves", "trends.biggest_movers"),
         _e("mobility.biggest_rank_moves", year_a=2025, year_b=2019),
         must={"year_a": 2019, "year_b": 2025, "start_year": 2019, "end_year": 2025}),
    Exam("X26", 7, "What share of Agriculture institutions stayed in the same rank band from one year to the next?",
         "category only from 2023", "views/mobility.py", "Share that stayed in the same band each year",
         "Category = Agriculture & Allied Sectors",
         [("selectbox", "x-mobility-category", AGRI)],
         [("mobility", "band_retention", dict(category=AGRI), None)],
         ("mobility.band_retention",), _e("mobility.band_retention", category="agriculture"),
         must={"category": AGRI}, check="every pair of years"),
    Exam("X27", 7, "Which institutions entered or left the Overall top 100 from one year to the next?",
         "tied ranks at the cut-off", "views/mobility.py", "Entries and exits of the top N, year to year",
         "Top N = 100",
         [("select_slider", "x-mobility-top10_entries_exits-top", 100)],
         [("mobility", "top10_entries_exits", dict(category="Overall", top=100), None)],
         ("mobility.top10_entries_exits",), _e("mobility.top10_entries_exits", top=100),
         must={"top": 100, "category": "Overall"}),

    # ---------- 8. Outliers ----------
    Exam("X28", 8, "Which Engineering institutions had unusually large year-to-year score changes, using |z| above 2.5?",
         "", "views/outliers.py", "Unusually large year-to-year score changes",
         "Category = Engineering; Unusual if |z| is above = 2.5",
         [("selectbox", "x-outliers-category", "Engineering"),
          ("select_slider", "x-outliers-unusual_score_jumps-z_threshold", 2.5)],
         [("outliers", "unusual_score_jumps", dict(category="Engineering", z_threshold=2.5), None)],
         ("outliers.unusual_score_jumps",),
         _e("outliers.unusual_score_jumps", category="Engineering", z_threshold=2.5),
         must={"category": "Engineering", "z_threshold": 2.5}),
    Exam("X29", 8, "Which Pharmacy institutions have unusually volatile ranks compared with their peers, counting only "
                   "those ranked in at least 6 years?", "missing in some years", "views/outliers.py",
         "Unusually volatile ranks compared with peers", "Category = Pharmacy; Ranked in at least … years = 6",
         [("selectbox", "x-outliers-category", "Pharmacy"), ("slider", "x-outliers-volatility_vs_peers-min_years", 6)],
         [("outliers", "volatility_vs_peers", dict(category="Pharmacy", min_years=6), None)],
         ("outliers.volatility_vs_peers",), _e("outliers.volatility_vs_peers", category="Pharmacy", min_years=6),
         must={"category": "Pharmacy", "min_years": 6}),
    Exam("X30", 8, "Which University institutions have a strong Perception score but a relatively poor rank in 2023?",
         "", "views/outliers.py", "Strong parameter, relatively poor rank",
         "Category = University; Year = 2023; Parameter = PR",
         [("selectbox", "x-outliers-category", "University"),
          ("selectbox", "x-outliers-strong_param_poor_rank-year", 2023),
          ("selectbox", "x-outliers-strong_param_poor_rank-param", "pr")],
         [("outliers", "strong_param_poor_rank", dict(param="pr", year=2023, category="University"), None)],
         ("outliers.strong_param_poor_rank",),
         _e("outliers.strong_param_poor_rank", param="perception", year=2023, category="University"),
         must={"param": "pr", "year": 2023, "category": "University"}),
]

PAGE_TITLES = {"views/trends.py": "Trends", "views/geography.py": "Geography", "views/distributions.py": "Distributions",
               "views/relationships.py": "Relationships", "views/multi_parameter.py": "Multi-Parameter",
               "views/mobility.py": "Mobility", "views/outliers.py": "Outliers"}
PREFIX = {"views/trends.py": "trends", "views/geography.py": "geography", "views/distributions.py": "distributions",
          "views/relationships.py": "relationships", "views/multi_parameter.py": "multi",
          "views/mobility.py": "mobility", "views/outliers.py": "outliers"}
