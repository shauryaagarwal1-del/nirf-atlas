"""Question registry: the 40 Annexure A questions (Q1.1-Q8.5), each mapped to the engine call that answers it.

One place that says, for every sample question: which engine function answers it, with which default
parameters, which chart type it draws (a name from docs/allowed_charts.md) and why that chart suits
the question. The dashboard uses it to show "the 40 questions", scripts/run_all_questions.py runs
all of them, and the chatbox can fall back on it. Level 2 questions reuse the same calls with
different parameters: run_question("Q2.1", year=2019, top_n=50).

Defaults: category "Overall" unless the question implies another; years = the full range NIRF
published for that category (2017-2025 for Overall), and the latest year (2025) when the question
is about a single year.
"""

from __future__ import annotations

import importlib
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from core.result import ChartResult
from core.theme import SOURCE_NOTE

ALLOWED_CHARTS = Path(__file__).resolve().parents[1] / "docs" / "allowed_charts.md"

ENGINES = ("trends", "geography", "univariate", "bivariate", "multivariate", "distribution", "mobility", "outliers")
SECTIONS = {
    1: "Time-series and trend analysis",
    2: "Geospatial and regional analysis",
    3: "Univariate analysis",
    4: "Bivariate analysis and correlation",
    5: "Multivariate analysis",
    6: "Distribution and statistical comparison",
    7: "Ranking transitions and institutional mobility",
    8: "Outlier detection and performance gaps",
}
FIRST, LAST = 2017, 2025


@dataclass(frozen=True)
class Question:
    id: str
    section: str
    text: str
    engine: str
    function: str
    default_params: dict = field(default_factory=dict)
    chart_type: str = ""
    why_this_chart: str = ""


def _q(qid: str, text: str, engine: str, function: str, params: dict, chart_type: str, why: str) -> Question:
    return Question(qid, SECTIONS[int(qid[1])], text, engine, function, params, chart_type, why)


