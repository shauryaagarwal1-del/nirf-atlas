"""Univariate engine: one variable at a time (Annexure A section 3, Q3.1-Q3.5).

Functions
  score_distribution()  shape of the overall scores in one year (histogram with density curve (KDE),
                        mean and median lines)
  rank_distribution()   how many institutions sit in each rank band (stacked bar chart, exact vs band-only)
  summary_stats()       mean, median, min, max, SD, quartiles of the scores (table + box-and-whisker plot)
  quartile_shares()     % of institutions in each score quartile, two definitions (100% stacked bar chart)
  spread_by_category()  score spread of every category in one year (box-and-whisker plot per category)

Every chart type is one of the types listed in docs/allowed_charts.md.

Scores exist only for institutions with an exact rank: NIRF does not publish scores for positions
it shows only as bands (e.g. 101-150), and publishes no scores at all for Innovation, SDG, Open
University and Skill University. Every function says how many institutions it used.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy import stats

from core.data import (BAND_ORDER, NirfInputError, category_years, check_category, check_year, filter_df,
                       load_master, short_name)
from core.result import ChartResult
from core.stats import describe
from core.theme import (BLUES, CATEGORICAL, CROSS_CATEGORY_NOTE, INK, INK_SECONDARY, finish, ordinal_blues)


def _scored(category: str | None, year: int | None) -> tuple[pd.DataFrame, str, int]:
    """Rows with a published overall score for one category-year (defaults: Overall, latest year)."""
    df = load_master()
    category = check_category(category, df)
    year = check_year(category_years(category, df)[-1] if year is None else year, category, df)
    rows = filter_df(df, categories=category, years=year)
    scored = rows[rows["score"].notna()].copy()
    if scored.empty:
        raise NirfInputError(f"NIRF published no overall scores for {category} {year} (only ranks), so there is "
                             f"no score distribution to show.")
    return scored, category, year


def score_distribution(year: int | None = None, category: str = "Overall") -> ChartResult:
    """Answers questions like: "What is the distribution of NIRF scores for 2025?" (Q3.1)

    Definition: the overall scores of all institutions with a published score in that category-year.
    Method: histogram (bars = how many institutions fall in each equal-width score interval) with a
    density curve on top: a kernel density estimate (KDE), i.e. a smooth version of the histogram
    made by placing a small bell curve on every score and adding them up (bell width by Scott's
    rule), scaled to the same "institutions per interval" units as the bars. Vertical lines mark the
    mean (sum / count) and the median (middle value). If the mean is clearly above the median, a few
    very high scores pull it up: the distribution is right-skewed.
    """
    scored, category, year = _scored(category, year)
    s = describe(scored["score"])
    width = 2.5 if s["n"] >= 50 else 5.0
    start = np.floor(s["min"] / width) * width

    fig = go.Figure(go.Histogram(
        x=scored["score"], xbins=dict(start=start, end=s["max"] + width, size=width), marker_color=CATEGORICAL[0],
        opacity=0.75, name="Institutions per interval",
        hovertemplate="Score %{x}<br>%{y} institutions<extra></extra>"))
    if s["n"] >= 3 and s["std"] > 0:
        kde = stats.gaussian_kde(scored["score"].astype(float))           # bandwidth: Scott's rule
        bw = float(np.sqrt(kde.covariance[0, 0]))                         # width (SD) of each bell curve
        grid = np.linspace(s["min"] - 3 * bw, s["max"] + 3 * bw, 300)     # 3 bell widths: curve fades to ~0
        fig.add_trace(go.Scatter(
            x=grid, y=kde(grid) * s["n"] * width, mode="lines", name="Density curve (KDE)",
            line=dict(color=INK_SECONDARY, width=2.5),
            hovertemplate="Score %{x:.1f}<br>Smoothed: %{y:.1f} institutions per interval<extra></extra>"))
    for value, label, color, pos in ((s["mean"], "Mean", INK, "top right"),
                                     (s["median"], "Median", CATEGORICAL[1], "top left")):
        fig.add_vline(x=value, line=dict(color=color, width=2), annotation_text=f"{label} {value:.1f}",
                      annotation_position=pos, annotation_font=dict(color=color, size=12))
    fig.update_xaxes(title_text="Overall score (0-100)")
    fig.update_yaxes(title_text="Number of institutions")
    fig.update_layout(bargap=0.04, legend=dict(orientation="h", x=0, y=1.0, yanchor="bottom"))

    gap = s["mean"] - s["median"]
    shape = ("right-skewed: a few high scorers pull the mean above the median" if gap > 0.5 and s["skew"] > 0.3 else
             "left-skewed: a few low scorers pull the mean below the median" if gap < -0.5 and s["skew"] < -0.3 else
             "roughly symmetric: mean and median are close")
    title = f"{category} {year}: most scores lie between {s['q1']:.0f} and {s['q3']:.0f}; the distribution is {shape.split(':')[0]}"
    insight = (f"In {category} {year}, the {s['n']} published scores run from {s['min']:.1f} to {s['max']:.1f}; the mean "
               f"is {s['mean']:.1f} and the median {s['median']:.1f}, so the distribution is {shape} "
               f"(skewness {s['skew']:.2f}).")
    finish(fig, title, f"{category} ranking {year} · {s['n']} institutions with a published score · "
           f"bars {width:g} points wide · curve = smoothed shape (KDE)", legend_title="")
    method = (f"We take every {category} institution with a published overall score in {year} ({s['n']}) and count "
              f"how many fall into each {width:g}-point score interval (histogram). The grey curve is a kernel "
              f"density estimate (KDE): a small bell curve is placed on every institution's score and they are added "
              f"up, giving a smooth outline of the histogram that does not depend on where the bar edges fall (bell "
              f"width chosen by Scott's rule; the curve is multiplied by {s['n']} × {width:g} so it is in the same "
              f"'institutions per interval' units as the bars). Because each bell has a width, the curve runs a "
              f"little beyond the lowest and highest score; it shows shape, not extra institutions. The black line is the mean (sum of scores / count), "
              f"the orange line the median (the middle score after sorting). Skewness measures lopsidedness: "
              f"positive = a long tail of high scores. NIRF publishes scores only for exact ranks, so band-only "
              f"institutions are not included.")
    table = (scored[["canonical_name", "state", "rank_raw", "score"]].sort_values("score", ascending=False)
             .rename(columns={"canonical_name": "institution", "rank_raw": "rank"}).reset_index(drop=True))
    return ChartResult(fig, table, insight, method, "histogram with density curve")


def rank_distribution(year: int | None = None, category: str = "Overall") -> ChartResult:
    """Answers questions like: "What is the distribution of overall ranks across all institutions?" (Q3.2)

    Definition: number of ranked institutions in each rank band (1-10, 11-25, 26-50, 51-100,
    101-150, 151-200, 201-300), split into those with an exact rank and those NIRF lists only by band.
    Method: count rows per band. Bands have different widths, so the hover also shows institutions
    per 10 rank positions.
    """
    df = load_master()
    category = check_category(category, df)
    year = check_year(category_years(category, df)[-1] if year is None else year, category, df)
    rows = filter_df(df, categories=category, years=year)
    ranked = rows[rows["rank_band"].notna()]
    order = [b for b in BAND_ORDER if b in set(ranked["rank_band"])]
    ranked = ranked.assign(kind=np.where(ranked["rank"].notna(), "Exact rank published", "Only rank band published"))
    counts = ranked.groupby(["rank_band", "kind"]).size().unstack(fill_value=0).reindex(order, fill_value=0)
    for k in ("Exact rank published", "Only rank band published"):
        if k not in counts:
            counts[k] = 0
    lo = counts.index.str.extract(r"^(\d+)")[0].astype(int).values
    hi = counts.index.str.extract(r"-(\d+)$")[0].astype(int).values
    width = hi - lo + 1
    total = counts.sum(axis=1)

    fig = go.Figure()
    for k, color in (("Exact rank published", CATEGORICAL[0]), ("Only rank band published", BLUES[3])):
        if counts[k].sum():
            fig.add_trace(go.Bar(
                x=counts.index, y=counts[k], name=k, marker_color=color,
                customdata=np.stack([total, width, (10 * total / width).round(1)], axis=1),
                hovertemplate=("<b>Ranks %{x}</b><br>" + k + ": %{y}<br>All in band: %{customdata[0]} "
                               "(band covers %{customdata[1]} positions, %{customdata[2]} per 10 positions)<extra></extra>")))
    fig.add_trace(go.Scatter(x=counts.index, y=total, mode="text", text=total, textposition="top center",
                             textfont=dict(color=INK_SECONDARY, size=11), showlegend=False, hoverinfo="skip"))
    fig.update_layout(barmode="stack", legend=dict(orientation="h", x=0, y=1.0, yanchor="bottom"))
    fig.update_xaxes(title_text="Rank band (1 = best)", type="category")
    fig.update_yaxes(title_text="Number of institutions", range=[0, total.max() * 1.15])

    n_exact, n_band = int(counts["Exact rank published"].sum()), int(counts["Only rank band published"].sum())
    ties = int(rows["is_tie"].sum())
    max_exact = rows["rank"].max()
    title = f"{category} {year}: {len(ranked)} institutions ranked, {n_exact} with an exact rank"
    insight = (f"In {category} {year}, NIRF ranked {len(ranked)} institutions: {n_exact} with an exact rank "
               f"(1-{max_exact})" + (f" and {n_band} only within bands (" + ", ".join(
                   f"{b}: {int(counts.at[b, 'Only rank band published'])}" for b in order
                   if counts.at[b, "Only rank band published"]) + ")" if n_band else "") +
               (f"; {ties} institutions share a rank with another (ties)." if ties else "."))
    finish(fig, title, f"{category} ranking {year} · institutions per rank band",
           note="Bands have different widths (1-10 covers 10 positions, 51-100 covers 50).")
    method = (f"Every institution in the {category} {year} list is placed in a standard rank band using its exact "
              f"rank, or the band NIRF published for it. We count institutions per band and colour the part with "
              f"an exact rank differently from the part NIRF published only as a band. Because NIRF numbers ranks "
              f"1, 2, 3 ... and gives each place to one institution (except ties), the count per band mostly "
              f"reflects the band's width and the length of the list; the hover gives institutions per 10 positions.")
    table = counts.assign(total=total, band_width=width).reset_index().rename(columns={"rank_band": "rank_band"})
    table.columns.name = None
    return ChartResult(fig, table, insight, method, "stacked bar chart")


def summary_stats(year: int | None = None, category: str = "Overall") -> ChartResult:
    """Answers questions like: "What is the average, median, minimum and maximum score in 2025?" (Q3.3)

    Definition: standard summary statistics of the published overall scores in one category-year.
    Method: mean = sum / count; median = middle value; min / max = lowest / highest; range = max - min;
    standard deviation = typical distance from the mean; Q1 / Q3 = 25th / 75th percentiles;
    IQR = Q3 - Q1; coefficient of variation = SD / mean. Shown as a table and a box plot with every
    institution as a dot.
    """
    scored, category, year = _scored(category, year)
    s = describe(scored["score"])
    lo = scored.loc[scored["score"].idxmin()]
    hi = scored.loc[scored["score"].idxmax()]
    table = pd.DataFrame([
        ("Institutions with a score", s["n"], ""),
        ("Mean", s["mean"], "sum of scores / count"),
        ("Median", s["median"], "middle score after sorting"),
        ("Minimum", s["min"], lo["canonical_name"]),
        ("Maximum", s["max"], hi["canonical_name"]),
        ("Range", s["range"], "maximum - minimum"),
        ("Standard deviation", s["std"], "typical distance from the mean"),
        ("Q1 (25th percentile)", s["q1"], "a quarter of scores are below this"),
        ("Q3 (75th percentile)", s["q3"], "a quarter of scores are above this"),
        ("IQR (Q3 - Q1)", s["iqr"], "spread of the middle 50%"),
        ("Coefficient of variation", s["std"] / s["mean"], "SD / mean"),
    ], columns=["statistic", "value", "note"])
    table["value"] = table["value"].astype(float).round(3)

    fig = go.Figure(go.Box(
        x=scored["score"], name=f"{category} {year}", orientation="h", boxpoints="all", jitter=0.5, pointpos=-1.8,
        boxmean="sd", marker_color=CATEGORICAL[0], line_color=CATEGORICAL[0],
        customdata=np.stack([scored["canonical_name"], scored["rank_raw"]], axis=1),
        hovertemplate="<b>%{customdata[0]}</b><br>Rank %{customdata[1]} · score %{x:.2f}<extra></extra>"))
    fig.update_xaxes(title_text="Overall score (0-100)", showgrid=True)
    fig.update_yaxes(showgrid=False, showticklabels=False)
    fig.update_layout(showlegend=False)

    title = f"{category} {year}: mean score {s['mean']:.1f}, median {s['median']:.1f}, range {s['min']:.1f}-{s['max']:.1f}"
    insight = (f"In {category} {year}, the {s['n']} published scores have a mean of {s['mean']:.1f} and a median of "
               f"{s['median']:.1f}; the lowest is {s['min']:.1f} ({short_name(lo['canonical_name'])}) and the highest "
               f"{s['max']:.1f} ({short_name(hi['canonical_name'])}), with a standard deviation of {s['std']:.1f}.")
    finish(fig, title, "Box = middle 50% (Q1 to Q3), line inside = median, dashed diamond = mean ± 1 SD, "
           "dots = institutions", height=400)
    method = (f"Calculated on the {s['n']} institutions with a published {category} score in {year}. Mean = sum / "
              f"count; median = the middle value after sorting; min and max = lowest and highest; standard "
              f"deviation (sample, divide by n−1) = typical distance from the mean; Q1 and Q3 = the scores below "
              f"which 25% and 75% of institutions lie; IQR = Q3 − Q1. The box plot shows the same numbers: "
              f"the box spans Q1-Q3, the line inside is the median, the diamond marks the mean ± 1 SD.")
    return ChartResult(fig, table, insight, method, "box-and-whisker plot")


def quartile_shares(year: int | None = None, category: str = "Overall", mode: str = "score_range") -> ChartResult:
    """Answers questions like: "What percentage of ranked institutions fall into each score quartile?" (Q3.4)

    Two definitions of "quartile":
      mode="score_range": fixed quarters of the 0-100 score scale (0-25, 25-50, 50-75, 75-100).
        The shares tell where institutions sit on the absolute scale and can be anything.
      mode="statistical": the data's own quartiles Q1, Q2 (median), Q3. Each group holds about 25%
        of institutions BY DEFINITION, so the informative part is the cut-point scores.
    Method: assign every scored institution to a group, share = group count / all x 100 (100% bar).
    """
    scored, category, year = _scored(category, year)
    mode = str(mode).lower()
    s = describe(scored["score"])
    if mode == "score_range":
        edges = [0, 25, 50, 75, 100.0001]
        names = ["0-25", "25-50", "50-75", "75-100"]
        group = pd.cut(scored["score"], bins=edges, labels=names, right=False)
        bounds = [(0, 25), (25, 50), (50, 75), (75, 100)]
    elif mode == "statistical":
        names = [f"Bottom 25% (≤ {s['q1']:.1f})", f"Q1-median ({s['q1']:.1f}-{s['median']:.1f})",
                 f"Median-Q3 ({s['median']:.1f}-{s['q3']:.1f})", f"Top 25% (> {s['q3']:.1f})"]
        group = pd.cut(scored["score"], bins=[-np.inf, s["q1"], s["median"], s["q3"], np.inf], labels=names)
        bounds = [(s["min"], s["q1"]), (s["q1"], s["median"]), (s["median"], s["q3"]), (s["q3"], s["max"])]
    else:
        raise NirfInputError("mode must be 'score_range' (0-25, 25-50, 50-75, 75-100) or 'statistical' (Q1/Q2/Q3).")
    counts = group.value_counts().reindex(names, fill_value=0)
    shares = 100 * counts / counts.sum()
    table = pd.DataFrame({"group": names, "score_from": [round(b[0], 2) for b in bounds],
                          "score_to": [round(b[1], 2) for b in bounds], "institutions": counts.values,
                          "share_pct": shares.round(1).values})

    colors = ordinal_blues(4)
    fig = go.Figure()
    for name, c, n, p in zip(names, colors, counts.values, shares.values):
        fig.add_trace(go.Bar(
            x=[p], y=[f"{category} {year}"], name=name, orientation="h", marker=dict(color=c, line=dict(width=2, color="#fcfcfb")),
            text=[f"{p:.0f}%" if p >= 6 else ""], textposition="inside", insidetextanchor="middle",
            textfont=dict(color="white" if colors.index(c) >= 2 else INK, size=13),
            hovertemplate=f"<b>{name}</b><br>{n} institutions ({p:.1f}%)<extra></extra>"))
    fig.update_layout(barmode="stack", barcornerradius=0, legend=dict(orientation="h", x=0, y=1.02, yanchor="bottom"),
                      margin=dict(t=130))
    fig.update_xaxes(title_text="Share of scored institutions (%)", range=[0, 100], ticksuffix="%", showgrid=True)
    fig.update_yaxes(showgrid=False, showticklabels=False)

    if mode == "score_range":
        main = shares.idxmax()
        title = f"{shares.max():.0f}% of {category} {year} institutions score {main}"
        insight = (f"On the fixed 0-100 scale, {category} {year} scores fall " + ", ".join(
            f"{p:.0f}% in {n}" for n, p in shares.items()) + f" (n = {s['n']}); most institutions sit in the "
                   f"{main} quarter of the scale.")
    else:
        title = f"{category} {year} quartile cut points: Q1 {s['q1']:.1f}, median {s['median']:.1f}, Q3 {s['q3']:.1f}"
        insight = (f"Statistical quartiles split the {s['n']} {category} {year} institutions into four groups of about "
                   f"25% each by construction ({', '.join(f'{p:.0f}%' for p in shares)}); what they tell us are the "
                   f"cut points: a quarter score below {s['q1']:.1f}, half below {s['median']:.1f}, and the top "
                   f"quarter above {s['q3']:.1f}.")
    finish(fig, title, f"{'Fixed score ranges 0-25 / 25-50 / 50-75 / 75-100' if mode == 'score_range' else 'Statistical quartiles of this year’s scores'}"
           f" · {s['n']} institutions", height=360, legend_title="Score group")
    method = ("Two meanings of 'quartile'. Score-range quartiles cut the 0-100 scale into four fixed quarters "
              "(0-25, 25-50, 50-75, 75-100) and count institutions in each, so the shares show where institutions "
              "sit on the absolute scale and can be very uneven (NIRF scores rarely fall below 25). Statistical "
              "quartiles are the 25th, 50th and 75th percentiles of this year's scores (Q1, median, Q3): they cut "
              "the institutions into four groups of about 25% each by definition (ties can shift this slightly), "
              f"so the useful information is the cut-point scores. This chart uses the "
              f"{'score-range' if mode == 'score_range' else 'statistical'} definition; share = group count / "
              f"{s['n']} × 100.")
    return ChartResult(fig, table, insight, method, "stacked bar chart")


def spread_by_category(year: int | None = None) -> ChartResult:
    """Answers questions like: "How does the spread of scores differ across NIRF categories?" (Q3.5)

    Definition: spread = interquartile range (IQR = Q3 - Q1) and standard deviation of the overall
    scores of each category in one year.
    Method: one box plot per category (box = middle 50%, whiskers to the furthest points within
    1.5 x IQR, dots beyond = outliers), sorted by median. Scores of different categories use
    different weights, so this compares spreads, not quality across categories.
    """
    df = load_master()
    year = int(df["year"].max() if year is None else year)
    if year not in set(df["year"]):
        raise NirfInputError(f"No NIRF data for {year}. Years available: 2017-2025.")
    rows = filter_df(df, years=year)
    scored = rows[rows["score"].notna()]
    no_scores = sorted(set(rows["category_std"]) - set(scored["category_std"]))
    g = scored.groupby("category_std")["score"]
    table = pd.DataFrame({"n": g.size(), "mean": g.mean(), "median": g.median(), "std": g.std(),
                          "q1": g.quantile(0.25), "q3": g.quantile(0.75), "min": g.min(), "max": g.max()})
    table["iqr"] = table["q3"] - table["q1"]
    table["cv"] = table["std"] / table["mean"]
    table = table.sort_values("median", ascending=False).round(2)
    table.index.name = "category"

    fig = go.Figure()
    for c in table.index[::-1]:          # highest median drawn at the top
        t = scored[scored["category_std"].eq(c)]
        fig.add_trace(go.Box(
            x=t["score"], name=c, orientation="h", marker_color=CATEGORICAL[0], line_color=CATEGORICAL[0],
            boxpoints="outliers", customdata=np.stack([t["canonical_name"], t["rank_raw"]], axis=1),
            hovertemplate="<b>%{customdata[0]}</b><br>Rank %{customdata[1]} · score %{x:.2f}<extra>" + c + "</extra>"))
    fig.update_layout(showlegend=False)
    fig.update_xaxes(title_text="Overall score (0-100, within each category)", showgrid=True)
    fig.update_yaxes(title_text=None, showgrid=False)

    wide, narrow = table["iqr"].idxmax(), table["iqr"].idxmin()
    title = f"In {year}, {wide} scores are the most spread out (IQR {table.at[wide, 'iqr']:.1f})"
    insight = (f"In {year}, {wide} has the widest spread of scores (IQR {table.at[wide, 'iqr']:.1f}, SD "
               f"{table.at[wide, 'std']:.1f}) and {narrow} the narrowest (IQR {table.at[narrow, 'iqr']:.1f}); "
               f"{table.index[0]} has the highest median ({table['median'].iloc[0]:.1f}).")
    if no_scores:
        insight += f" No scores are published for {', '.join(no_scores)}."
    finish(fig, title, f"{year} · one box per category, sorted by median · box = middle 50%, dots = outliers (1.5 × IQR rule)",
           note=CROSS_CATEGORY_NOTE, height=max(420, 170 + 34 * len(table)))
    method = (f"For each category ranked in {year} we take the published overall scores and draw a box plot: the box "
              f"runs from Q1 to Q3 (the middle half), the line inside is the median, whiskers reach the furthest "
              f"scores within 1.5 × IQR of the box, and dots beyond are outliers. Spread is measured by the IQR "
              f"(Q3 − Q1) and the standard deviation. Each category has its own parameter weights, so we compare "
              f"how spread out scores are, not which category is 'better'. Categories without published scores: "
              f"{', '.join(no_scores) if no_scores else 'none'}.")
    return ChartResult(fig, table.reset_index(), insight, method, "box-and-whisker plot")
