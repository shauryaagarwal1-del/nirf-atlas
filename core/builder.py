"""Chart Builder: a safe "pick filters, variables, aggregation and chart type" query engine.

The safety net for questions no ready-made analysis covers. Everything is chosen from fixed lists,
so the builder can only ever filter, group and summarise the cleaned master table:
  * filters: categories, years, states, regions, institutions and a rank cut-off (top N);
  * X, Y, colour and facet: a dimension (year, category, state, region, rank band, institution, new
    entrant) or a measure (overall score, the parameters, the exact rank);
  * for bar charts, optionally only the top N groups (largest values; best for rank);
  * aggregation: count (number of distinct institutions), mean, median, min or max;
  * chart type: only types from docs/allowed_charts.md.
build_chart() checks the combination first. A combination that cannot make a sensible chart raises
BuilderHint, whose message is a friendly hint saying what to change ("A pie chart shows parts of a
whole, so it needs Count"). Smaller problems (too many groups, an option the chart does not use) are
handled and reported in the chart note and the method instead.
The page is app/views/chart_builder.py; the Ask NIRF chat can call the same function.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from core.data import (BAND_ORDER, LABELS, SHORT, NirfInputError, chart_labels, check_category, check_states,
                       filter_df, fmt_years, load_master)
from core.result import ChartResult
from core.stats import correlate, strength
from core.theme import CATEGORICAL, CROSS_CATEGORY_NOTE, OTHER, SEQUENTIAL, finish, ordinal_ramp

DIMENSIONS = {"year": "Year", "category": "Category", "state": "State", "region": "Region",
              "rank_band": "Rank band", "institution": "Institution", "new_entrant": "New entrant"}
NEW_ENTRANT = ["New entrant", "Ranked before", "First year of the list"]   # values of the new_entrant group
MEASURES = {m: SHORT[m] for m in ["score", "tlr", "rpc", "go", "oi", "pr", "qnr", "qlr", "sfc", "rank"]}
AGGREGATIONS = {"count": "Count", "mean": "Mean", "median": "Median", "min": "Minimum", "max": "Maximum"}
# chart key -> (label in the builder, chart type name from docs/allowed_charts.md)
CHARTS = {
    "bar": ("Bar chart", "bar chart"),
    "grouped_bar": ("Grouped bar chart", "grouped bar chart"),
    "stacked_bar": ("Stacked bar chart", "stacked bar chart"),
    "line": ("Line chart", "line chart"),
    "scatter": ("Scatterplot", "scatterplot"),
    "bubble": ("Bubble chart", "bubble chart"),
    "box": ("Box plot", "box-and-whisker plot"),
    "violin": ("Violin plot", "violin plot"),
    "histogram": ("Histogram", "histogram"),
    "strip": ("Strip chart", "jittered strip chart"),
    "heatmap": ("Heatmap", "matrix heatmap"),
    "pie": ("Pie chart", "pie chart"),
}
AGGREGATED = {"bar", "grouped_bar", "stacked_bar", "line", "heatmap", "pie"}   # one value per group
PER_ROW = {"scatter", "bubble", "box", "violin", "histogram", "strip"}         # one mark per institution-year

# What each chart type uses: (X kind, needs Y, uses aggregation, colour rule, facet allowed)
#   X kind: "dimension" or "measure"; colour rule: "optional", "required" or "unused".
RULES = {
    "bar": ("dimension", True, True, "optional", True),
    "grouped_bar": ("dimension", True, True, "required", True),
    "stacked_bar": ("dimension", True, True, "required", True),
    "line": ("dimension", True, True, "optional", True),
    "scatter": ("measure", True, False, "optional", True),
    "bubble": ("measure", True, False, "optional", True),
    "box": ("dimension", True, False, "optional", True),
    "violin": ("dimension", True, False, "optional", True),
    "histogram": ("measure", False, False, "optional", True),
    "strip": ("dimension", True, False, "optional", True),
    "heatmap": ("dimension", True, True, "required", False),
    "pie": ("dimension", False, True, "unused", False),
}
MAX_BARS = 30          # institutions as X: the 30 largest values are shown
MAX_COLOURS = 8        # the categorical palette has 8 colours; the rest becomes "Other"
MAX_PANELS = 12        # facets: the 12 largest groups
MAX_HEATMAP_ROWS = 40  # heatmap rows: enough for every state
ORDERED = {"year", "rank_band", "new_entrant"}


class BuilderHint(NirfInputError):
    """A chart combination that cannot work; the message says what to change."""


def uses(chart: str) -> dict:
    """Which controls a chart type uses (the page greys out the others)."""
    x_kind, needs_y, agg, colour, facet = RULES[chart]
    return {"x_kind": x_kind, "y": needs_y, "agg": agg, "colour": colour != "unused", "colour_required":
            colour == "required", "facet": facet, "size": chart == "bubble",
            "limit": chart in ("bar", "grouped_bar", "stacked_bar")}


def label(col: str | None) -> str:
    return DIMENSIONS.get(col) or MEASURES.get(col) or str(col)


def _name(col: str) -> str:
    """The column of the prepared table that holds a dimension or measure."""
    return "category_std" if col == "category" else col


def _check(chart, x, y, agg, color, facet, size) -> None:
    """Raise a BuilderHint when the combination cannot make a sensible chart."""
    if chart not in CHARTS:
        raise BuilderHint(f"Choose a chart type from the list: {', '.join(v[0] for v in CHARTS.values())}.")
    x_kind, needs_y, uses_agg, colour_rule, _ = RULES[chart]
    name = CHARTS[chart][0]
    if agg not in AGGREGATIONS:
        raise BuilderHint(f"Choose an aggregation: {', '.join(AGGREGATIONS.values())}.")
    if x is None:
        raise BuilderHint("Choose a variable for the X axis.")
    if x_kind == "measure" and x not in MEASURES:
        raise BuilderHint(f"A {name.lower()} needs a number on the X axis, and {label(x)} is a group. "
                          f"Try Overall score or a parameter; to compare groups use a box plot or a bar chart.")
    if x_kind == "dimension" and x not in DIMENSIONS:
        raise BuilderHint(f"A {name.lower()} needs groups on the X axis (e.g. Year, State, Category), and "
                          f"{label(x)} is a number. To see how a number is spread, use a histogram; to relate "
                          f"two numbers, use a scatterplot.")
    if chart == "line" and x != "year":
        raise BuilderHint("A line chart shows change over time, so X must be Year. To compare groups, use a "
                          "bar chart.")
    if needs_y and not (uses_agg and agg == "count") and y not in MEASURES:
        raise BuilderHint(f"Choose a number for the Y axis (e.g. Overall score) for the {name.lower()}"
                          + (", or set the aggregation to Count." if uses_agg else "."))
    if chart in ("scatter", "bubble") and x == y:
        raise BuilderHint("Choose two different numbers for X and Y: a number is always perfectly related "
                          "to itself.")
    if chart == "pie" and agg != "count":
        raise BuilderHint("A pie chart shows parts of a whole, so it only works with Count (how many "
                          "institutions in each group). For averages use a bar chart.")
    if chart == "stacked_bar" and agg != "count":
        raise BuilderHint("Stacked bars add the groups on top of each other, which only makes sense for Count. "
                          f"For the {AGGREGATIONS[agg].lower()} use a grouped bar chart.")
    if colour_rule == "required" and color is None:
        what = "Rows (second group)" if chart == "heatmap" else "Colour / group"
        raise BuilderHint(f"A {name.lower()} needs a second grouping: choose {what}, e.g. Region or Year.")
    for v, role in ((color, "Colour"), (facet, "Facet")):
        if v is not None and v not in DIMENSIONS:
            raise BuilderHint(f"{role} must be a group (Year, Category, State, Region, Rank band, Institution), "
                              f"not a number.")
    picked = [v for v in (x, color, facet) if v in DIMENSIONS]
    if len(picked) != len(set(picked)):
        raise BuilderHint("X, Colour and Facet must be different groups; the same one twice adds nothing.")
    if chart == "bubble" and size not in MEASURES:
        raise BuilderHint("A bubble chart needs a number for the bubble size (e.g. PR).")


def _filtered(categories, years, states, regions, institutions, rank_max) -> tuple[pd.DataFrame, list[str]]:
    """Master-table rows matching every filter, plus a plain-words description of the filters."""
    df = load_master()
    cats = [check_category(c, df) for c in (categories or [])]
    rows = filter_df(df, categories=cats or None, years=years or None, states=states or None,
                     institutions=institutions or None, rank_max=int(rank_max) if rank_max else None)
    if regions:
        rows = rows[rows["region"].isin(regions)]
    words = [", ".join(cats) if cats else "all categories",
             fmt_years(sorted(rows["year"].unique().tolist())) if len(rows) else "no years"]
    if states:
        words.append(", ".join(check_states(states)))
    if regions:
        words.append(", ".join(regions) + " region" + ("s" if len(regions) > 1 else ""))
    if institutions:
        words.append(f"{len(institutions)} chosen institution" + ("s" if len(institutions) > 1 else ""))
    if rank_max:
        words.append(f"ranks 1–{int(rank_max)}")
    return rows, words


def _prepare(rows: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Add the 'institution' label column and make group columns plain text in a sensible order."""
    d = rows.copy()
    if "institution" in cols:
        d["institution"] = d["institution_key"].map(chart_labels(d["institution_key"].unique()))
    d["rank"] = d["rank"].astype("Float64").astype(float)
    if "rank_band" in cols:
        d["rank_band"] = d["rank_band"].fillna("unbanded")
    if "new_entrant" in cols:
        # New entrant = first year in this category's list (not counting the list's own first year).
        launch = load_master().groupby("category_std")["year"].min()
        first_list = d["year"].eq(d["category_std"].map(launch))
        d["new_entrant"] = np.select([d["is_new_entrant"], first_list], NEW_ENTRANT[::2], NEW_ENTRANT[1])
    return d


