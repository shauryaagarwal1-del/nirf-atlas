"""Multi-Parameter: all five NIRF parameters at once (engine: core/engines/multivariate.py).

Every multivariate function is one entry of "What do you want to see?", with controls for all of its
parameters (app/explorer.py).
"""

from app.components import page_header
from app.explorer import CATEGORY, INSTITUTIONS, PERIOD, SCOPE, YEAR, C, View, explore, how_many, param, variant

VIEWS = [
    View("Parameter profile of chosen institutions", "multivariate", "parameter_profile",
         (CATEGORY, YEAR, INSTITUTIONS, variant("view", "Chart", {"bar": "Grouped bars", "heatmap": "Heatmap"}, "bar"),
          SCOPE),
         hint="No institutions chosen = the top 5 of that year (of the chosen states, if any)."),
    View("High on one parameter, low on another", "multivariate", "gap_finder",
         (CATEGORY, YEAR, param("param_high", "High on", "rpc"), param("param_low", "Low on", "tlr"),
          C("choice", "n_labels", "Names shown on the chart", list(range(0, 16)), 6, widget="slider"), SCOPE)),
    View("Overall score rose although a parameter fell", "multivariate", "improved_despite_decline",
         (CATEGORY, PERIOD, how_many("n", "How many institutions", (5, 10, 12, 15, 20, 25, 30)), SCOPE)),
    View("Biggest gap between strongest and weakest parameter", "multivariate", "strongest_weakest_gap",
         (CATEGORY, YEAR, how_many("n", "How many institutions", (5, 10, 15, 20, 25, 30)), SCOPE)),
    View("Map of institutions by all parameters (PCA)", "multivariate", "parameter_pca", (CATEGORY, YEAR, SCOPE)),
]

page_header("Multi-Parameter", "All five parameters at once: institution profiles, high-on-one-but-low-on-another "
            "gaps, overall gains despite weaker parameters, and the spread between strongest and weakest.",
            eyebrow="Explore · Multivariate")
explore("multi", VIEWS)
