"""Relationships: how two NIRF numbers move together (engine: core/engines/bivariate.py).

The first view is the "select any two variables" interface asked for in the project statement: X and
Y over every numeric column (overall score, the parameters, rank), colour by state / region / category /
rank band, category and year filters, an optional state filter and a trend-line toggle. Above the
scatterplot, metric cards give Pearson r, Spearman rho, R squared, the p-value and n, with a one-line
interpretation in plain words. The other two views are the remaining bivariate functions, with all
their knobs (app/explorer.py).
"""

import streamlit as st

from app.components import chart_card, empty_state, kpi_cards, page_header, run_engine
from app.explorer import CATEGORY, SCOPE, YEAR, Ctx, View, draw, explore_view, keep_valid, param, variant
from app.filters import category_years_map, current, parameters_for
from core.data import SHORT
from core.stats import p_text, strength

PAGE = "relationships"
COLOR_BY = {None: "Nothing", "state": "State", "region": "Region", "category": "Category", "rank_band": "Rank band"}
TWO = "Any two numbers: scatterplot and correlation"
TOP_CUTS = {None: "All", 10: "10", 25: "25", 50: "50", 100: "100", 150: "150", 200: "200"}

OTHER_VIEWS = [
    View("Which parameter is most linked to the overall score", "bivariate", "correlation_with_overall",
         (CATEGORY, YEAR, variant("view", "Chart", {"correlogram": "Correlogram", "bar": "Ranked bars"},
                                  "correlogram"), SCOPE)),
    View("How one parameter's link to the overall score changed over the years", "bivariate", "correlation_over_time",
         (CATEGORY, param("param", "Parameter", "rpc"), SCOPE)),
]


def numbers_for(categories: list[str]) -> list[str]:
    """Score, every parameter published by any of the categories (NIRF order), and rank."""
    params = list(dict.fromkeys(p for c in categories for p in parameters_for(c)))
    return ["score"] + params + ["rank"]


def interpretation(c: dict, x: str, y: str) -> str:
    """One line in plain words: strength and direction of r, what it means here, and whether it is significant."""
    r, p = c["pearson_r"], c["pearson_p"]
    words = strength(r)
    if "rank" in (x, y):
        other = SHORT[y if x == "rank" else x]
        meaning = (f"institutions with a higher {other} tend to have a better (smaller) rank" if r < 0 else
                   f"institutions with a higher {other} tend to have a worse (larger) rank")
    else:
        meaning = f"institutions with a higher {SHORT[x]} tend to have a {'higher' if r > 0 else 'lower'} {SHORT[y]}"
    sig = (f"statistically significant ({p_text(p)})" if p < 0.05 else
           f"not statistically significant ({p_text(p)}), so it could be chance")
    return f"**{words.capitalize()} relationship**: {meaning}; {sig}."


def two_variables() -> None:
    f = current()
    ctx = Ctx(PAGE, View(TWO, "bivariate", "scatter_relation", (CATEGORY,)))
    with st.container(border=True, key=f"x-{PAGE}-controls"):
        row1 = st.columns(4, gap="small")
        bottom = st.columns(4, gap="small")
        # The filters (second row) are read first: the X/Y lists depend on the category.
        with row1[2]:
            color = st.selectbox("Colour by", list(COLOR_BY), format_func=COLOR_BY.get, key=f"x-{PAGE}-color")
        with bottom[0]:
            if color == "category":
                cats = st.multiselect("Categories (one colour each)", list(category_years_map()),
                                      default=[f.category, "Engineering" if f.category != "Engineering" else "Overall"],
                                      max_selections=8, key=f"x-{PAGE}-categories-{f.category}")
                cats = cats or [f.category]
            else:
                cats = [draw(CATEGORY, ctx)["category"]]
        years = sorted({y for c in cats for y in category_years_map()[c]})
        with bottom[1]:
            default = min(f.end, years[-1])
            keep_valid(f"x-{PAGE}-year", years)
            year = st.selectbox("Year", years, index=years.index(default) if default in years else len(years) - 1,
                                key=f"x-{PAGE}-year")
        with bottom[2]:
            top = st.select_slider("Only ranks 1 to …", list(TOP_CUTS), format_func=TOP_CUTS.get, key=f"x-{PAGE}-top",
                                   help="All = every institution with both numbers; 50 = only the top 50.")
        with bottom[3]:
            states = draw(SCOPE, ctx)["__states"]
        numbers = numbers_for(cats)
        keep_valid(f"x-{PAGE}-x", numbers)                # keep X and Y when the new category has them
        keep_valid(f"x-{PAGE}-y", numbers)
        with row1[0]:
            x = st.selectbox("X axis", numbers, index=numbers.index("rpc") if "rpc" in numbers else 0,
                             format_func=SHORT.get, key=f"x-{PAGE}-x")
        with row1[1]:
            y = st.selectbox("Y axis", numbers, index=0, format_func=SHORT.get, key=f"x-{PAGE}-y")
        with row1[3]:
            st.html("<div style='height:1.9rem'></div>")
            trend = st.toggle("Trend line", value=True, key=f"x-{PAGE}-trend",
                              help="The least-squares straight line through the dots.")
        if len(cats) > 1:
            st.caption("Scores of different categories are on different scales of meaning: compare the patterns, "
                       "not the levels.")
        elif color == "category":
            st.caption("Add a second category to colour the dots by category.")

    if x == y:
        with st.container(border=True, key=f"card-{PAGE}-same"):
            empty_state(f"X and Y are both {SHORT[x]}. A variable is always perfectly related to itself.",
                        title="Choose two different numbers", hint="Pick another number for the X or the Y axis.")
        return
    params = dict(x=x, y=y, year=year, category=cats[0] if len(cats) == 1 else cats,
                  color_by=color, trendline=trend, top_n=top)
    with st.spinner("Drawing the chart…"):
        result, error = run_engine("bivariate", "scatter_relation", params, tuple(states) if states else None)
    if error:
        with st.container(border=True, key=f"card-{PAGE}-scatter"):
            empty_state(error, title="This selection has no answer")
        return
    c = result.table.attrs["stats"]
    kpi_cards([
        ("Pearson r", f"{c['pearson_r']:.2f}", "straight-line strength, −1 to +1"),
        ("Spearman rho", f"{c['spearman_rho']:.2f}", "same on ranks: any steady rise or fall"),
        ("R²", f"{c['r2']:.2f}", f"the line explains {100 * c['r2']:.0f}% of {SHORT[y]}"),
        ("p-value", p_text(c["pearson_p"]).removeprefix("p ").removeprefix("= "), "< 0.05 = significant"),
        ("n", f"{c['n']}", "institutions with both values"),
    ])
    st.markdown(interpretation(c, x, y))
    chart_card(result, key=f"{PAGE}-scatter", why="A scatterplot shows every institution as one dot, so the shape, "
               "direction and strength of the relationship, and any outliers, are visible at once.")


page_header("Relationships", "How two NIRF numbers move together: pick any two, see the scatterplot, the trend "
            "line and the correlation; or see which parameter is most linked to the overall score.",
            eyebrow="Explore · Correlation")
labels = [TWO] + [v.label for v in OTHER_VIEWS]
choice = st.selectbox("What do you want to see?", labels, key=f"x-{PAGE}-view")
if choice == TWO:
    two_variables()
else:
    explore_view(PAGE, OTHER_VIEWS[labels.index(choice) - 1])