def _order(d: pd.DataFrame, col: str) -> list:
    values = d[_name(col)].dropna().unique().tolist()
    if col == "rank_band":
        return [b for b in BAND_ORDER if b in values] + sorted(v for v in values if v not in BAND_ORDER)
    if col == "new_entrant":
        return [v for v in NEW_ENTRANT if v in values]
    return sorted(values)


def _colours(groups: list, col: str) -> dict:
    if col in ORDERED:
        return dict(zip(groups, ordinal_ramp(len(groups))))
    out, slot = {}, 0
    for g in groups:
        out[g] = OTHER if g == "Other" else CATEGORICAL[slot % len(CATEGORICAL)]
        slot += g != "Other"
    return out


def _limit_groups(d: pd.DataFrame, col: str | None, limit: int, notes: list[str], role: str) -> pd.DataFrame:
    """Keep the `limit - 1` groups with most institutions and fold the rest into 'Other'."""
    if col is None or col in ORDERED:
        return d
    c = _name(col)
    sizes = d.groupby(c)["institution_key"].nunique().sort_values(ascending=False)
    if len(sizes) <= limit:
        return d
    keep = sizes.index[:limit - 1]
    d = d.copy()
    d[c] = d[c].where(d[c].isin(keep), "Other")
    notes.append(f"{role}: the {limit - 1} {label(col).lower()} groups with the most institutions are shown; the "
                 f"other {len(sizes) - limit + 1} are combined as 'Other'.")
    return d


