"""Bivariate engine: how two numbers move together (Annexure A section 4, Q4.1-Q4.5).

Functions
  scatter_relation()          any two numeric attributes: scatterplot (optionally grouped by colour: region,
                              state, rank band, or category when several categories are pooled) with the
                              least-squares line; r, rho, R squared, p, n
  correlation_with_overall()  correlation of each parameter with the overall score (correlogram of score and
                              all parameters, or view="bar": ranked bar chart of r)
  correlation_over_time()     correlation of one parameter with the overall score, year by year (multi-series
                              line chart: Pearson and Spearman)

Every chart type is one of the types listed in docs/allowed_charts.md.

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
from core.theme import (CATEGORICAL, CROSS_CATEGORY_NOTE, DIVERGING, DOWN, INK_SECONDARY, UP, color_map, finish,
                        ordinal_ramp)

COLOR_BY = {"region", "state", "rank_band", "category"}
MAX_STATE_COLORS = 7


def _category_year(category: str, year: int | None) -> tuple[pd.DataFrame, str, int]:
    df = load_master()
    category = check_category(category, df)
    year = check_year(category_years(category, df)[-1] if year is None else year, category, df)
    return filter_df(df, categories=category, years=year), category, year


def _stat_line(c: dict) -> str:
    return (f"Pearson r = {c['pearson_r']:.2f} · Spearman ρ = {c['spearman_rho']:.2f} · "
            f"R² = {c['r2']:.2f} · {p_text(c['pearson_p'])} · n = {c['n']}")


def _pooled_year(categories: list[str], year: int | None) -> tuple[pd.DataFrame, list[str], int, list[str]]:
    """Rows of several categories in one year; categories without that year are left out (and listed)."""
    df = load_master()
    cats = list(dict.fromkeys(check_category(c, df) for c in categories))
    if year is None:
        year = max(category_years(c, df)[-1] for c in cats)
    year = int(year)
    have = [c for c in cats if year in category_years(c, df)]
    if not have:
        raise NirfInputError(f"None of {', '.join(cats)} has a NIRF ranking in {year}.")
    return filter_df(df, categories=have, years=year), have, year, [c for c in cats if c not in have]


def scatter_relation(x: str = "rpc", y: str = "score", year: int | None = None, category="Overall",
                     color_by: str | None = None, trendline: bool = True, top_n: int | None = None) -> ChartResult:
    """Answers questions like: "How strongly are RPC scores associated with overall scores?" (Q4.1, Q4.2, Q4.4)

    Definition: the association between two numbers across the institutions of one category-year.
    Method: one dot per institution; Pearson r (straight-line strength, -1 to +1), Spearman rho
    (same on ranks: any steady rise/fall, robust to outliers), R squared (share of y's variation
    explained by the straight line) and the p-value (chance of a correlation this strong if there
    were none). The least-squares line is the straight line with the smallest sum of squared
    vertical distances to the dots. color_by: None, "region", "state", "rank_band" or "category".
    category can also be a list: the categories' institutions of that year are pooled into one
    scatterplot (an institution ranked in two categories is then two dots), coloured by category,
    with a visible note that scores of different categories are not on the same scale.
    top_n: keep only institutions certainly ranked 1..top_n (e.g. 50), to ask "among the top 50".
    """
    categories = [category] if isinstance(category, str) else list(category)
    if len(categories) > 1:
        cat, cats, year, missing = _pooled_year(categories, year)
        category = " + ".join(cats)
    else:
        cat, category, year = _category_year(categories[0], year)
        cats, missing = [category], []
    x = check_column(x, category, cat)
    y = check_column(y, category, cat)
    if x == y:
        raise NirfInputError("Please choose two different numbers for x and y.")
    if color_by is not None and color_by not in COLOR_BY:
        raise NirfInputError(f"color_by must be one of: {', '.join(sorted(COLOR_BY))} (or None).")
    d = cat[cat[x].notna() & cat[y].notna()].copy()
    if top_n:
        d = d[d["rank_upper"].le(int(top_n)).fillna(False).astype(bool)]
        category_words = f"{category} top {int(top_n)}"
    else:
        category_words = category
    d[x], d[y] = d[x].astype(float), d[y].astype(float)
    if len(d) < 3:
        raise NirfInputError(f"Only {len(d)} {category_words} institutions in {year} have both {SHORT[x]} and {SHORT[y]}; "
                             f"at least 3 are needed for a correlation.")
    c = correlate(d[x], d[y])

    if color_by is None:
        d["group"] = "Institutions"
        groups = ["Institutions"]
        colors = {"Institutions": CATEGORICAL[0]}
    elif color_by == "rank_band":
        d["group"] = d["rank_band"].fillna("unknown")
        groups = [b for b in BAND_ORDER if b in set(d["group"])]
        groups += ["unknown"] if d["group"].eq("unknown").any() else []
        colors = dict(zip(groups, ordinal_ramp(len(groups))[::-1]))
    else:
        d["group"] = d["category_std" if color_by == "category" else color_by]
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
            customdata=np.stack([t["canonical_name"], t["state"], t["rank_raw"], t["category_std"]], axis=1),
            hovertemplate=(f"<b>%{{customdata[0]}}</b> (%{{customdata[1]}})<br>%{{customdata[3]}} rank "
                           f"%{{customdata[2]}}<br>{SHORT[x]}: %{{x:.2f}}<br>{SHORT[y]}: %{{y:.2f}}<extra></extra>")))
    if trendline and pd.notna(c["slope"]):
        xs = np.array([d[x].min(), d[x].max()])
        fig.add_trace(go.Scatter(
            x=xs, y=c["intercept"] + c["slope"] * xs, mode="lines", name="Least-squares line",
            line=dict(color=INK_SECONDARY, width=2),
            hovertemplate=(f"{SHORT[y]} = {c['intercept']:.2f} + {c['slope']:.3f} × {SHORT[x]}"
                           f"<br>R² = {c['r2']:.2f}<extra></extra>")))
    fig.update_xaxes(title_text=LABELS[x] + (" (1 = best, on the right)" if x == "rank" else ""), showgrid=True,
                     autorange="reversed" if x == "rank" else True)
    fig.update_yaxes(title_text=LABELS[y] + (" (1 = best, at the top)" if y == "rank" else ""),
                     autorange="reversed" if y == "rank" else True)
    if color_by is None:
        fig.update_layout(legend=dict(orientation="h", x=0, y=1.0, yanchor="bottom"))

    words = strength(c["pearson_r"])
    title = f"{SHORT[x]} and {SHORT[y]}: {words} relationship in {category_words} {year} (r = {c['pearson_r']:.2f})"
    insight = (f"In {category_words} {year}, {SHORT[x]} and {SHORT[y]} have a {words} relationship ({_stat_line(c)}); "
               f"the straight line explains {100 * c['r2']:.0f}% of the variation in {SHORT[y]}"
               + (f", and 10 more {SHORT[x]} points go with {signed(10 * c['slope'], 1)} {SHORT[y]} points on average."
                  if "rank" not in (x, y) else "."))
    if "rank" in (x, y):
        other = SHORT[y] if x == "rank" else SHORT[x]
        insight += (f" A smaller rank is better, so a negative r means institutions with a higher {other} "
                    f"tend to be ranked better.")
    if abs(c["spearman_rho"] - c["pearson_r"]) >= 0.15:
        insight += (f" Spearman (ρ = {c['spearman_rho']:.2f}) differs from Pearson, so the pattern is not a "
                    f"straight line or a few outliers matter.")
    notes = []
    if len(cats) > 1:
        notes.append(CROSS_CATEGORY_NOTE + " Pooled here only to compare patterns.")
    if missing:
        notes.append(f"Not ranked in {year}, so left out: {', '.join(missing)}.")
    if "score" in (x, y) and "rank" not in (x, y):
        notes.append("The overall score is a weighted sum of the parameters, so part of this association is built in.")
    legend = {None: None, "rank_band": "Rank band"}.get(color_by, str(color_by).title())
    finish(fig, title, _stat_line(c), note="<br>".join(notes) or None, legend_title=legend)
    method = (f"We take the {c['n']} {category_words} institutions of {year} with both {SHORT[x]} and {SHORT[y]} published "
              f"and compute: Pearson r (how close the dots are to a straight line, −1 to +1), Spearman ρ "
              f"(Pearson on the ranks of the values, so it captures any steadily rising or falling pattern and is "
              f"robust to outliers), R² = r² (share of {SHORT[y]}'s variation explained by the line) and "
              f"the p-value (chance of seeing a correlation this strong if there were truly none; < 0.05 = "
              f"significant). The trend line is the least-squares line {SHORT[y]} = {c['intercept']:.2f} + "
              f"{c['slope']:.3f} × {SHORT[x]}. Strength words: |r| < 0.2 very weak, < 0.4 weak, < 0.6 "
              f"moderate, < 0.8 strong, otherwise very strong. Only ranked institutions with published scores are "
              f"included, i.e. the top of the list, which can make correlations weaker than over all institutions."
              + (" Several categories are pooled into one set of dots (one dot per institution and category), "
                 "although each category weighs the parameters differently." if len(cats) > 1 else ""))
    keep = list(dict.fromkeys(["canonical_name", "category_std", "state", "region", "rank_raw", "rank_band", x, y]))
    table = (d[keep].rename(columns={"canonical_name": "institution", "category_std": "category",
                                     "rank_raw": "published_rank"}).reset_index(drop=True))
    table.attrs["stats"] = c
    return ChartResult(fig, table, insight, method, "scatterplot")


def correlation_with_overall(year: int | None = None, category: str = "Overall",
                             view: str = "correlogram") -> ChartResult:
    """Answers questions like: "Which NIRF parameter has the strongest correlation with the overall score?" (Q4.3)

    Definition: Pearson r between each parameter and the overall score across institutions of one
    category-year (Spearman rho and p-values in the ranked table).
    Method: compute r for every pair of the overall score and the parameters the category publishes
    (score, TLR, RPC, GO, OI, PR; Research Institutions: QnR, QlR, SFC, OI, PR).
      view="correlogram" (default): correlation heatmap, one cell per pair with r printed in it
        (teal = positive, coral = negative, darker = stronger). The "Overall score" row answers the
        question; the other cells show how the parameters move with each other.
      view="bar": ranked horizontal bar chart of each parameter's r with the overall score.
    """
    view = str(view).lower()
    if view not in {"correlogram", "bar"}:
        raise NirfInputError("view must be 'correlogram' (correlation heatmap) or 'bar' (ranked bar chart of r).")
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

    top, low = table.iloc[0], table.iloc[-1]
    title = f"{top['parameter']} tracks the overall score most closely in {category} {year} (r = {top['pearson_r']:.2f})"
    insight = (f"In {category} {year}, {top['name']} has the strongest correlation with the overall score "
               f"(r = {top['pearson_r']:.2f}, {p_text(top['p_value'])}), followed by {table.iloc[1]['parameter']} "
               f"(r = {table.iloc[1]['pearson_r']:.2f}); the weakest is {low['parameter']} (r = {low['pearson_r']:.2f}).")
    weight_note = ("Each parameter is a weighted part of the overall score; r reflects both its weight and how much "
                   "institutions differ on it.")
    if view == "correlogram":
        return _correlogram(cat, params, category, year, title, insight, weight_note)
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

    finish(fig, title, f"{category} ranking {year} · {int(table['n'].max())} institutions with published scores · "
           f"ranked bar chart of r", note=weight_note, height=420)
    method = (f"For each parameter published for {category} in {year}, we compute the Pearson correlation r with the "
              f"overall score across all institutions that have both values. r runs from −1 to +1; the closer to "
              f"+1, the more institutions that score high on the parameter also score high overall. We also report "
              f"Spearman ρ (correlation of ranks) and the p-value. Because the overall score is a weighted sum "
              f"of the parameters, a parameter correlates strongly when it has a large weight and/or institutions "
              f"differ a lot on it. The bars are sorted from the strongest to the weakest r.")
    return ChartResult(fig, table.round(4), insight, method, "bar chart")


def _correlogram(cat: pd.DataFrame, params: list[str], category: str, year: int, title: str, insight: str,
                 note: str) -> ChartResult:
    """Correlation heatmap of the overall score and every published parameter (r printed in each cell).

    r for each pair uses the institutions that have both values (pairwise), exactly as correlate() does,
    so the "Overall score" row equals the bars of the ranked view.
    """
    cols = ["score"] + params
    d = cat[cols].astype("float64")
    corr = d.corr(method="pearson")                       # pairwise: rows missing either value are skipped
    has = d.notna().astype(int)
    n = has.T @ has                                       # institutions with both values, per pair
    names = [SHORT[c] for c in cols]

    fig = go.Figure(go.Heatmap(
        z=corr.values, x=names, y=names, zmin=-1, zmax=1, colorscale=DIVERGING,
        text=corr.round(2).values, texttemplate="%{text:.2f}", textfont=dict(size=13),
        customdata=n.values, xgap=2, ygap=2,
        colorbar=dict(title=dict(text="Pearson r", side="top"), tickvals=[-1, -0.5, 0, 0.5, 1], thickness=12),
        hovertemplate="<b>%{y} and %{x}</b><br>Pearson r = %{z:.3f}<br>n = %{customdata} institutions<extra></extra>"))
    fig.update_xaxes(showgrid=False, showline=False, ticks="", side="top", title_text=None)
    fig.update_yaxes(showgrid=False, showline=False, ticks="", autorange="reversed", title_text=None)
    fig.update_layout(margin=dict(t=130))

    pairs = corr.where(np.triu(np.ones(corr.shape, dtype=bool), k=1)).stack()
    pp = pairs.drop(index=[("score", p) for p in params], errors="ignore")    # parameter-parameter pairs only
    if len(pp):
        (a, b), r = pp.abs().idxmax(), pp.loc[pp.abs().idxmax()]
        insight += (f" Among the parameters themselves, {SHORT[a]} and {SHORT[b]} move together the most "
                    f"(r = {r:.2f}).")
    size = 140 + 62 * len(cols)
    finish(fig, title, f"{category} ranking {year} · correlogram: Pearson r for every pair, read the "
           f"'Overall score' row for the answer", note=note, height=max(460, size))
    method = (f"We take the {category} institutions of {year} and compute the Pearson correlation r for every pair of "
              f"the overall score and the {len(params)} parameters ({', '.join(SHORT[p] for p in params)}), each pair "
              f"using the institutions that have both values. The correlogram (correlation heatmap) shows one cell per "
              f"pair with r printed in it: teal = positive, coral = negative, darker = stronger; the diagonal is 1 "
              f"(every variable with itself) and the matrix is a mirror image across it. The 'Overall score' row "
              f"answers the question; the other cells show which parameters rise and fall together. r runs from −1 "
              f"to +1. Because the overall score is a weighted sum of the parameters, a parameter correlates "
              f"strongly when it has a large weight and/or institutions differ a lot on it. view='bar' draws the "
              f"same 'Overall score' row as a ranked bar chart.")
    table = corr.round(4).rename(index=dict(zip(cols, names)), columns=dict(zip(cols, names)))
    table.index.name = "variable"
    return ChartResult(fig, table.reset_index(), insight, method, "correlogram")


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
    return ChartResult(fig, table.round(4), insight, method, "multi-series line chart")
