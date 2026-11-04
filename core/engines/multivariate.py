"""Multivariate engine: several parameters at once (Annexure A section 5, Q5.1-Q5.5, plus a PCA view).

Functions
  parameter_profile()         chosen institutions on all five parameters (grouped bar chart, or
                              view="heatmap": matrix heatmap institution x parameter)
  gap_finder()                high on one parameter, low on another (scatterplot split into four quadrants
                              by the two medians; the "high / low" quadrant is labelled)
  improved_despite_decline()  overall score went up although one or more parameters went down (table +
                              small-multiple bar charts: one small chart of parameter changes per institution)
  strongest_weakest_gap()     strongest minus weakest parameter per institution (lollipop chart, sorted)
  parameter_pca()             the five parameters squeezed into two summary axes (PCA scatterplot coloured by
                              rank band, with the % of variance each axis explains)

Every chart type is one of the types listed in docs/allowed_charts.md.

The five parameters (TLR, RPC, GO, OI, PR; Research Institutions publish QnR, QlR, SFC, OI, PR
instead) are each scored out of 100, and only institutions with an exact rank have them. Each
category has its own weights, so parameters are compared within one category-year.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from core.data import (BAND_ORDER, LABELS, SHORT, NirfInputError, category_year, category_years, chart_labels,
                       check_category, check_column, check_year, filter_df, find_institutions, load_master,
                       parameters_of, short_name)
from core.result import ChartResult
from core.stats import signed
from core.theme import (CATEGORICAL, DOWN, INK, INK_SECONDARY, OTHER, UP, add_lollipops, color_map, finish,
                        highlight_marker, label_points, ordinal_ramp, padded_range)

MAX_INSTITUTIONS = 8


def _with_parameters(category: str, year) -> tuple[pd.DataFrame, str, int, list[str]]:
    """Rows of one category-year that have all published parameters, and the parameter list."""
    rows, category, year = category_year(category, year)
    params = parameters_of(rows)
    if not params:
        raise NirfInputError(f"NIRF published no parameter scores for {category} {year} (only ranks or bands).")
    return rows.dropna(subset=params).copy(), category, year, params


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def parameter_profile(institutions=None, year: int | None = None, category: str = "Overall",
                      view: str = "bar") -> ChartResult:
    """Answers questions like: "How do the top five institutions compare across all five NIRF parameters?" (Q5.1)

    Definition: each institution's five parameter scores (each out of 100) in one category-year.
    Method: view="bar" (default) draws a grouped bar chart: the parameters along the x-axis and one
    bar per institution inside each group, so institutions are compared parameter by parameter.
    view="heatmap" draws a matrix heatmap (institution x parameter, darker = higher, value in the
    cell). The hover gives each value's position among all institutions of that category-year.
    Default institutions: the top 5 of the year.
    """
    view = str(view).lower()
    if view not in {"bar", "heatmap"}:
        raise NirfInputError("view must be 'bar' (grouped bar chart) or 'heatmap' (matrix heatmap).")
    rows, category, year, params = _with_parameters(category, year)
    if institutions is None or (not isinstance(institutions, str) and len(list(institutions)) == 0):
        keys = rows.sort_values(["rank", "canonical_name"])["institution_key"].head(5).tolist()
        chosen = "the top 5"
    else:
        keys = find_institutions(institutions)
        chosen = None
    if len(keys) > MAX_INSTITUTIONS:
        raise NirfInputError(f"Please choose at most {MAX_INSTITUTIONS} institutions (you chose {len(keys)}).")
    labels = chart_labels(keys)
    missing = [labels[k] for k in keys if k not in set(rows["institution_key"])]
    if missing:
        raise NirfInputError(f"{', '.join(missing)} {'has' if len(missing) == 1 else 'have'} no published "
                             f"{category} parameter scores in {year} (not ranked, or only a rank band).")

    # Position of every value among all institutions of the category-year (1 = highest).
    pos = rows[params].rank(ascending=False, method="min").astype(int)
    pos.index = rows["institution_key"]
    sel = rows.set_index("institution_key").loc[keys]
    table = pd.DataFrame({"institution": [labels[k] for k in keys], "full_name": sel["canonical_name"].values,
                          "rank": sel["rank_raw"].values, "score": sel["score"].values})
    for p in params:
        table[SHORT[p]] = sel[p].values
    n_all = len(rows)
    xs = [SHORT[p] for p in params]

    fig = go.Figure()
    colors = color_map(table["institution"])
    if view == "bar":
        for k, name in zip(keys, table["institution"]):
            vals = [sel.at[k, p] for p in params]
            where = [f"{_ordinal(int(pos.at[k, p]))} of {n_all}" for p in params]
            fig.add_trace(go.Bar(
                x=xs, y=vals, name=name, marker_color=colors[name], customdata=np.stack([[LABELS[p] for p in params],
                                                                                         where], axis=1),
                hovertemplate=(f"<b>{name}</b> (rank {sel.at[k, 'rank_raw']})<br>%{{customdata[0]}}: %{{y:.2f}}"
                               f"<br>%{{customdata[1]}} in {category} {year}<extra></extra>")))
        fig.update_layout(barmode="group", bargap=0.22, bargroupgap=0.06)
        fig.update_yaxes(title_text="Parameter score (0-100)", range=[0, 105])
        fig.update_xaxes(title_text="NIRF parameter")
    else:
        z = table[xs].to_numpy(dtype=float)
        where = [[f"{_ordinal(int(pos.at[k, p]))} of {n_all}" for p in params] for k in keys]
        fig.add_trace(go.Heatmap(
            z=z, x=xs, y=table["institution"], text=np.round(z, 1), texttemplate="%{text}", customdata=where,
            zmin=0, zmax=100, colorbar=dict(title=dict(text="Score")),
            hovertemplate="<b>%{y}</b><br>%{x}: %{z:.2f}<br>%{customdata} in " + f"{category} {year}<extra></extra>"))
        fig.update_yaxes(autorange="reversed", showgrid=False, title_text="Institution")
        fig.update_xaxes(side="top", title_text="NIRF parameter")

    # Insight: who leads on most parameters, and where the chosen institutions differ most / least.
    leaders = {p: table.loc[table[SHORT[p]].idxmax(), "institution"] for p in params}
    lead_counts = pd.Series(leaders).value_counts()
    spread = {p: table[SHORT[p]].max() - table[SHORT[p]].min() for p in params}
    widest, narrowest = max(spread, key=spread.get), min(spread, key=spread.get)
    top = lead_counts.index[0]
    group = chosen or f"these {len(keys)} institutions"
    if len(keys) == 1:
        best = max(params, key=lambda p: sel.at[keys[0], p])
        worst = min(params, key=lambda p: sel.at[keys[0], p])
        title = f"{top}: strongest on {SHORT[best]} ({sel.at[keys[0], best]:.1f}), weakest on {SHORT[worst]} ({sel.at[keys[0], worst]:.1f})"
        insight = (f"In {category} {year}, {top} scores highest on {SHORT[best]} ({sel.at[keys[0], best]:.1f}) and lowest "
                   f"on {SHORT[worst]} ({sel.at[keys[0], worst]:.1f}).")
    else:
        title = (f"{top} leads on {lead_counts.iloc[0]} of {len(params)} parameters; the biggest difference is in "
                 f"{SHORT[widest]} ({spread[widest]:.0f} points)")
        insight = (f"Among {group} in {category} {year}, {top} has the highest score on "
                   f"{', '.join(SHORT[p] for p in params if leaders[p] == top)}. They differ most on {SHORT[widest]} "
                   f"({table[SHORT[widest]].min():.1f} to {table[SHORT[widest]].max():.1f}, a {spread[widest]:.1f}-point "
                   f"range) and least on {SHORT[narrowest]} ({spread[narrowest]:.1f} points).")
        ranks = sel["rank"].dropna()
        if len(ranks) == len(keys) and ranks.nunique() == 1:
            insight += (f" All of them share rank {int(ranks.iloc[0])} (a tie: NIRF gave them the same overall rank), "
                        f"so the parameters show how each one reaches that rank.")
    subtitle = f"{category} ranking {year}" + (f" · {chosen}" if chosen else "") + " · each parameter out of 100"
    finish(fig, title, subtitle, legend_title="Institution" if view == "bar" else None,
           height=520 if view == "bar" else max(360, 200 + 46 * len(keys)))
    shown = ("a grouped bar chart: parameters on the x-axis, one bar per institution in each group"
             if view == "bar" else "a matrix heatmap: one row per institution, one column per parameter, darker = higher")
    method = (f"We take the published parameter scores ({', '.join(SHORT[p] for p in params)}; each out of 100) of the "
              f"chosen institutions in {category} {year} and draw {shown}. The hover gives each value's position among "
              f"all {n_all} {category} institutions with parameter scores that year (1st = highest). 'Difference' = "
              f"highest minus lowest value among the chosen institutions on that parameter.")
    return ChartResult(fig, table, insight, method, "grouped bar chart" if view == "bar" else "matrix heatmap")


def gap_finder(param_high: str = "rpc", param_low: str = "tlr", year: int | None = None, category: str = "Overall",
               n_labels: int = 6) -> ChartResult:
    """Answers questions like: "Which institutions have high research scores but relatively low teaching
    scores?" (Q5.2, Q5.3)

    Definition: "high on A but relatively low on B" = A above the median of A AND B below the median
    of B, among the institutions of the same category-year (medians, so a few extreme values do
    not move the dividing lines).
    Method: scatterplot with B on the x-axis and A on the y-axis; a dashed line at each median splits
    it into four quadrants, and the top-left quadrant (high A, low B) is highlighted. Inside it,
    institutions are sorted by the gap in z-scores, z(A) - z(B), where z = (value - mean) / SD: how
    many standard deviations above average on A minus on B (this puts both parameters on the same
    footing even though their typical levels differ). The n_labels largest gaps are labelled.
    """
    rows, category, year, params = _with_parameters(category, year)
    hi = check_column(param_high, category, rows)
    lo = check_column(param_low, category, rows)
    if hi == lo or "score" in (hi, lo) or "rank" in (hi, lo):
        raise NirfInputError("Please choose two different parameters (e.g. param_high='rpc', param_low='tlr').")
    d = rows.dropna(subset=[hi, lo]).copy()
    med_hi, med_lo = d[hi].median(), d[lo].median()
    d["z_high"] = (d[hi] - d[hi].mean()) / d[hi].std()
    d["z_low"] = (d[lo] - d[lo].mean()) / d[lo].std()
    d["z_gap"] = d["z_high"] - d["z_low"]
    d["in_quadrant"] = d[hi].gt(med_hi) & d[lo].lt(med_lo)
    d["label"] = d["institution_key"].map(chart_labels(d["institution_key"]))
    quad = d[d["in_quadrant"]].sort_values("z_gap", ascending=False)
    label_keys = quad["institution_key"].head(max(int(n_labels), 0)).tolist()

    fig = go.Figure()
    groups = ((~d["in_quadrant"], "Other institutions", OTHER, 8),
              (d["in_quadrant"], f"High {SHORT[hi]}, low {SHORT[lo]}", CATEGORICAL[1], 10))
    for mask, name, color, size in groups:
        t = d[mask]
        fig.add_trace(go.Scatter(
            x=t[lo], y=t[hi], mode="markers", name=name, marker=highlight_marker(color, size, 0.85),
            customdata=np.stack([t["canonical_name"], t["rank_raw"], t["z_gap"].round(2)], axis=1),
            hovertemplate=(f"<b>%{{customdata[0]}}</b><br>Rank %{{customdata[1]}}<br>{SHORT[hi]}: %{{y:.2f}} · "
                           f"{SHORT[lo]}: %{{x:.2f}}<br>z-gap ({SHORT[hi]} − {SHORT[lo]}): %{{customdata[2]}}"
                           f"<extra></extra>")))
    fig.add_vline(x=med_lo, line=dict(color=INK_SECONDARY, width=1, dash="dash"),
                  annotation_text=f"median {SHORT[lo]} {med_lo:.1f}", annotation_position="bottom right",
                  annotation_font=dict(size=11, color=INK_SECONDARY))
    fig.add_hline(y=med_hi, line=dict(color=INK_SECONDARY, width=1, dash="dash"),
                  annotation_text=f"median {SHORT[hi]} {med_hi:.1f}", annotation_position="bottom right",
                  annotation_font=dict(size=11, color=INK_SECONDARY))
    fig.add_annotation(text=f"<b>high {SHORT[hi]}, low {SHORT[lo]}</b>", xref="x domain", yref="y domain", x=0.01,
                       y=0.99, xanchor="left", yanchor="top", showarrow=False, font=dict(color=CATEGORICAL[1], size=12))
    fig.update_xaxes(title_text=LABELS[lo], showgrid=True)
    fig.update_yaxes(title_text=LABELS[hi])
    fig.update_layout(legend=dict(orientation="h", x=0, y=1.0, yanchor="bottom"))
    lab = d.set_index("institution_key").loc[label_keys]
    label_points(fig, lab[lo], lab[hi], lab["label"], padded_range(d[lo]), padded_range(d[hi]),
                 avoid_x=d[lo], avoid_y=d[hi])

    if len(quad):
        best = quad.iloc[0]
        title = (f"{len(quad)} {category} institutions in {year} score above the median on {SHORT[hi]} but below it "
                 f"on {SHORT[lo]}")
        insight = (f"In {category} {year}, {len(quad)} of {len(d)} institutions have {SHORT[hi]} above the median "
                   f"({med_hi:.1f}) but {SHORT[lo]} below the median ({med_lo:.1f}). The clearest case is "
                   f"{best['canonical_name']} (rank {best['rank_raw']}: {SHORT[hi]} {best[hi]:.1f}, {SHORT[lo]} "
                   f"{best[lo]:.1f}, z-gap {best['z_gap']:.2f})"
                   + (f", followed by {', '.join(quad['label'].iloc[1:4])}." if len(quad) > 1 else "."))
    else:
        title = f"No {category} institution in {year} is above the median on {SHORT[hi]} and below it on {SHORT[lo]}"
        insight = (f"In {category} {year}, no institution combines {SHORT[hi]} above the median ({med_hi:.1f}) with "
                   f"{SHORT[lo]} below the median ({med_lo:.1f}); the two parameters rise and fall together here.")
    finish(fig, title, f"{category} ranking {year} · dashed lines = medians · labelled: the {min(len(quad), int(n_labels))} "
           f"largest gaps", legend_title="Group")
    method = (f"We take the {len(d)} {category} institutions of {year} with both {SHORT[hi]} and {SHORT[lo]} published. "
              f"'High' and 'low' are relative to the median of the same year and category (median = middle value; half "
              f"of the institutions are above it). The top-left quadrant holds institutions above the median on "
              f"{SHORT[hi]} and below the median on {SHORT[lo]}. To rank them we convert both parameters to z-scores "
              f"(value − mean) / SD, which puts them on the same scale even though their typical levels differ, and "
              f"sort by z({SHORT[hi]}) − z({SHORT[lo]}).")
    table = (quad[["label", "canonical_name", "state", "rank_raw", "score", hi, lo, "z_high", "z_low", "z_gap"]]
             .rename(columns={"label": "institution", "canonical_name": "full_name", "rank_raw": "rank",
                              hi: SHORT[hi], lo: SHORT[lo], "z_high": f"z_{hi}", "z_low": f"z_{lo}"})
             .round(2).reset_index(drop=True))
    if table.empty:
        table = pd.DataFrame({"institution": ["none"], "note": [insight]})
    table.attrs.update(median_high=med_hi, median_low=med_lo, n=len(d))
    return ChartResult(fig, table, insight, method, "scatterplot")


def improved_despite_decline(category: str = "Overall", start_year: int | None = None, end_year: int | None = None,
                             n: int = 12) -> ChartResult:
    """Answers questions like: "Which institutions have improved their overall scores despite declining scores
    in one or more parameters?" (Q5.4)

    Definition: change = value in end_year - value in start_year, for the overall score and each
    parameter. An institution qualifies when its overall score rose (change > 0) while at least one
    parameter fell (change < 0).
    Method: keep institutions with published scores in both years, compute every change, keep those
    that qualify and sort them by overall score gain. The table lists all of them; the chart shows
    the first n as small-multiple bar charts (one small chart per institution, same y-axis for all):
    one bar per parameter change (teal = rose, coral = fell) and the overall-score change as a dark bar.
    Defaults: the first and last year of the category.
    """
    df = load_master()
    category = check_category(category, df)
    available = category_years(category, df)
    start_year = check_year(available[0] if start_year is None else start_year, category, df)
    end_year = check_year(available[-1] if end_year is None else end_year, category, df)
    if start_year >= end_year:
        raise NirfInputError(f"The start year ({start_year}) must be before the end year ({end_year}).")
    cat = filter_df(df, categories=category, years=[start_year, end_year])
    params = [p for p in parameters_of(cat) if cat.loc[cat["year"].eq(start_year), p].notna().any()
              and cat.loc[cat["year"].eq(end_year), p].notna().any()]
    if not params:
        raise NirfInputError(f"{category} has no parameter scores published in both {start_year} and {end_year}.")
    cols = ["score"] + params
    a = cat[cat["year"].eq(start_year)].dropna(subset=cols).set_index("institution_key")
    b = cat[cat["year"].eq(end_year)].dropna(subset=cols).set_index("institution_key")
    both = a.index.intersection(b.index)
    if both.empty:
        raise NirfInputError(f"No {category} institution has published scores in both {start_year} and {end_year}.")
    change = (b.loc[both, cols] - a.loc[both, cols]).astype(float)
    improved = change[change["score"] > 0]
    fell = improved[params].lt(0)
    q = improved[fell.any(axis=1)].sort_values("score", ascending=False)
    if q.empty:
        raise NirfInputError(f"No {category} institution improved its overall score between {start_year} and "
                             f"{end_year} while a parameter declined.")
    labels = chart_labels(q.index)

    table = pd.DataFrame({"institution": [labels[k] for k in q.index],
                          "full_name": b.loc[q.index, "canonical_name"].values,
                          f"rank_{start_year}": a.loc[q.index, "rank_raw"].values,
                          f"rank_{end_year}": b.loc[q.index, "rank_raw"].values,
                          f"score_{start_year}": a.loc[q.index, "score"].values,
                          f"score_{end_year}": b.loc[q.index, "score"].values,
                          "score_change": q["score"].round(2).values})
    for p in params:
        table[f"{SHORT[p]}_change"] = q[p].round(2).values
    table["parameters_declined"] = [", ".join(SHORT[p] for p in params if fell.at[k, p]) for k in q.index]
    table["n_declined"] = fell.loc[q.index].sum(axis=1).astype(int).values

    show = q.head(max(int(n), 1))
    cols_n = 4 if len(show) > 6 else min(3, len(show))
    rows_n = int(np.ceil(len(show) / cols_n))
    fig = make_subplots(rows=rows_n, cols=cols_n, shared_yaxes=True, shared_xaxes=True,
                        subplot_titles=[short_name(labels[k], 30) for k in show.index], vertical_spacing=0.12 / max(rows_n - 1, 1) + 0.06,
                        horizontal_spacing=0.025)
    xs = [SHORT[p] for p in params] + ["Overall"]
    for i, k in enumerate(show.index):
        r, c = i // cols_n + 1, i % cols_n + 1
        vals = [show.at[k, p] for p in params] + [show.at[k, "score"]]
        colors = [UP if v > 0 else DOWN for v in vals[:-1]] + [INK]
        fig.add_trace(go.Bar(
            x=xs, y=vals, marker_color=colors, showlegend=False,
            customdata=[LABELS[p] for p in params] + ["Overall score"],
            hovertemplate=(f"<b>{b.at[k, 'canonical_name']}</b><br>%{{customdata}}: %{{y:+.2f}} points "
                           f"({start_year}→{end_year})<extra></extra>")), row=r, col=c)
    for name, color in (("Parameter rose", UP), ("Parameter fell", DOWN), ("Overall score change", INK)):
        fig.add_trace(go.Bar(x=[None], y=[None], name=name, marker_color=color), row=1, col=1)
    fig.update_yaxes(zeroline=True, zerolinecolor=INK_SECONDARY, zerolinewidth=1)
    fig.update_yaxes(title_text="Change (points)", col=1)
    fig.update_xaxes(tickfont=dict(size=10), showline=True)
    fig.update_xaxes(title_text="Parameter", title_font=dict(size=11), row=rows_n)
    fig.update_annotations(font=dict(size=12, color=INK))
    fig.update_layout(bargap=0.2, margin=dict(t=130))

    common = fell.loc[q.index].sum().sort_values(ascending=False)
    top = q.index[0]
    title = (f"{len(q)} of {len(improved)} {category} institutions raised their score {start_year}→{end_year} "
             f"while at least one parameter fell")
    insight = (f"Of the {len(both)} {category} institutions scored in both {start_year} and {end_year}, {len(improved)} "
               f"improved their overall score, and {len(q)} of those did so despite a fall in at least one parameter "
               f"(most often {SHORT[common.index[0]]}: {int(common.iloc[0])} institutions). The largest such gain is "
               f"{b.at[top, 'canonical_name']} ({signed(q.at[top, 'score'], 1)} points, although "
               f"{table.at[0, 'parameters_declined']} fell).")
    finish(fig, title, f"{category} · change {start_year}→{end_year} · first {len(show)} of {len(q)} by overall gain · "
           f"every small chart uses the same scale", note="NIRF adjusted some sub-metrics over the years, so part of a "
           "change can come from the method.", height=170 + 210 * rows_n, legend_title="Change")
    method = (f"For each {category} institution with published scores in both {start_year} and {end_year} "
              f"({len(both)}), change = {end_year} value − {start_year} value for the overall score and for each "
              f"parameter ({', '.join(SHORT[p] for p in params)}). An institution qualifies if its overall score change "
              f"is positive and at least one parameter change is negative. That is possible because the overall score "
              f"is a weighted sum: a gain on a heavily weighted parameter can outweigh a loss on another. The table "
              f"lists all {len(q)}, sorted by overall gain; the chart shows the first {len(show)} as small multiples "
              f"(the same small bar chart repeated per institution with a shared y-axis, so bar lengths can be "
              f"compared across panels).")
    return ChartResult(fig, table, insight, method, "small-multiple bar charts")


def strongest_weakest_gap(year: int | None = None, category: str = "Overall", n: int = 15) -> ChartResult:
    """Answers questions like: "Which institutions have the largest difference between their strongest and
    weakest parameters?" (Q5.5)

    Definition: gap = highest parameter score - lowest parameter score of the same institution
    (all parameters are out of 100). A large gap = a lopsided profile; a small gap = balanced.
    Method: compute the gap for every institution of the category-year, sort from largest to
    smallest, and draw the n largest as a lollipop chart (stem length = gap). The hover names the
    strongest and the weakest parameter.
    """
    rows, category, year, params = _with_parameters(category, year)
    n = int(n)
    if n < 1:
        raise NirfInputError("n must be at least 1.")
    d = rows.copy()
    vals = d[params].astype(float)
    d["strongest"] = vals.idxmax(axis=1).map(SHORT)
    d["weakest"] = vals.idxmin(axis=1).map(SHORT)
    d["strongest_value"] = vals.max(axis=1)
    d["weakest_value"] = vals.min(axis=1)
    d["gap"] = d["strongest_value"] - d["weakest_value"]
    d = d.sort_values(["gap", "rank"], ascending=[False, True])
    labels = chart_labels(d["institution_key"])
    d["institution"] = d["institution_key"].map(labels)
    top = d.head(n).iloc[::-1]

    fig = go.Figure()
    add_lollipops(
        fig, top["gap"], top["institution"], [CATEGORICAL[0]] * len(top),
        text=[f"{s} − {w}" for s, w in zip(top["strongest"], top["weakest"])],
        customdata=np.stack([top["canonical_name"], top["rank_raw"], top["strongest"], top["strongest_value"],
                             top["weakest"], top["weakest_value"]], axis=1),
        hovertemplate=("<b>%{customdata[0]}</b> (rank %{customdata[1]})<br>Strongest: %{customdata[2]} "
                       "%{customdata[3]:.2f}<br>Weakest: %{customdata[4]} %{customdata[5]:.2f}<br>Gap: %{x:.2f} "
                       "points<extra></extra>"))
    fig.update_xaxes(title_text="Gap: strongest − weakest parameter (points)", showgrid=True,
                     range=[0, top["gap"].max() * 1.15])
    fig.update_yaxes(title_text="Institution", showgrid=False)

    first = d.iloc[0]
    pair = (d["strongest"] + " − " + d["weakest"]).value_counts()
    title = (f"{first['institution']} has the most lopsided profile in {category} {year}: {first['strongest']} "
             f"{first['strongest_value']:.0f} vs {first['weakest']} {first['weakest_value']:.0f}")
    insight = (f"In {category} {year}, {first['canonical_name']} has the largest gap between its strongest and weakest "
               f"parameter ({first['strongest']} {first['strongest_value']:.1f} − {first['weakest']} "
               f"{first['weakest_value']:.1f} = {first['gap']:.1f} points). Across all {len(d)} institutions the median "
               f"gap is {d['gap'].median():.1f}; the most common pattern is strongest {pair.index[0].split(' − ')[0]}, "
               f"weakest {pair.index[0].split(' − ')[1]} ({pair.iloc[0]} institutions).")
    finish(fig, title, f"{category} ranking {year} · the {len(top)} largest gaps of {len(d)} institutions · label = "
           f"strongest − weakest parameter", note="Parameters differ in typical level (e.g. PR is usually far below GO), "
           "so part of every gap reflects how hard each parameter is.", height=max(420, 170 + 30 * len(top)))
    method = (f"For each of the {len(d)} {category} institutions of {year} with all parameters published "
              f"({', '.join(SHORT[p] for p in params)}, each out of 100) we find the highest and the lowest of its "
              f"parameter scores; gap = highest − lowest. We sort by gap and draw the {len(top)} largest as a lollipop "
              f"chart (a bar chart drawn as a thin stem with a dot, which keeps a long sorted list easy to read).")
    table = (d[["institution", "canonical_name", "rank_raw", "score", "strongest", "strongest_value", "weakest",
                "weakest_value", "gap"]]
             .rename(columns={"canonical_name": "full_name", "rank_raw": "rank"}).round(2).reset_index(drop=True))
    return ChartResult(fig, table, insight, method, "lollipop chart")


def parameter_pca(year: int | None = None, category: str = "Overall") -> ChartResult:
    """Answers questions like: "Can the five parameters be summarised in two numbers, and do the top-ranked
    institutions stand apart?" (multivariate overview)

    Definition: principal component analysis (PCA). Each parameter is first turned into a z-score
    ((value - mean) / SD) so all five count equally. PC1 is the direction through the cloud of
    institutions along which they differ the most; PC2 is the next-most-varied direction at right
    angles to PC1. Each institution gets a PC1 and a PC2 value: a weighted sum of its five z-scores
    (the weights are the "loadings"). The % of variance says how much of the institutions'
    differences each axis keeps.
    Method: z-scores -> singular value decomposition (numpy) -> scatterplot of PC1 vs PC2, coloured
    by rank band.
    """
    rows, category, year, params = _with_parameters(category, year)
    if len(rows) < len(params) + 2:
        raise NirfInputError(f"Only {len(rows)} {category} institutions in {year} have all parameters; PCA needs more.")
    X = rows[params].astype(float).to_numpy()
    Z = (X - X.mean(axis=0)) / X.std(axis=0, ddof=1)
    _, s, vt = np.linalg.svd(Z, full_matrices=False)
    explained = s ** 2 / np.sum(s ** 2)
    for i in range(len(vt)):                 # sign convention: PC points towards "higher parameters"
        if vt[i].sum() < 0:
            vt[i] = -vt[i]
    scores = Z @ vt[:2].T
    d = rows.copy()
    d["pc1"], d["pc2"] = scores[:, 0], scores[:, 1]
    loadings = pd.DataFrame(vt[:2].T, index=[SHORT[p] for p in params], columns=["PC1", "PC2"]).round(3)

    def axis_words(col: str) -> str:
        load = loadings[col]
        if (load > 0).all() or (load < 0).all():
            return "all parameters together (" + ", ".join(load.abs().sort_values(ascending=False).index[:2]) + " most)"
        pos, neg = load.idxmax(), load.idxmin()
        return f"{pos} (+) vs {neg} (−)"

    d["group"] = d["rank_band"].fillna("unknown")
    groups = [b for b in BAND_ORDER if b in set(d["group"])]
    colors = dict(zip(groups, ordinal_ramp(len(groups))[::-1]))
    labels = chart_labels(d["institution_key"])
    fig = go.Figure()
    for g in groups:
        t = d[d["group"].eq(g)]
        fig.add_trace(go.Scatter(
            x=t["pc1"], y=t["pc2"], mode="markers", name=g, marker=dict(color=colors[g], size=9, opacity=0.9),
            customdata=np.stack([t["canonical_name"], t["rank_raw"]] + [t[p] for p in params], axis=1),
            hovertemplate=("<b>%{customdata[0]}</b><br>Rank %{customdata[1]}<br>PC1 %{x:.2f} · PC2 %{y:.2f}<br>"
                           + " · ".join(f"{SHORT[p]} %{{customdata[{i + 2}]:.1f}}" for i, p in enumerate(params))
                           + "<extra></extra>")))
    top3 = d.nsmallest(3, "rank")
    for _, r in top3.iterrows():
        fig.add_annotation(x=r["pc1"], y=r["pc2"], text=labels[r["institution_key"]], showarrow=True, arrowhead=0,
                           ax=24, ay=-22, font=dict(size=10, color=INK_SECONDARY), arrowcolor=INK_SECONDARY)
    fig.update_xaxes(title_text=f"PC1 ({100 * explained[0]:.0f}% of variance) · {axis_words('PC1')}", showgrid=True,
                     zeroline=True, zerolinecolor=OTHER)
    fig.update_yaxes(title_text=f"PC2 ({100 * explained[1]:.0f}% of variance)", zeroline=True, zerolinecolor=OTHER)

    r_score = float(np.corrcoef(d["pc1"], d["score"])[0, 1])
    two = 100 * (explained[0] + explained[1])
    title = (f"Two summary axes keep {two:.0f}% of the differences in {category} {year}; "
             f"PC1 {'tracks' if abs(r_score) >= 0.8 else 'is related to'} the overall score (r = {r_score:.2f})")
    insight = (f"In {category} {year}, PC1 explains {100 * explained[0]:.0f}% of the variation in the "
               f"{len(params)} parameters and weighs {axis_words('PC1')}; it correlates with the overall score at "
               f"r = {r_score:.2f}" + (", so it is essentially a general 'strength' axis" if r_score >= 0.8 else "")
               + f". PC2 adds "
               f"{100 * explained[1]:.0f}% and contrasts {axis_words('PC2')}: institutions high on PC2 are relatively "
               f"stronger on {loadings['PC2'].idxmax()} than their overall level suggests.")
    finish(fig, title, f"{category} ranking {year} · {len(d)} institutions · each dot = one institution · darker = "
           f"better rank band", legend_title="Rank band", height=560)
    method = (f"PCA (principal component analysis) on the {len(params)} parameters of the {len(d)} {category} "
              f"institutions of {year}. Step 1: turn every parameter into a z-score ((value − mean) / SD) so that each "
              f"counts equally. Step 2: find the direction along which institutions differ the most (PC1) and the "
              f"next one at right angles to it (PC2), using numpy's singular value decomposition. Each institution's "
              f"PC value is a weighted sum of its z-scores; the weights (loadings) are PC1: "
              + ", ".join(f"{k} {v:+.2f}" for k, v in loadings["PC1"].items()) + "; PC2: "
              + ", ".join(f"{k} {v:+.2f}" for k, v in loadings["PC2"].items())
              + f". % of variance = how much of the institutions' differences an axis keeps (all {len(params)} "
              f"axes together keep 100%). Signs are chosen so that PC1 grows with the parameters.")
    table = (d.assign(institution=d["institution_key"].map(labels))
             [["institution", "canonical_name", "rank_raw", "rank_band", "score", "pc1", "pc2"] + params]
             .rename(columns={"canonical_name": "full_name", "rank_raw": "rank", **{p: SHORT[p] for p in params}})
             .round(3).reset_index(drop=True))
    table.attrs.update(loadings=loadings, explained_variance=explained.round(4).tolist())
    return ChartResult(fig, table, insight, method, "PCA scatterplot")