def _aggregate(d: pd.DataFrame, keys: list[str], y: str | None, agg: str) -> pd.DataFrame:
    """One row per group: the aggregated value and n (distinct institutions behind it)."""
    names = [_name(k) for k in keys]
    g = d.groupby(names, observed=True)
    out = g["institution_key"].nunique().rename("n").to_frame()
    if agg == "count":
        out["value"] = out["n"]
    else:
        vals = d[d[y].notna()].groupby(names, observed=True)[y]
        out["value"] = getattr(vals, agg)()
        out["n"] = d[d[y].notna()].groupby(names, observed=True)["institution_key"].nunique()
        out = out.dropna(subset=["value"])
    return out.reset_index()


def _fmt(v: float, col: str | None, agg: str) -> str:
    if agg == "count":
        return f"{int(v):,}"
    return f"{v:.0f}" if col == "rank" else f"{v:.1f}"


def build_chart(chart: str, x: str, y: str | None = "score", agg: str = "mean", color: str | None = None,
                facet: str | None = None, size: str | None = None, categories=None, years=None, states=None,
                regions=None, institutions=None, rank_max: int | None = None, limit: int | None = None
                ) -> ChartResult:
    """Draw any allowed chart from the master table.

    Definition: the rows matching the filters (categories, years, states, regions, institutions,
    rank cut-off), grouped by X (and colour/facet), summarised with the aggregation.
    Method: count = number of distinct institutions in a group; mean/median/min/max = that
    statistic of the chosen number over the group's rows (each institution-year-category is one row).
    Row-level charts (scatter, bubble, box, violin, histogram, strip) draw one mark per row instead.
    limit (bar charts): show only the `limit` X groups with the largest totals (the best for rank).
    """
    _check(chart, x, y, agg, color, facet, size)
    x_kind, needs_y, uses_agg, colour_rule, facet_ok = RULES[chart]
    notes: list[str] = []
    if colour_rule == "unused" and color is not None:
        notes.append(f"Colour is not used by a {CHARTS[chart][0].lower()}, so it was ignored.")
        color = None
    if not facet_ok and facet is not None:
        notes.append(f"Facets are not available for a {CHARTS[chart][0].lower()}, so it was ignored.")
        facet = None
    if uses_agg and agg == "count":
        y = None

    rows, words = _filtered(categories, years, states, regions, institutions, rank_max)
    measures = [m for m in (x, y, size) if m in MEASURES]
    for m in measures:
        if rows[m].notna().sum() == 0:
            raise BuilderHint(f"NIRF published no {SHORT[m]} for this selection ({'; '.join(words)}). Choose "
                              f"another number or category (Research Institutions use QnR, QlR, SFC instead of "
                              f"TLR, RPC, GO; Innovation and SDG publish ranks only).")
    if measures:
        rows = rows.dropna(subset=measures)
    if rows.empty:
        raise BuilderHint(f"No rows match these filters ({'; '.join(words)}). Widen the years, add categories "
                          f"or clear the state, region or institution filters.")
    dims = [v for v in (x, color, facet) if v in DIMENSIONS]
    d = _prepare(rows, dims)
    # Heatmap rows can be many (e.g. every state); colours and pie slices are limited to the palette.
    d = _limit_groups(d, color, MAX_HEATMAP_ROWS if chart == "heatmap" else MAX_COLOURS, notes,
                      "Rows" if chart == "heatmap" else "Colour")
    if chart == "pie":
        d = _limit_groups(d, x, MAX_COLOURS, notes, "Slices")

    n_cats = d["category_std"].nunique()
    if (n_cats > 1 or "category" in dims) and any(m != "rank" for m in measures):
        notes.append(CROSS_CATEGORY_NOTE)
    n_years = d["year"].nunique()
    if n_years > 1 and "year" not in dims:
        notes.append(f"Pooled over {n_years} years: " + ("an institution ranked in any of them is counted once per "
                     "group." if chart in AGGREGATED and agg == "count" else "each institution counts once per year "
                     "it was ranked."))

    if chart in AGGREGATED:
        fig, table, title, explain = _aggregated(d, chart, x, y, agg, color, facet, notes, limit)
    else:
        fig, table, title, explain = _per_row(d, chart, x, y, color, facet, size, notes)

    chart_type = CHARTS[chart][1]
    if chart == "line" and color:
        chart_type = "multi-series line chart"
    if chart == "bar" and facet:
        chart_type = "small-multiple bar charts"
    if chart == "histogram" and color:
        chart_type = "overlapping histogram"

    filters = "; ".join(words)
    panels = d[_name(facet)].nunique() if facet else 1
    height = 520 if panels == 1 else 170 + 300 * math.ceil(min(panels, MAX_PANELS) / 3)
    if chart == "heatmap":                       # one readable row label per group
        height = max(height, 190 + 24 * d[_name(color)].nunique())
    finish(fig, title, f"{CHARTS[chart][0]} · {filters}", note="<br>".join(dict.fromkeys(notes)) or None,
           height=height, legend_title=label(color) if color else None)
    insight = f"{title} ({filters}; {d['institution_key'].nunique():,} institutions, {len(d):,} rows)."
    method = (f"Filters: {filters}. {explain} "
              + (f"Each panel shows one {label(facet).lower()} (facet). " if facet else "")
              + " ".join(dict.fromkeys(notes)))
    table.attrs["notes"] = list(dict.fromkeys(notes))
    return ChartResult(fig, table.reset_index(drop=True), insight, method.strip(), chart_type)


