"""Outliers: institutions that break the pattern (engine: core/engines/outliers.py).

Every outliers function is one entry of "What do you want to see?", with controls for all of its
parameters (app/explorer.py).
"""

from app.components import page_header
from app.explorer import CATEGORY, SCOPE, YEAR, Z_THRESHOLD, C, View, explore, how_many, param


def labels(default: int) -> C:
    return C("choice", "max_labels", "Names shown on the chart", list(range(0, 21)), default, widget="slider")


VIEWS = [
    View("A parameter unusually high for the overall score", "outliers", "research_vs_overall_outliers",
         (CATEGORY, YEAR, param("param", "Parameter", "rpc"), Z_THRESHOLD, SCOPE)),
    View("Research much stronger than teaching", "outliers", "research_over_teaching",
         (CATEGORY, YEAR, how_many("n", "How many institutions", (5, 10, 15, 20, 25, 30)), SCOPE)),
    View("Unusually large year-to-year score changes", "outliers", "unusual_score_jumps",
         (CATEGORY, Z_THRESHOLD, labels(12), SCOPE)),
    View("Strong parameter, relatively poor rank", "outliers", "strong_param_poor_rank",
         (CATEGORY, YEAR, param("param", "Parameter", "go"), labels(10), SCOPE)),
    View("Unusually volatile ranks compared with peers", "outliers", "volatility_vs_peers",
         (CATEGORY, C("choice", "min_years", "Ranked in at least … years", "years2", 4), SCOPE)),
]

page_header("Outliers", "Institutions that break the pattern: a parameter far above what the overall score "
            "predicts, unusual year-to-year jumps, strong parameters with weak ranks, and unstable ranks.",
            eyebrow="Explore · Outliers & gaps")
explore("outliers", VIEWS)
