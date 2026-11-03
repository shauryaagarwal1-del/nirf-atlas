"""Geography: where the ranked institutions are and how the map changes (engine: core/engines/geography.py).

Every geography function is one entry of "What do you want to see?", with controls for all of its
parameters (app/explorer.py).
"""

from app.components import page_header
from app.explorer import CATEGORY, PERIOD, SCOPE, TOP_CUT, YEAR, YEARS_RANGE, C, View, explore

DEFAULT_STATES = ("Karnataka", "Tamil Nadu")

VIEWS = [
    View("States with the most institutions in the top list", "geography", "state_counts",
         (CATEGORY, YEAR, TOP_CUT, SCOPE)),
    View("Each state's share of the top list over time", "geography", "state_share_over_time",
         (CATEGORY, TOP_CUT, SCOPE)),
    View("States that gained or lost places in the top list", "geography", "state_representation_change",
         (CATEGORY, PERIOD, TOP_CUT, SCOPE)),
    View("Compare the ranks of chosen states", "geography", "compare_states",
         (CATEGORY, C("states", default=DEFAULT_STATES), YEARS_RANGE),
         hint="No states chosen = Karnataka and Tamil Nadu. Pick up to 8 states."),
    View("States with the most new entrants", "geography", "new_entrants_by_state",
         (CATEGORY, YEARS_RANGE, SCOPE)),
]

page_header("Geography", "Which states hold the top places, how their share changes over the years, and how "
            "two or more states compare.", eyebrow="Explore · Regions")
explore("geography", VIEWS)