def _facet_titles(fig: go.Figure) -> None:
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=", 1)[-1]))


def _aggregated(d, chart, x, y, agg, color, facet, notes, limit=None):
    keys = [v for v in (x, color, facet) if v]
    t = _aggregate(d, keys, y, agg)
    xc, cc, fc = _name(x), color and _name(color), facet and _name(facet)
    what = "institutions" if agg == "count" else f"{AGGREGATIONS[agg].lower()} {SHORT[y]}"
    value_label = "Number of institutions" if agg == "count" else f"{AGGREGATIONS[agg]} {LABELS[y]}"
    best_low = y == "rank" and agg != "count"           # a smaller rank is better

    cap = limit or (MAX_BARS if x == "institution" else None)
    if cap and chart in ("bar", "grouped_bar", "stacked_bar"):
        totals = t.groupby(xc)["value"].sum().sort_values(ascending=best_low)
        if len(totals) > cap:
            t = t[t[xc].isin(totals.index[:int(cap)])]
            what_x = "institutions" if x == "institution" else f"{label(x).lower()} groups"
            notes.append(f"The {int(cap)} {'best' if best_low else 'largest'} of {len(totals)} {what_x} are shown.")
    if facet:
        sizes = t.groupby(fc)["n"].sum().sort_values(ascending=False)
        if len(sizes) > MAX_PANELS:
            t = t[t[fc].isin(sizes.index[:MAX_PANELS])]
            notes.append(f"Facets: the {MAX_PANELS} {label(facet).lower()} groups with the most institutions.")

    x_order = _order(t, x)
    if x == "institution" or x not in ORDERED and chart != "line":
        x_order = t.groupby(xc)["value"].sum().sort_values(ascending=best_low).index.tolist()
    orders = {xc: x_order}
    cmap = None
    if color:
        groups = _order(t, color)
        if "Other" in groups:
            groups = [g for g in groups if g != "Other"] + ["Other"]
        orders[cc] = groups
        cmap = _colours(groups, color)
    if facet:
        orders[fc] = _order(t, facet)
    labels = {xc: label(x), "value": value_label, "n": "Institutions"}
    if cc:
        labels[cc] = label(color)
    if fc:
        labels[fc] = label(facet)
    t_plot = t.copy()
    if x == "year":
        t_plot[xc] = t_plot[xc].astype(int)
    if cc == "year":
        t_plot[cc] = t_plot[cc].astype(str)
        orders[cc] = [str(g) for g in orders[cc]]
        cmap = {str(k): v for k, v in cmap.items()}
    if fc == "year":
        t_plot[fc] = t_plot[fc].astype(str)
        orders[fc] = [str(g) for g in orders[fc]]
    common = dict(category_orders=orders, labels=labels, hover_data={"n": True})
    if fc:
        common.update(facet_col=fc, facet_col_wrap=3, facet_row_spacing=0.12, facet_col_spacing=0.06)

    if chart == "pie":
        fig = go.Figure(go.Pie(labels=t_plot[xc], values=t_plot["value"], sort=False, hole=0,
                               marker=dict(colors=[_colours(x_order, x).get(g, OTHER) for g in t_plot[xc]],
                                           line=dict(color="#ffffff", width=1)),
                               textinfo="label+percent", textposition="inside", insidetextorientation="horizontal",
                               hovertemplate="<b>%{label}</b><br>%{value} institutions (%{percent})<extra></extra>"))
        top = t.loc[t["value"].idxmax()]
        share = 100 * top["value"] / t["value"].sum()
        title = f"{top[xc]} has the largest share: {share:.0f}% of the institutions"
        explain = (f"We count the distinct institutions in each {label(x).lower()} and draw each count as a slice "
                   f"of the whole; the percentage is the slice's count ÷ the total of all slices × 100. An "
                   f"institution that appears in several {label(x).lower()} groups is counted in each.")
        return fig, t.rename(columns={xc: x, "value": "institutions"}), title, explain

    if chart == "heatmap":
        pivot = t.pivot_table(index=cc, columns=xc, values="value", aggfunc="first")
        pivot = pivot.reindex(index=orders[cc] if cc != "year" else sorted(pivot.index),
                              columns=[v for v in x_order if v in pivot.columns])
        fig = go.Figure(go.Heatmap(
            z=pivot.values, x=[str(v) for v in pivot.columns], y=[str(v) for v in pivot.index],
            colorscale=SEQUENTIAL, reversescale=best_low, xgap=2, ygap=2,
            text=[[("" if pd.isna(v) else _fmt(v, y, agg)) for v in row] for row in pivot.values],
            texttemplate="%{text}", textfont=dict(size=11),
            colorbar=dict(title=dict(text="Institutions" if agg == "count" else f"{AGGREGATIONS[agg]} {SHORT[y]}",
                                     side="top"), thickness=12),
            hovertemplate=f"<b>%{{y}} · %{{x}}</b><br>{value_label}: %{{text}}<extra></extra>"))
        fig.update_xaxes(title_text=label(x), type="category", showgrid=False)
        fig.update_yaxes(title_text=label(color), type="category", autorange="reversed", showgrid=False)
        real = t[t[cc].ne("Other")] if t[cc].ne("Other").any() else t
        cell = real.loc[(real["value"].idxmin() if best_low else real["value"].idxmax())]
        title = f"{'Best' if best_low else 'Largest'} cell: {cell[cc]} in {cell[xc]} ({_fmt(cell['value'], y, agg)} {what})"
        explain = (f"We group the rows by {label(x).lower()} (columns) and {label(color).lower()} (rows) and colour "
                   f"each cell by the {_agg_words(agg, y)}; the number is printed in the cell, and an empty cell "
                   f"means no institution in that combination.")
        return fig, t.rename(columns={xc: x, cc: color}), title, explain

    if chart == "line":
        t_plot = t_plot.sort_values(xc)
        fig = px.line(t_plot, x=xc, y="value", color=cc, markers=True, color_discrete_map=cmap, **common)
        fig.update_xaxes(dtick=1)
        if best_low:
            fig.update_yaxes(autorange="reversed")
        if color:
            last = t[t[xc].eq(t[xc].max())]
            top = last.loc[last["value"].idxmin() if best_low else last["value"].idxmax()]
            title = (f"In {int(top[xc])}, {top[cc]} has the {'most' if agg == 'count' else 'best' if best_low else 'highest'} {what} "
                     f"({_fmt(top['value'], y, agg)})")
        else:
            s = t.groupby(xc)["value"].first().sort_index()
            change = s.iloc[-1] - s.iloc[0]
            verb = "rose" if change > 0 else "fell" if change < 0 else "stayed"
            if best_low:
                verb = "improved" if change < 0 else "worsened" if change > 0 else "stayed"
            title = (f"The {what} {verb} from {_fmt(s.iloc[0], y, agg)} in {int(s.index[0])} to "
                     f"{_fmt(s.iloc[-1], y, agg)} in {int(s.index[-1])}")
        explain = (f"For every year we take the {_agg_words(agg, y)}"
                   + (f", separately for each {label(color).lower()}" if color else "")
                   + "; the points are joined in time order." + (" The rank axis is reversed so better ranks are "
                                                                 "higher." if best_low else ""))
        return fig, t.rename(columns={xc: x, **({cc: color} if cc else {})}), title, explain

    mode = {"bar": "relative", "grouped_bar": "group", "stacked_bar": "stack"}[chart]
    fig = px.bar(t_plot, x=xc, y="value", color=cc, barmode=mode, color_discrete_map=cmap,
                 color_discrete_sequence=[CATEGORICAL[0]], **common)
    if x == "year":
        fig.update_xaxes(dtick=1)
    elif x in ("institution", "state") and len(x_order) > 8:
        # Slanted names need room below the axis: a fixed bottom margin sized to the longest name keeps
        # the axis title and the source note underneath them instead of on top of them.
        longest = max((len(str(v)) for v in x_order), default=0)
        fig.update_xaxes(tickangle=-40, automargin=False)
        fig.update_layout(margin=dict(b=110 + int(longest * 6.6 * 0.64)))
    if fc:
        _facet_titles(fig)
    sums = t.groupby(xc)["value"].sum() if chart == "stacked_bar" else t.set_index(xc)["value"]
    top_x = sums.idxmin() if best_low else sums.idxmax()
    if chart == "bar" and not facet:
        title = (f"{top_x} has the most institutions ({_fmt(sums[top_x], y, agg)})" if agg == "count" else
                 f"{top_x} has the {'best' if best_low else 'highest'} {what} ({_fmt(sums[top_x], y, agg)})")
    elif chart == "stacked_bar":
        # Name the largest coloured segment (for "New entrant": the year with the most new entrants).
        segs = t[t[cc].eq("New entrant")] if color == "new_entrant" else t[t[cc].ne("Other")]
        seg = (segs if len(segs) else t).loc[(segs if len(segs) else t)["value"].idxmax()]
        lead = (f"Most new entrants: {seg[xc]} ({_fmt(seg['value'], y, agg)})" if color == "new_entrant" else
                f"Largest group: {seg[cc]} in {seg[xc]} ({_fmt(seg['value'], y, agg)})")
        title = f"{lead}; {top_x} has the most institutions in total ({_fmt(sums[top_x], y, agg)})"
    else:
        top = t.loc[t["value"].idxmin() if best_low else t["value"].idxmax()]
        extra = " · ".join(str(top[k]) for k in (cc, fc) if k)
        title = (f"{'Best' if best_low else 'Highest'} {what}: {top[xc]}" + (f" ({extra})" if extra else "")
                 + f", {_fmt(top['value'], y, agg)}")
    explain = (f"We group the rows by {label(x).lower()}" + (f" and {label(color).lower()}" if color else "")
               + (f" and {label(facet).lower()}" if facet else "") + f" and take the {_agg_words(agg, y)} in "
               f"each group." + (" Stacked bars add the groups' counts on top of each other." if chart ==
                                 "stacked_bar" else " Bars of the same X stand side by side." if chart ==
                                 "grouped_bar" else "") + (" A smaller rank is better." if best_low else ""))
    return fig, t.rename(columns={xc: x, **({cc: color} if cc else {}), **({fc: facet} if fc else {})}), title, explain


