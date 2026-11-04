"""Mobility: movement between rank bands and in and out of the top (engine: core/engines/mobility.py).

Every mobility function is one entry of "What do you want to see?", with controls for all of its
parameters (app/explorer.py).
"""

from app.components import page_header
from app.explorer import CATEGORY, PERIOD_AB, SCOPE, C, View, explore, how_many, top_n

VIEWS = [
    View("Moves between rank bands from one year to another", "mobility", "band_transitions",
         (CATEGORY, PERIOD_AB, SCOPE)),
    View("Entries and exits of the top N, year to year", "mobility", "top10_entries_exits",
         (CATEGORY, top_n("top", "Top N", (3, 5, 10, 15, 20, 25, 50, 100)), SCOPE)),
    View("Share that stayed in the same band each year", "mobility", "band_retention",
         (CATEGORY, C("choice", "by_band", "Split by band", default=False, widget="toggle"), SCOPE)),
    View("Largest climbs and falls between two years", "mobility", "biggest_rank_moves",
         (CATEGORY, PERIOD_AB, how_many("n", "How many each way"), SCOPE)),
    View("Moved up, down or stayed, each year", "mobility", "up_down_same_counts", (CATEGORY, SCOPE)),
]

page_header("Mobility", "How institutions move: between rank bands from one year to another, in and out of the "
            "top N, and how many moved up, down or stayed each year.", eyebrow="Explore · Rank transitions")
explore("mobility", VIEWS)