QUESTION_REGISTRY: dict[str, Question] = {q.id: q for q in [
    # 1. Time-series and trend analysis
    _q("Q1.1", "How has the overall NIRF ranking of a selected institution changed from 2017 to 2025?",
       "trends", "rank_trajectory",
       {"institutions": ["IIT Madras"], "category": "Overall", "years": list(range(FIRST, LAST + 1))},
       "line chart", "Change over time is read best along a line, with the rank axis reversed so up means better."),
    _q("Q1.2", "Which institutions have shown the greatest improvement in rank over the nine years?",
       "trends", "biggest_movers",
       {"category": "Overall", "start_year": FIRST, "end_year": LAST, "direction": "up", "n": 10},
       "bar chart", "Sorted horizontal bars rank the improvements and leave room for long institution names."),
    _q("Q1.3", "Which institutions have experienced the largest decline in ranking?",
       "trends", "biggest_movers",
       {"category": "Overall", "start_year": FIRST, "end_year": LAST, "direction": "down", "n": 10},
       "bar chart", "Sorted horizontal bars make the size of each fall easy to compare."),
    _q("Q1.4", "How has the average score of institutions changed over time?",
       "trends", "average_score_over_time", {"categories": "Overall", "stat": "mean"},
       "line chart", "A line through the yearly means shows the direction and size of the change over time."),
    _q("Q1.5", "Which institutions have remained consistently in the top 10 across multiple years?",
       "trends", "consistent_top_n", {"category": "Overall", "n": 10, "min_years": 5},
       "matrix heatmap", "An institution x year grid shows at a glance in which years each one was in the top 10."),

    # 2. Geospatial and regional analysis
    _q("Q2.1", "Which states have the highest number of institutions in the top 100?",
       "geography", "state_counts", {"year": LAST, "category": "Overall", "top_n": 100},
       "bar chart", "Counts per state are amounts; sorted bars rank the states from most to fewest."),
    _q("Q2.2", "How is the geographical distribution of top-ranked institutions changing from 2017 to 2025?",
       "geography", "state_share_over_time", {"category": "Overall", "top_n": 100},
       "multi-series line chart", "One line per state's share shows each state's rise or fall from a common baseline."),
    _q("Q2.3", "Which states have improved their representation in the top 100 over time?",
       "geography", "state_representation_change",
       {"category": "Overall", "start_year": FIRST, "end_year": LAST, "top_n": 100},
       "bar chart", "Bars either side of zero separate states that gained places from those that lost them."),
    _q("Q2.4", "How do the rankings of institutions in Karnataka compare with those in Tamil Nadu?",
       "geography", "compare_states", {"states": ["Karnataka", "Tamil Nadu"], "category": "Overall"},
       "box-and-whisker plot", "Side-by-side boxes compare the level and spread of the two states' ranks each year."),
    _q("Q2.5", "Which states have produced the largest number of newly appearing institutions in the rankings?",
       "geography", "new_entrants_by_state", {"category": "Overall"},
       "stacked bar chart", "Each state's bar is its total of new entrants, split by the year they appeared."),

    # 3. Univariate analysis
    _q("Q3.1", "What is the distribution of NIRF scores for a selected year?",
       "univariate", "score_distribution", {"year": LAST, "category": "Overall"},
       "histogram with density curve", "A histogram shows the shape of one numeric variable; the curve smooths it."),
    _q("Q3.2", "What is the distribution of overall ranks across all institutions?",
       "univariate", "rank_distribution", {"year": LAST, "category": "Overall"},
       "stacked bar chart", "Bars per rank band show how many institutions sit where, split into exact and band-only ranks."),
    _q("Q3.3", "What is the average, median, minimum, and maximum score in a given year?",
       "univariate", "summary_stats", {"year": LAST, "category": "Overall"},
       "box-and-whisker plot", "A box plot draws the median, quartiles, minimum and maximum the table reports."),
    _q("Q3.4", "What percentage of ranked institutions fall into each score quartile?",
       "univariate", "quartile_shares", {"year": LAST, "category": "Overall", "mode": "score_range"},
       "stacked bar chart", "One 100% bar split into four parts shows the percentage in each quartile as parts of a whole."),
    _q("Q3.5", "How does the spread of scores differ across NIRF categories?",
       "univariate", "spread_by_category", {"year": LAST},
       "box-and-whisker plot", "One box per category compares spreads (IQR, whiskers, outliers) side by side."),

    # 4. Bivariate analysis and correlation
    _q("Q4.1", "How strongly are Research and Professional Practice (RPC) scores associated with overall scores?",
       "bivariate", "scatter_relation", {"x": "rpc", "y": "score", "year": LAST, "category": "Overall"},
       "scatterplot", "A scatterplot with a trend line is the standard picture of how two numbers move together."),
    _q("Q4.2", "How does Perception (PR) relate to overall scores?",
       "bivariate", "scatter_relation", {"x": "pr", "y": "score", "year": LAST, "category": "Overall"},
       "scatterplot", "Each dot is an institution, so both the trend and the exceptions are visible."),
    _q("Q4.3", "Which NIRF parameter has the strongest correlation with the overall score?",
       "bivariate", "correlation_with_overall", {"year": LAST, "category": "Overall", "view": "correlogram"},
       "correlogram", "A correlation heatmap shows r for every pair, with the overall-score row answering the question."),
    _q("Q4.4", "How are TLR and RPC scores related across institutions?",
       "bivariate", "scatter_relation", {"x": "tlr", "y": "rpc", "year": LAST, "category": "Overall"},
       "scatterplot", "A scatterplot of two parameters shows the strength and shape of their relationship."),
    _q("Q4.5", "Has the correlation between research scores and overall scores changed from 2017 to 2025?",
       "bivariate", "correlation_over_time", {"param": "rpc", "category": "Overall"},
       "multi-series line chart", "Pearson r and Spearman rho by year, as two lines, show how the relationship changed."),

    # 5. Multivariate analysis
    _q("Q5.1", "How do the top five institutions compare across all five NIRF parameters?",
       "multivariate", "parameter_profile", {"institutions": None, "year": LAST, "category": "Overall", "view": "bar"},
       "grouped bar chart", "Grouping bars by parameter compares the five institutions one parameter at a time."),
    _q("Q5.2", "Which institutions have high research scores but relatively low teaching scores?",
       "multivariate", "gap_finder", {"param_high": "rpc", "param_low": "tlr", "year": LAST, "category": "Overall"},
       "scatterplot", "Median lines split the scatterplot into quadrants; the high-RPC, low-TLR corner is the answer."),
    _q("Q5.3", "Which institutions have high teaching scores but relatively low perception scores?",
       "multivariate", "gap_finder", {"param_high": "tlr", "param_low": "pr", "year": LAST, "category": "Overall"},
       "scatterplot", "Median lines split the scatterplot into quadrants; the high-TLR, low-PR corner is the answer."),
    _q("Q5.4", "Which institutions have improved their overall scores despite declining scores in one or more "
               "parameters?",
       "multivariate", "improved_despite_decline", {"category": "Overall", "start_year": FIRST, "end_year": LAST},
       "small-multiple bar charts", "One small chart per institution shows which parameters fell while the overall rose."),
    _q("Q5.5", "Which institutions have the largest difference between their strongest and weakest parameters?",
       "multivariate", "strongest_weakest_gap", {"year": LAST, "category": "Overall", "n": 15},
       "lollipop chart", "A sorted lollipop chart ranks a long list of gaps with less ink than bars."),

    # 6. Distribution and statistical comparison
    _q("Q6.1", "How does the score distribution differ between the top 10 and the remaining institutions?",
       "distribution", "top10_vs_rest", {"year": LAST, "category": "Overall", "view": "violin"},
       "violin plot", "Violins compare the shape of two distributions, and the box inside gives their medians and IQRs."),
    _q("Q6.2", "Are NIRF scores more dispersed in one year than another?",
       "distribution", "dispersion_by_year", {"category": "Overall", "view": "box"},
       "box-and-whisker plot", "One box per year shows the spread directly: a taller box means more dispersed scores."),
    _q("Q6.3", "Which NIRF parameter exhibits the greatest variability across institutions?",
       "distribution", "parameter_variability", {"year": LAST, "category": "Overall", "view": "bar"},
       "bar chart", "A ranked bar chart of the coefficient of variation orders the parameters from most to least variable."),
    _q("Q6.4", "How do the median and interquartile range of scores change over time?",
       "distribution", "median_iqr_over_time", {"category": "Overall"},
       "point plot with error bars", "The point is the median and the error bar runs from Q1 to Q3, exactly the two quantities asked about."),
    _q("Q6.5", "How does the score distribution differ across states?",
       "distribution", "score_by_state", {"year": LAST, "category": "Overall", "min_institutions": 3},
       "box-and-whisker plot", "One box per state, sorted by median, compares level and spread across many groups."),

    # 7. Ranking transitions and institutional mobility
    _q("Q7.1", "How many institutions moved from the 51–100 band into the top 50 between two selected years?",
       "mobility", "band_transitions", {"category": "Overall", "year_a": FIRST, "year_b": LAST},
       "matrix heatmap", "A band x band transition matrix counts every move; the 51-100 to top-50 cells answer the question."),
    _q("Q7.2", "Which institutions entered or exited the top 10 between consecutive years?",
       "mobility", "top10_entries_exits", {"category": "Overall", "top": 10},
       "time-series dot plot", "One row per institution with a dot per top-10 year makes every entry and exit visible."),
    _q("Q7.3", "What percentage of institutions remained in the same rank band from one year to the next?",
       "mobility", "band_retention", {"category": "Overall"},
       "line chart", "A line with one point per year pair shows how the retention percentage changes over time."),
    _q("Q7.4", "Which institutions experienced the largest upward and downward rank movements?",
       "mobility", "biggest_rank_moves", {"category": "Overall", "year_a": FIRST, "year_b": LAST, "n": 10},
       "lollipop chart", "Stems right of zero (up) and left of zero (down) compare the size of climbs and falls."),
    _q("Q7.5", "How many institutions moved up, moved down, or retained their positions each year?",
       "mobility", "up_down_same_counts", {"category": "Overall"},
       "stacked bar chart", "Each year's bar is split into up, same and down, so both the counts and the mix are visible."),

    # 8. Outlier detection and performance gaps
    _q("Q8.1", "Which institutions have unusually high research scores relative to their overall scores?",
       "outliers", "research_vs_overall_outliers", {"year": LAST, "category": "Overall", "param": "rpc"},
       "scatterplot", "Points far above the regression line (residual z > 2) are the unusual ones, and the scatterplot shows them."),
    _q("Q8.2", "Which institutions perform substantially better in research than in teaching?",
       "outliers", "research_over_teaching", {"year": LAST, "category": "Overall", "n": 15},
       "bar chart", "A ranked bar chart of RPC minus TLR puts the biggest research advantages first."),
    _q("Q8.3", "Which institutions experienced an unusually large year-to-year score change?",
       "outliers", "unusual_score_jumps", {"category": "Overall"},
       "jittered strip chart", "Every change is a dot over its year's box plot, so the extreme |z| > 2 changes stand out."),
    _q("Q8.4", "Which institutions have a strong parameter score but a relatively poor overall rank?",
       "outliers", "strong_param_poor_rank", {"param": "go", "year": LAST, "category": "Overall"},
       "scatterplot", "Plotting the parameter against the rank shows the strong-parameter, poor-rank corner directly."),
    _q("Q8.5", "Which institutions have unusually high ranking volatility compared with similar institutions?",
       "outliers", "volatility_vs_peers", {"category": "Overall", "min_years": 4},
       "box-and-whisker plot", "Box plots per peer band define 'unusual' (beyond the whisker) within comparable institutions."),
]}


