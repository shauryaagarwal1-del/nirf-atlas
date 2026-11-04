"""Trends: how ranks and scores changed over the years (engine: core/engines/trends.py).

Every trends function is one entry of "What do you want to see?", with controls for all of its
parameters (app/explorer.py).
"""

from app.components import page_header
from app.explorer import (CATEGORY, INSTITUTIONS, PERIOD, SCOPE, TOP_ONLY, YEARS_RANGE, C, View, explore, how_many,
                          top_n)

VIEWS = [
    View("Rank of chosen institutions, year by year", "trends", "rank_trajectory",
         (CATEGORY, INSTITUTIONS, YEARS_RANGE, SCOPE),
         hint="No institutions chosen = the top 5 of the last year (of the chosen states, if any)."),
    View("Parameter scores of one institution, year by year", "trends", "parameter_trends",
         (CATEGORY, C("institution"), YEARS_RANGE),
         why="A multi-series line chart puts each parameter's path over time on one score axis (all are out of "
             "100), so gains and falls are easy to compare; the dashed line is the overall score."),
    View("Biggest climbers between two years", "trends", "biggest_movers",
         (CATEGORY, PERIOD, how_many(), SCOPE), fixed={"direction": "up"}),
    View("Biggest fallers between two years", "trends", "biggest_movers",
         (CATEGORY, PERIOD, how_many(), SCOPE), fixed={"direction": "down"}),
    View("Average or median score per year", "trends", "average_score_over_time",
         (C("categories"), C("choice", "stat", "Statistic", {"mean": "Mean", "median": "Median"}, "mean",
                             widget="segmented"),
          TOP_ONLY, C("choice", "show_spread", "Show Q1–Q3 as error bars", default=False, widget="toggle"), SCOPE),
         hint="Add categories to compare their averages; scores of different categories are on different scales."),
    View("Who stayed in the top N for many years", "trends", "consistent_top_n",
         (CATEGORY, top_n("n", "Top N"),
          C("choice", "min_years", "In the top N for at least … years", "years", 5), SCOPE)),
    View("Today's top N, followed back in time", "trends", "top_n_race",
         (CATEGORY, YEARS_RANGE, how_many("n", "Top N of the last year", (3, 5, 10, 15, 20)),
          C("choice", "highlight", "Coloured lines", list(range(0, 9)), 3, widget="slider",
            help="The best this many are coloured; the others are grey context lines."),
          C("choice", "depth", "Rank axis down to", {None: "Auto", 25: "25", 50: "50", 100: "100", 200: "200"}, None,
            help="Auto = 2.5 × N (deeper when a state filter is on)."), SCOPE)),
]

page_header("Trends", "How ranks and scores moved over time: one institution's path, the biggest climbers and "
            "fallers, the average score each year, and who stayed at the top.", eyebrow="Explore · Time series")
explore("trends", VIEWS)