def _agg_words(agg: str, y: str | None) -> str:
    if agg == "count":
        return "number of distinct institutions"
    return {"mean": "mean (sum ÷ count)", "median": "median (middle value)", "min": "minimum",
            "max": "maximum"}[agg] + f" of {SHORT[y]}"


def _per_row(d, chart, x, y, color, facet, size, notes):
    """Charts with one mark per row (institution-year-category)."""
    cc, fc = color and _name(color), facet and _name(facet)
    xc = _name(x)
    d = d.copy()
    d["institution_name"] = d["canonical_name"]
    if facet:
        sizes = d.groupby(fc)["institution_key"].nunique().sort_values(ascending=False)
        if len(sizes) > MAX_PANELS:
            d = d[d[fc].isin(sizes.index[:MAX_PANELS])]
            notes.append(f"Facets: the {MAX_PANELS} {label(facet).lower()} groups with the most institutions.")
    orders, cmap = {}, None
    for col, c in ((x, xc), (color, cc), (facet, fc)):
        if col in DIMENSIONS:
            if col == "year":
                d[c] = d[c].astype(str)
            groups = [str(g) for g in _order(d, col)] if col == "year" else _order(d, col)
            if "Other" in groups:
                groups = [g for g in groups if g != "Other"] + ["Other"]
            orders[c] = groups
    if color:
        cmap = _colours(orders[cc], color)
    labels = {c: label(v) for v, c in ((x, xc), (y, y), (color, cc), (facet, fc), (size, size)) if v}
    labels["institution_name"] = "Institution"
    hover = {k: True for k in ("state", "year") if k not in (xc, cc, fc)}
    common = dict(category_orders=orders, labels=labels, color=cc, color_discrete_map=cmap,
                  color_discrete_sequence=[CATEGORICAL[0]])
    if fc:
        common.update(facet_col=fc, facet_col_wrap=3, facet_row_spacing=0.12, facet_col_spacing=0.06)
    rank_axis = {"x": x == "rank", "y": y == "rank"}

    if chart in ("scatter", "bubble"):
        if chart == "bubble":
            d = d.dropna(subset=[size])
            d["_size"] = d[size].clip(lower=0)
        fig = px.scatter(d, x=x, y=y, size="_size" if chart == "bubble" else None, size_max=28,
                         hover_name="institution_name", hover_data={**hover, **({size: ":.1f", "_size": False}
                                                                                 if chart == "bubble" else {})},
                         opacity=0.8, **common)
        c = correlate(d[x], d[y])
        rho = "" if pd.isna(c["spearman_rho"]) else f", Spearman ρ = {c['spearman_rho']:.2f}"
        title = (f"{SHORT[x]} and {SHORT[y]}: {strength(c['pearson_r'])} relationship (r = {c['pearson_r']:.2f}"
                 f"{rho}, n = {c['n']})" if pd.notna(c["pearson_r"]) else f"{SHORT[y]} against {SHORT[x]}")
        explain = (f"One dot per institution and year ({c['n']} dots); Pearson r measures how close the dots are to a "
                   f"straight line (−1 to +1), Spearman ρ the same on ranks."
                   + (f" Bubble area shows {SHORT[size]}." if chart == "bubble" else ""))
        table = d[["canonical_name", "category_std", "year", "state", x, y] + ([size] if chart == "bubble" else [])
                  + ([cc] if cc and cc not in ("category_std", "year", "state") else [])]
    elif chart == "histogram":
        fig = px.histogram(d, x=x, nbins=20, barmode="overlay" if color else "relative",
                           opacity=0.6 if color else 1, **common)
        fig.update_yaxes(title_text="Number of rows (institution-years)")
        q1, med, q3 = d[x].quantile([0.25, 0.5, 0.75])
        title = (f"The middle half of {SHORT[x]} values lies between {q1:.1f} and {q3:.1f} (median {med:.1f}, "
                 f"n = {len(d)})")
        explain = (f"The {SHORT[x]} values are cut into about 20 equal-width bins and each bar counts the rows in "
                   f"its bin; Q1 and Q3 (the 25th and 75th percentiles) bound the middle half."
                   + (" Groups are drawn as overlapping, see-through histograms." if color else ""))
        table = d[["canonical_name", "category_std", "year", "state", x] + ([cc] if cc and cc not in
                                                                             ("category_std", "year", "state") else [])]
    else:
        maker = {"box": px.box, "violin": px.violin, "strip": px.strip}[chart]
        extra = {"box": dict(points="outliers"), "violin": dict(box=True, points="outliers"),
                 "strip": dict(stripmode="overlay")}[chart]
        fig = maker(d, x=xc, y=y, hover_name="institution_name", hover_data=hover, **extra, **common)
        if chart == "strip":
            fig.update_traces(jitter=0.6, marker=dict(size=7, opacity=0.75))
        med = d.groupby(xc)[y].median()
        best = med.idxmin() if y == "rank" else med.idxmax()
        title = (f"{best} has the {'best' if y == 'rank' else 'highest'} median {SHORT[y]} ({med[best]:.1f}) of "
                 f"{len(med)} {label(x).lower()} groups")
        explain = {"box": "Each box spans Q1 to Q3 (the middle 50%), the line inside is the median, whiskers reach the "
                          "furthest values within 1.5 × IQR and dots beyond them are outliers.",
                   "violin": "Each violin's width shows how many rows have each value (a smoothed density); the box "
                             "inside marks the median and Q1–Q3.",
                   "strip": "Every row is one dot, spread sideways at random (jitter) so dots do not hide each "
                            "other."}[chart] + f" Groups: {label(x).lower()}."
        table = d[["canonical_name", "category_std", "year", "state", y] + [c for c in {xc, cc} - {
            None, "category_std", "year", "state"}]]
    for axis, rev in rank_axis.items():
        if rev:
            (fig.update_xaxes if axis == "x" else fig.update_yaxes)(autorange="reversed")
    if fc:
        _facet_titles(fig)
    table = table.rename(columns={"canonical_name": "institution", "category_std": "category"})
    return fig, table, title, explain