def get_question(qid: str) -> Question:
    """The registry entry for an ID such as 'Q5.2' (case and spaces ignored)."""
    key = str(qid).strip().upper().replace(" ", "")
    if key not in QUESTION_REGISTRY:
        raise KeyError(f"Unknown question '{qid}'. IDs run from Q1.1 to Q8.5.")
    return QUESTION_REGISTRY[key]


def engine_function(q: Question):
    """The Python function that answers a question (core.engines.<engine>.<function>)."""
    return getattr(importlib.import_module(f"core.engines.{q.engine}"), q.function)


def run_question(qid: str, **overrides) -> ChartResult:
    """Run a question with its default parameters; keyword arguments replace any default (Level 2 changes)."""
    q = get_question(qid)
    return engine_function(q)(**{**q.default_params, **overrides})


@lru_cache(maxsize=1)
def allowed_chart_types() -> frozenset[str]:
    """The chart-type names in docs/allowed_charts.md (the backticked name at the start of each list item)."""
    return frozenset(re.findall(r"^- `([^`]+)`", ALLOWED_CHARTS.read_text(encoding="utf-8"), flags=re.MULTILINE))


def check_result(result, q: Question) -> list[str]:
    """Everything that is wrong with one answer to question `q` (empty list = pass).

    A complete answer has a Plotly figure with data and a title, the NIRF source note, a non-empty
    table, an insight, a method text, and a chart type listed in docs/allowed_charts.md that matches
    the registry. Used by the "Run all 40" grid and scripts/run_all_questions.py.
    """
    problems = []
    if not isinstance(result, ChartResult):
        return [f"returned {type(result).__name__}, not ChartResult"]
    if not isinstance(result.fig, go.Figure) or not result.fig.data:
        problems.append("figure has no data")
    if not result.fig.layout.title.text:
        problems.append("no title")
    if not any(SOURCE_NOTE in (a.text or "") for a in result.fig.layout.annotations):
        problems.append("no source note")
    if not isinstance(result.table, pd.DataFrame) or result.table.empty:
        problems.append("empty table")
    if not result.insight or len(result.insight) < 20:
        problems.append("no insight")
    if not result.method or len(result.method) < 40:
        problems.append("no method")
    if result.chart_type not in allowed_chart_types():
        problems.append(f"chart type '{result.chart_type}' not in docs/allowed_charts.md")
    elif result.chart_type != q.chart_type:
        problems.append(f"chart type '{result.chart_type}' differs from registry '{q.chart_type}'")
    return problems
