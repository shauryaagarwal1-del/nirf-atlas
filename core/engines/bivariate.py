"""Bivariate engine: how two numbers move together (Annexure A section 4, Q4.1-Q4.5).

Functions
  scatter_relation()          any two numeric attributes: scatter, least-squares line, r, rho, R squared, p, n
  correlation_with_overall()  correlation of each parameter with the overall score (sorted bar)
  correlation_over_time()     correlation of one parameter with the overall score, year by year (line)

Numbers available: score, the five parameters (TLR, RPC, GO, OI, PR; Research Institutions use
QnR, QlR, SFC, OI, PR instead) and the exact rank. Only institutions with both values published
are used. Correlation describes association, not cause. The overall score is a weighted sum of
the parameters, so every parameter is partly "inside" the score it is correlated with.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from core.data import (BAND_ORDER, LABELS, SHORT, NirfInputError, category_years, check_category, check_column, check_year,
                       filter_df, fmt_years, load_master, parameters_of)
from core.result import ChartResult
from core.stats import correlate, p_text, signed, strength
from core.theme import CATEGORICAL, DOWN, INK_SECONDARY, UP, color_map, finish, ordinal_blues

COLOR_BY = {"region", "state", "rank_band"}
MAX_STATE_COLORS = 7


def _category_year(category: str, year: int | None) -> tuple[pd.DataFrame, str, int]:
    df = load_master()
    category = check_category(category, df)
    year = check_year(category_years(category, df)[-1] if year is None else year, category, df)
    return filter_df(df, categories=category, years=year), category, year


def _stat_line(c: dict) -> str:
    return (f"Pearson r = {c['pearson_r']:.2f} · Spearman ρ = {c['spearman_rho']:.2f} · "
            f"R² = {c['r2']:.2f} · {p_text(c['pearson_p'])} · n = {c['n']}")


def scatter_relation(x: str = "rpc", y: str = "score", year: int | None = None, category: str = "Overall",
                     color_by: str | None = None, trendline: bool = True) -> ChartResult:
    """Answers questions like: "How strongly are RPC scores associated with overall scores?" (Q4.1, Q4.2, Q4.4)

    Definition: the association between two numbers across the institutions of one category-year.
    Method: one dot per institution; Pearson r (straight-line strength, -1 to +1), Spearman rho
    (same on ranks: any steady rise/fall, robust to outliers), R squared (share of y's variation
    explained by the straight line) and the p-value (chance of a correlation this strong if there
    were none). The least-squares line is the straight line with the smallest sum of squared
    vertical distances to the dots. color_by: None, "region", "state" or "rank_band".
    """
    cat, category, year = _category_year(category, year)
    x = check_column(x, category, cat)
    y = check_column(y, category, cat)
    if x == y:
        raise NirfInputError("Please choose two different numbers for x and y.")
    if color_by is not None and color_by not in COLOR_BY:
        raise NirfInputError(f"color_by must be one of: {', '.join(sorted(COLOR_BY))} (or None).")
    d = cat[cat[x].notna() & cat[y].notna()].copy()
    d[x], d[y] = d[x].astype(float), d[y].astype(float)
    if len(d) < 3:
        raise NirfInputError(f"Only {len(d)} {category} institutions in {year} have both {SHORT[x]} and {SHORT[y]}; "
                             f"at least 3 are needed for a correlation.")
    c = correlate(d[x], d[y])

    if color_by is None:
        d["group"] = "Institutions"
        groups = ["Institutions"]
        colors = {"Institutions": CATEGORICAL[0]}
    elif color_by == "rank_band":
        d["group"] = d["rank_band"].fillna("unknown")
        groups = [b for b in BAND_ORDER if b in set(d["group"])]
        colors = dict(zip(groups, ordinal_blues(len(groups))[::-1]))
    else:
        d["group"] = d[color_by]
        groups = d["group"].value_counts().index.tolist()
        if color_by == "state" and len(groups) > MAX_STATE_COLORS:
            keep = groups[:MAX_STATE_COLORS]
            d.loc[~d["group"].isin(keep), "group"] = "Other states"
            groups = keep + ["Other states"]
        colors = color_map(groups, other_label="Other states")

    fig = go.Figure()
    for gname in groups:
        t = d[d["group"].eq(gname)]
        fig.add_trace(go.Scatter(
            x=t[x], y=t[y], mode="markers", name=gname, marker=dict(color=colors[gname], size=9, opacity=0.85),
            customdata=np.stack([t["canonical_name"], t["state"], t["rank_raw"]], axis=1),
            hovertemplate=(f"<b>%{{customdata[0]}}</b> (%{{customdata[1]}})<br>Rank %{{customdata[2]}}"
                           f"<br>{SHORT[x]}: %{{x:.2f}}<br>{SHORT[y]}: %{{y:.2f}}<extra></extra>")))
    if trendline and pd.notna(c["slope"]):
        xs = np.array([d[x].min(), d[x].max()])
        fig.add_trace(go.Scatter(
            x=xs, y=c["intercept"] + c["slope"] * xs, mode="lines", name="Least-squares line",
            line=dict(color=INK_SECONDARY, width=2),
            hovertemplate=(f"{SHORT[y]} = {c['intercept']:.2f} + {c['slope']:.3f} × {SHORT[x]}"
                           f"<br>R² = {c['r2']:.2f}<extra></extra>")))
    fig.update_xaxes(title_text=LABELS[x], showgrid=True, autorange="reversed" if x == "rank" else True)
    fig.update_yaxes(title_text=LABELS[y], autorange="reversed" if y == "rank" else True)
    if color_by is None:
        fig.update_layout(legend=dict(orientation="h", x=0, y=1.0, yanchor="bottom"))

    words = strength(c["pearson_r"])
    title = f"{SHORT[x]} and {SHORT[y]}: {words} relationship in {category} {year} (r = {c['pearson_r']:.2f})"
    insight = (f"In {category} {year}, {SHORT[x]} and {SHORT[y]} have a {words} relationship ({_stat_line(c)}); "
               f"the straight line explains {100 * c['r2']:.0f}% of the variation in {SHORT[y]}"
               + (f", and 10 more {SHORT[x]} points go with {signed(10 * c['slope'], 1)} {SHORT[y]} points on average."
                  if "rank" not in (x, y) else "."))
    if abs(c["spearman_rho"] - c["pearson_r"]) >= 0.15:
        insight += (f" Spearman (ρ = {c['spearman_rho']:.2f}) differs from Pearson, so the pattern is not a "
                    f"straight line or a few outliers matter.")
    note = None
    if "score" in (x, y) and "rank" not in (x, y):
        note = "The overall score is a weighted sum of the parameters, so part of this association is built in."
    finish(fig, title, _stat_line(c), note=note, legend_title=None if color_by is None else color_by.replace("_", " ").title())
    method = (f"We take the {c['n']} {category} institutions of {year} with both {SHORT[x]} and {SHORT[y]} published "
              f"and compute: Pearson r (how close the dots are to a straight line, −1 to +1), Spearman ρ "
              f"(Pearson on the ranks of the values, so it captures any steadily rising or falling pattern and is "
              f"robust to outliers), R² = r² (share of {SHORT[y]}'s variation explained by the line) and "
              f"the p-value (chance of seeing a correlation this strong if there were truly none; < 0.05 = "
              f"significant). The trend line is the least-squares line {SHORT[y]} = {c['intercept']:.2f} + "
              f"{c['slope']:.3f} × {SHORT[x]}. Strength words: |r| < 0.2 very weak, < 0.4 weak, < 0.6 "
              f"moderate, < 0.8 strong, otherwise very strong. Only ranked institutions with published scores are "
              f"included, i.e. the top of the list, which can make correlations weaker than over all institutions.")
    table = (d[["canonical_name", "state", "region", "rank_raw", "rank_band", x, y]]
             .rename(columns={"canonical_name": "institution", "rank_raw": "rank"}).reset_index(drop=True))
    table.attrs["stats"] = c
    return ChartResult(fig, table, insight, method, "scatter")


def correlation_with_overall(year: int | None = None, category: str = "Overall") -> ChartResult:
    """Answers questions like: "Which NIRF parameter has the strongest correlation with the overall score?" (Q4.3)

    Definition: Pearson r between each parameter and the overall score across institutions of one
    category-year (Spearman rho and p-values in the table).
    Method: compute r for every parameter the category publishes, sort, and draw a bar per parameter.
    """
    cat, category, year = _category_year(category, year)
    if cat["score"].notna().sum() < 3:
        raise NirfInputError(f"NIRF published no overall scores for {category} {year}.")
    params = parameters_of(cat)
    if not params:
        raise NirfInputError(f"NIRF published no parameter scores for {category} {year}.")
    rows = []
    for p in params:
        c = correlate(cat[p], cat["score"])
        rows.append({"parameter": SHORT[p], "name": LABELS[p], "pearson_r": c["pearson_r"], "p_value": c["pearson_p"],
                     "spearman_rho": c["spearman_rho"], "r2": c["r2"], "n": c["n"]})
    table = pd.DataFrame(rows).sort_values("pearson_r", ascending=False).reset_index(drop=True)
    plot = table.iloc[::-1]

    fig = go.Figure(go.Bar(
        x=plot["pearson_r"], y=plot["name"], orientation="h",
        marker_color=[UP if r >= 0 else DOWN for r in plot["pearson_r"]],
        text=[f"{r:.2f}" for r in plot["pearson_r"]], textposition="outside", cliponaxis=False, showlegend=False,
        customdata=np.stack([plot["spearman_rho"], plot["p_value"].map(p_text), plot["n"]], axis=1),
        hovertemplate=("<b>%{y}</b><br>Pearson r = %{x:.3f}<br>Spearman ρ = %{customdata[0]:.3f}"
                       "<br>%{customdata[1]} · n = %{customdata[2]}<extra></extra>")))
    lo = min(0, table["pearson_r"].min())
    fig.update_xaxes(title_text="Pearson correlation with the overall score (r)", showgrid=True,
                     range=[lo - 0.12 if lo < 0 else 0, 1.08], zeroline=True, zerolinecolor=INK_SECONDARY)
    fig.update_yaxes(title_text=None, showgrid=False)

    top, low = table.iloc[0], table.iloc[-1]
    title = f"{top['parameter']} tracks the overall score most closely in {category} {year} (r = {top['pearson_r']:.2f})"
    insight = (f"In {category} {year}, {top['name']} has the strongest correlation with the overall score "
               f"(r = {top['pearson_r']:.2f}, {p_text(top['p_value'])}), followed by {table.iloc[1]['parameter']} "
               f"(r = {table.iloc[1]['pearson_r']:.2f}); the weakest is {low['parameter']} (r = {low['pearson_r']:.2f}).")
    finish(fig, title, f"{category} ranking {year} · {int(table['n'].max())} institutions with published scores",
           note="Each parameter is a weighted part of the overall score; r reflects both its weight and how much "
                "institutions differ on it.", height=420)
    method = (f"For each parameter published for {category} in {year}, we compute the Pearson correlation r with the "
              f"overall score across all institutions that have both values. r runs from −1 to +1; the closer to "
              f"+1, the more institutions that score high on the parameter also score high overall. We also report "
              f"Spearman ρ (correlation of ranks) and the p-value. Because the overall score is a weighted sum "
              f"of the parameters, a parameter correlates strongly when it has a large weight and/or institutions "
              f"differ a lot on it.")
    return ChartResult(fig, table.round(4), insight, method, "bar")


def correlation_over_time(param: str = "rpc", category: str = "Overall") -> ChartResult:
    """Answers questions like: "Has the correlation between research scores and overall scores changed
    from 2017 to 2025?" (Q4.5)

    Definition: for every year, Pearson r (and Spearman rho) between the chosen parameter and the
    overall score across the institutions ranked that year.
    Method: compute both coefficients year by year and draw them as two lines (hover: p-value, n).
    """
    df = load_master()
    category = check_category(category, df)
    cat = filter_df(df, categories=category)
    param = check_column(param, category, cat)
    if param == "score":
        raise NirfInputError("Choose a parameter (e.g. RPC, PR) to correlate with the overall score.")
    rows = []
    for yr, t in cat.groupby("year"):
        c = correlate(t[param], t["score"])
        if c["n"] >= 3 and pd.notna(c["pearson_r"]):
            rows.append({"year": int(yr), "pearson_r": c["pearson_r"], "spearman_rho": c["spearman_rho"],
                         "p_value": c["pearson_p"], "r2": c["r2"], "n": c["n"]})
    if len(rows) < 2:
        raise NirfInputError(f"{SHORT[param]} and the overall score are published together for {category} in fewer "
                             f"than two years, so there is no trend to show.")
    table = pd.DataFrame(rows)

    fig = go.Figure()
    for col, name, color in (("pearson_r", "Pearson r", CATEGORICAL[0]), ("spearman_rho", "Spearman ρ", CATEGORICAL[1])):
        fig.add_trace(go.Scatter(
            x=table["year"], y=table[col], name=name, mode="lines+markers", line=dict(color=color),
            marker=dict(color=color), customdata=np.stack([table["p_value"].map(p_text), table["n"]], axis=1),
            hovertemplate=f"<b>{name}</b> %{{x}}: %{{y:.3f}}<br>%{{customdata[0]}} · n = %{{customdata[1]}}<extra></extra>"))
    lo = min(0, table[["pearson_r", "spearman_rho"]].min().min())
    fig.update_yaxes(title_text=f"Correlation of {SHORT[param]} with the overall score",
                     range=[lo - 0.05 if lo < 0 else 0, 1.02], zeroline=True, zerolinecolor=INK_SECONDARY)
    fig.update_xaxes(title_text="Year", dtick=1)
    fig.update_layout(hovermode="x unified")

    a, z = table.iloc[0], table.iloc[-1]
    hi, lo_row = table.loc[table["pearson_r"].idxmax()], table.loc[table["pearson_r"].idxmin()]
    change = z["pearson_r"] - a["pearson_r"]
    verb = "strengthened" if change > 0.05 else "weakened" if change < -0.05 else "stayed about the same"
    title = (f"The {SHORT[param]}-score correlation in {category} {verb}: r = {a['pearson_r']:.2f} in {int(a.year)} "
             f"→ {z['pearson_r']:.2f} in {int(z.year)}")
    insight = (f"In {category}, the correlation between {SHORT[param]} and the overall score went from r = "
               f"{a['pearson_r']:.2f} in {int(a.year)} to {z['pearson_r']:.2f} in {int(z.year)} "
               f"({signed(change, 2)}); it was highest in {int(hi.year)} ({hi['pearson_r']:.2f}) and lowest in "
               f"{int(lo_row.year)} ({lo_row['pearson_r']:.2f}).")
    years = table["year"].tolist()
    ns = table.groupby("n")["year"].apply(fmt_years)
    note = ("The number of scored institutions changes: " + "; ".join(f"{n} in {y}" for n, y in ns.items()) + "."
            if table["n"].max() > 1.1 * table["n"].min() else None)
    finish(fig, title, f"{category} ranking, {fmt_years(years)} · {LABELS[param]} vs overall score", note=note,
           legend_title="Coefficient")
    method = (f"For every year we take the {category} institutions with both {SHORT[param]} and the overall score "
              f"published and compute Pearson r (straight-line association) and Spearman ρ (association of the "
              f"ranks). One point per year; a rising line means {SHORT[param]} and the overall score move together "
              f"more closely. Differences of a few hundredths between years are within normal year-to-year "
              f"variation; NIRF also adjusts sub-metrics and the number of scored institutions over time.")
    return ChartResult(fig, table.round(4), insight, method, "line")
