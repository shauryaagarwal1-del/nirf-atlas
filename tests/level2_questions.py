"""The 15 examiner-style Level 2 questions (not in Annexure A) and the UI settings that answer each one.

Each entry says which page and view to open and which controls to set; `call` is the analysis those
settings run (the same engine call the page makes). tests/test_level2.py drives the real app with
these settings, and docs/level2_questions.md lists the questions with their answers.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class L2:
    id: str
    question: str
    page: str                       # app page file under app/
    view: str | None                # "What do you want to see?" option (None: Chart Builder)
    controls: dict                  # control label -> value, as set in the UI
    call: tuple                     # ("engine", "function", params, states) or ("builder", params)
    widgets: list = field(default_factory=list)   # (widget type, key prefix, value) set in the app test


LEVEL2 = [
    L2("E01", "Which states have the most Engineering institutions in the top 50 in 2019?",
       "pages/geography.py", "States with the most institutions in the top list",
       {"Category": "Engineering", "Year": 2019, "Top list (rank cut-off)": 50},
       ("geography", "state_counts", dict(category="Engineering", year=2019, top_n=50), None),
       [("selectbox", "x-geography-category", "Engineering"), ("selectbox", "x-geography-state_counts-year", 2019),
        ("select_slider", "x-geography-state_counts-top_n", 50)]),
    L2("E02", "How have IIT Bombay's and IIT Delhi's Engineering ranks changed since 2017?",
       "pages/trends.py", "Rank of chosen institutions, year by year",
       {"Category": "Engineering", "Institutions": "IIT Bombay, IIT Delhi"},
       ("trends", "rank_trajectory", dict(category="Engineering", institutions=["IIT Bombay", "IIT Delhi"]), None),
       [("selectbox", "x-trends-category", "Engineering"),
        ("multiselect", "x-trends-institutions", ["IIT Bombay", "IIT Delhi"])]),
    L2("E03", "Which Pharmacy institutions climbed the most between 2020 and 2024?",
       "pages/trends.py", "Biggest climbers between two years",
       {"Category": "Pharmacy", "From year → to year": "2020 → 2024", "How many institutions": 10},
       ("trends", "biggest_movers", dict(category="Pharmacy", start_year=2020, end_year=2024, direction="up", n=10),
        None),
       [("selectbox", "x-trends-category", "Pharmacy"), ("select_slider", "x-trends-biggest_movers-up-period", (2020, 2024))]),
    L2("E04", "Among Kerala's institutions in the University ranking, which climbed the most from 2017 to 2025?",
       "pages/trends.py", "Biggest climbers between two years",
       {"Category": "University", "Only states": "Kerala"},
       ("trends", "biggest_movers", dict(category="University", start_year=2017, end_year=2025, direction="up", n=10),
        ["Kerala"]),
       [("selectbox", "x-trends-category", "University"), ("multiselect", "x-trends-states", ["Kerala"])]),
    L2("E05", "How have IIM Ahmedabad's parameter scores changed over the years?",
       "pages/trends.py", "Parameter scores of one institution, year by year",
       {"Category": "Management", "Institution": "IIM Ahmedabad"},
       ("trends", "parameter_trends", dict(category="Management", institution="IIM Ahmedabad"), None),
       [("selectbox", "x-trends-category", "Management"),
        ("selectbox", "x-trends-parameter_trends-institution", "IIM Ahmedabad")]),
    L2("E06", "Which parameter varies the most across Pharmacy institutions in 2023?",
       "pages/distributions.py", "Which parameter varies the most",
       {"Category": "Pharmacy", "Year": 2023},
       ("distribution", "parameter_variability", dict(category="Pharmacy", year=2023), None),
       [("selectbox", "x-distributions-category", "Pharmacy"),
        ("selectbox", "x-distributions-parameter_variability-year", 2023)]),
    L2("E07", "In 2024, is Perception (PR) linked to the overall score more strongly in Engineering or in Management?",
       "pages/relationships.py", "Any two numbers: scatterplot and correlation",
       {"X axis": "PR", "Y axis": "Overall score", "Year": 2024, "Category": "Engineering, then Management"},
       ("bivariate", "scatter_relation", dict(x="pr", y="score", year=2024, category="Engineering"), None),
       [("selectbox", "x-relationships-category", "Engineering"), ("selectbox", "x-relationships-year", 2024),
        ("selectbox", "x-relationships-x", "pr")]),
    L2("E08", "Among the Overall top 50 of 2025, how is Graduation Outcomes (GO) related to rank?",
       "pages/relationships.py", "Any two numbers: scatterplot and correlation",
       {"X axis": "GO", "Y axis": "Rank", "Only ranks 1 to …": 50},
       ("bivariate", "scatter_relation", dict(x="go", y="rank", year=2025, category="Overall", top_n=50), None),
       [("selectbox", "x-relationships-x", "go"), ("selectbox", "x-relationships-y", "rank"),
        ("select_slider", "x-relationships-top", 50)]),
    L2("E09", "How many Engineering institutions moved from the 51-100 band into the top 50 between 2018 and 2025?",
       "pages/mobility.py", "Moves between rank bands from one year to another",
       {"Category": "Engineering", "From year → to year": "2018 → 2025"},
       ("mobility", "band_transitions", dict(category="Engineering", year_a=2018, year_b=2025), None),
       [("selectbox", "x-mobility-category", "Engineering"),
        ("select_slider", "x-mobility-band_transitions-period", (2018, 2025))]),
    L2("E10", "Which Law institutions entered or left the top 5 from one year to the next?",
       "pages/mobility.py", "Entries and exits of the top N, year to year",
       {"Category": "Law", "Top N": 5},
       ("mobility", "top10_entries_exits", dict(category="Law", top=5), None),
       [("selectbox", "x-mobility-category", "Law"), ("select_slider", "x-mobility-top10_entries_exits-top", 5)]),
    L2("E11", "Which University institutions had unusually high research (RPC) for their overall score in 2021, "
              "using |z| > 1.5?",
       "pages/outliers.py", "A parameter unusually high for the overall score",
       {"Category": "University", "Year": 2021, "Parameter": "RPC", "Unusual if |z| is above": 1.5},
       ("outliers", "research_vs_overall_outliers", dict(category="University", year=2021, param="rpc",
                                                        z_threshold=1.5), None),
       [("selectbox", "x-outliers-category", "University"),
        ("selectbox", "x-outliers-research_vs_overall_outliers-year", 2021),
        ("select_slider", "x-outliers-research_vs_overall_outliers-z_threshold", 1.5)]),
    L2("E12", "Which Overall institutions in 2025 score high on Perception but relatively low on Graduation Outcomes?",
       "pages/multi_parameter.py", "High on one parameter, low on another",
       {"High on": "PR", "Low on": "GO", "Year": 2025},
       ("multivariate", "gap_finder", dict(category="Overall", year=2025, param_high="pr", param_low="go"), None),
       [("selectbox", "x-multi-gap_finder-param_high", "pr"), ("selectbox", "x-multi-gap_finder-param_low", "go")]),
    L2("E13", "What share of the Overall top 100 in 2025 does each region hold?",
       "pages/chart_builder.py", None,
       {"Categories": "Overall", "From/To year": "2025", "Rank cut-off": "Top 100", "Chart type": "Pie chart",
        "X axis": "Region", "Aggregation": "Count"},
       ("builder", dict(chart="pie", x="region", agg="count", categories=["Overall"], years=[2025], rank_max=100)),
       [("selectbox", "cb-from", 2025), ("selectbox", "cb-rank", 100), ("selectbox", "cb-chart", "pie"),
        ("selectbox", "cb-x", "region"), ("selectbox", "cb-agg", "count")]),
    L2("E14", "How many institutions entered the Overall ranking for the first time in each year?",
       "pages/chart_builder.py", None,
       {"Quick start": "New entrants per year (stacked bar: X Year, Colour New entrant, Count)"},
       ("builder", dict(chart="stacked_bar", x="year", agg="count", color="new_entrant", categories=["Overall"])),
       [("button", "cb-q-New entrants per year", None)]),
    L2("E15", "How has the average TLR of Engineering institutions in the North and the South changed over time?",
       "pages/chart_builder.py", None,
       {"Categories": "Engineering", "Regions": "North, South", "Chart type": "Line chart", "X axis": "Year",
        "Y axis": "TLR", "Aggregation": "Mean", "Colour / group": "Region"},
       ("builder", dict(chart="line", x="year", y="tlr", agg="mean", color="region", categories=["Engineering"],
                        regions=["North", "South"])),
       [("multiselect", "cb-categories", ["Engineering"]), ("multiselect", "cb-regions", ["North", "South"]),
        ("selectbox", "cb-chart", "line"), ("selectbox", "cb-x", "year"), ("selectbox", "cb-agg", "mean"),
        ("selectbox", "cb-y", "tlr"), ("selectbox", "cb-color", "region")]),
]
