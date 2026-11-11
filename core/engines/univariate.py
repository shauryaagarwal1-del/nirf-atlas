"""Univariate engine: one variable at a time (Annexure A section 3, Q3.1-Q3.5).

Functions
  score_distribution()  shape of the overall scores in one year (histogram with density curve (KDE),
                        mean and median lines)
  rank_distribution()   how many institutions sit in each rank band (stacked bar chart, exact vs band-only)
  summary_stats()       mean, median, min, max, SD, quartiles of the scores (table + box-and-whisker plot)
  quartile_shares()     % of institutions in each score quartile, two definitions (100% stacked bar chart)
  spread_by_category()  score spread of every category in one year (box-and-whisker plot per category)
  coverage_by_category_year()  how many institutions each category lists per year (matrix heatmap)

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
from core.theme import (AXIS, CATEGORICAL, CROSS_CATEGORY_NOTE, INK, INK_SECONDARY, MARIGOLD_INK, OTHER, RAMP,
                        SURFACE, finish, ordinal_ramp, tint)


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
        opacity=0.75, name="Institutions in each score range",
        hovertemplate="Score %{x}<br>%{y} institutions<extra></extra>"))
    if s["n"] >= 3 and s["std"] > 0:
        kde = stats.gaussian_kde(scored["score"].astype(float))           # bandwidth: Scott's rule
        bw = float(np.sqrt(kde.covariance[0, 0]))                         # width (SD) of each bell curve
        grid = np.linspace(s["min"] - 3 * bw, s["max"] + 3 * bw, 300)     # 3 bell widths: curve fades to ~0
        fig.add_trace(go.Scatter(
            x=grid, y=kde(grid) * s["n"] * width, mode="lines", name="Smoothed shape (KDE)",
            line=dict(color=INK_SECONDARY, width=2.5),
            hovertemplate="Score %{x:.1f}<br>Smoothed: %{y:.1f} institutions per interval<extra></extra>"))
    for value, label, color, ink, pos, shift in ((s["mean"], "Average (mean)", INK, INK, "top right", -2),
                                                 (s["median"], "Middle value (median)", CATEGORICAL[1], MARIGOLD_INK,
                                                  "top left", -22)):
        fig.add_vline(x=value, line=dict(color=color, width=2), annotation_text=f"{label} {value:.1f}",
                      annotation_position=pos, annotation_font=dict(color=ink, size=12), annotation_yshift=shift)
    fig.update_xaxes(title_text="Overall score (0-100)")
    fig.update_yaxes(title_text="Number of institutions")
    fig.update_layout(bargap=0.04, legend=dict(orientation="h", x=0, y=1.0, yanchor="bottom"))

    gap = s["mean"] - s["median"]
    shape = ("right-skewed: a few high scorers pull the mean above the median" if gap > 0.5 and s["skew"] > 0.3 else
             "left-skewed: a few low scorers pull the mean below the median" if gap < -0.5 and s["skew"] < -0.3 else
             "roughly symmetric: mean and median are close")
    title = (f"Half of all {category} institutions score between {s['q1']:.1f} and {s['q3']:.1f} in {year}; "
             f"the shape is {shape.split(':')[0]}")
    insight = (f"In {category} {year}, the {s['n']} published scores run from {s['min']:.1f} to {s['max']:.1f}; the mean "
               f"is {s['mean']:.1f} and the median {s['median']:.1f}, so the distribution is {shape} "
               f"(skewness {s['skew']:.2f}).")
    finish(fig, title, f"Each bar = how many of the {s['n']} institutions score in that {width:g}-point range · "
                       f"taller = more institutions · the curve is the smoothed shape (KDE)", legend_title="Key")
    method = (f"We take every {category} institution with a published overall score in {year} ({s['n']}) and count "
              f"how many fall into each {width:g}-point score interval (histogram). The grey curve is a kernel "
              f"density estimate (KDE): a small bell curve is placed on every institution's score and they are added "
              f"up, giving a smooth outline of the histogram that does not depend on where the bar edges fall (bell "
              f"width chosen by Scott's rule; the curve is multiplied by {s['n']} × {width:g} so it is in the same "
              f"'institutions per interval' units as the bars). Because each bell has a width, the curve runs a "
              f"little beyond the lowest and highest score; it shows shape, not extra institutions. The black line is the mean (sum of scores / count), "
              f"the orange line the median (the middle score after sorting). The title's 'half of all institutions' "
              f"is the middle half: from Q1 (a quarter score below it) to Q3 (a quarter score above it), the IQR. "
              f"Skewness measures lopsidedness: "
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
    plain = {"Exact rank published": "Given an exact rank (e.g. 7th)",
             "Only rank band published": "Given only a band (e.g. 101-150)"}
    for k, color in (("Exact rank published", CATEGORICAL[0]), ("Only rank band published", RAMP[3])):
        if counts[k].sum():
            fig.add_trace(go.Bar(
                x=counts.index, y=counts[k], name=plain[k], marker_color=color,
                text=counts[k].where(counts[k] > 0, ""), textposition="inside", insidetextanchor="middle",
                textfont=dict(size=12),
                customdata=np.stack([total, width, (10 * total / width).round(1)], axis=1),
                hovertemplate=("<b>Ranks %{x}</b><br>" + k + ": %{y}<br>All in band: %{customdata[0]} "
                               "(band covers %{customdata[1]} positions, %{customdata[2]} per 10 positions)<extra></extra>")))
    fig.add_trace(go.Scatter(x=counts.index, y=total, mode="text", text=[f"{v} in all" for v in total],
                             textposition="top center", textfont=dict(color=INK, size=12), showlegend=False,
                             hoverinfo="skip"))
    fig.update_layout(barmode="stack", legend=dict(orientation="h", x=0, y=1.0, yanchor="bottom"))
    fig.update_xaxes(title_text="Rank band (1 = best)", type="category")
    fig.update_yaxes(title_text="Number of institutions", range=[0, total.max() * 1.15])

    n_exact, n_band = int(counts["Exact rank published"].sum()), int(counts["Only rank band published"].sum())
    ties = int(rows["is_tie"].sum())
    max_exact = rows["rank"].max()
    title = (f"{category} {year}: {len(ranked)} institutions ranked; {n_exact} got an exact rank"
             + (f", {n_band} only a band" if n_band else ""))
    insight = (f"In {category} {year}, NIRF ranked {len(ranked)} institutions: {n_exact} with an exact rank "
               f"(1-{max_exact})" + (f" and {n_band} only within bands (" + ", ".join(
                   f"{b}: {int(counts.at[b, 'Only rank band published'])}" for b in order
                   if counts.at[b, "Only rank band published"]) + ")" if n_band else "") +
               (f"; {ties} institutions share a rank with another (ties)." if ties else "."))
    finish(fig, title, f"Each bar is one rank band (1 = best, on the left) · taller = more institutions · "
                       f"the number on top = all institutions in that band",
           note="Bands have different widths (1-10 covers 10 positions, 51-100 covers 50).", legend_title="Key")
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
    # Plain-word labels on the picture itself: lowest, highest, middle value, average, typical range.
    if s["n"] > 1:
        for value, label, y, anchor in ((s["min"], f"lowest {s['min']:.1f}", 0.5, "left"),
                                        (s["max"], f"highest {s['max']:.1f}", 0.5, "right"),
                                        (s["median"], f"middle value (median) {s['median']:.1f}", 0.42, "center"),
                                        (s["mean"], f"average (mean) {s['mean']:.1f}", -0.72, "center")):
            fig.add_annotation(x=value, y=y, yref="y", text=label, showarrow=False, xanchor=anchor, yanchor="bottom",
                               font=dict(size=11, color=INK), bgcolor=tint(SURFACE, 0.8))
        fig.add_annotation(x=(s["q1"] + s["q3"]) / 2, y=0.26, yref="y", showarrow=False, xanchor="center",
                           text=f"typical range: middle half (IQR) {s['q1']:.1f} to {s['q3']:.1f}",
                           font=dict(size=11, color=INK_SECONDARY), bgcolor=tint(SURFACE, 0.8))
        fig.update_yaxes(range=[-0.85, 0.62])

    if s["n"] == 1:      # one institution (e.g. a state filter): its score is the mean, median, min and max
        title = f"{category} {year}: only one published score ({s['mean']:.1f}, {short_name(lo['canonical_name'])})"
        insight = (f"In {category} {year}, only one institution has a published score: {short_name(lo['canonical_name'])}"
                   f" with {s['mean']:.1f}, which is at once the mean, median, minimum and maximum; one value has "
                   f"no spread, so the standard deviation and IQR cannot be calculated.")
    else:
        title = (f"{category} {year}: average score {s['mean']:.1f}, middle value {s['median']:.1f}, "
                 f"lowest {s['min']:.1f}, highest {s['max']:.1f}")
        insight = (f"In {category} {year}, the {s['n']} published scores have a mean of {s['mean']:.1f} and a median "
                   f"of {s['median']:.1f}; the lowest is {s['min']:.1f} ({short_name(lo['canonical_name'])}) and the "
                   f"highest {s['max']:.1f} ({short_name(hi['canonical_name'])}), with a standard deviation of "
                   f"{s['std']:.1f}.")
    finish(fig, title, "Each dot is one institution · box = the middle half of institutions (IQR) · line in the "
                       "box = middle value (median) · dashed diamond = average (mean) ± 1 standard deviation",
           height=420)
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

    # The biggest group (the answer) in teal, the other groups in greys that get lighter away from it.
    biggest = int(shares.values.argmax())
    greys = [OTHER, "#c9cdda", "#dfe2ec", "#eceef4"]
    colors = [CATEGORICAL[0] if i == biggest else greys[min(abs(i - biggest), 3)] for i in range(4)]
    legend_names = [f"Scores {n}" for n in names] if mode == "score_range" else names
    fig = go.Figure()
    for name, c, n, p in zip(legend_names, colors, counts.values, shares.values):
        fig.add_trace(go.Bar(
            x=[p], y=[f"{category} {year}"], name=name, orientation="h", marker=dict(color=c, line=dict(width=2, color=SURFACE)),
            text=[f"{p:.0f}% ({n})" if p >= 9 else f"{p:.0f}%" if p >= 4 else ""], textposition="inside",
            insidetextanchor="middle", textfont=dict(size=14),
            hovertemplate=f"<b>{name}</b><br>{n} institutions ({p:.1f}%)<extra></extra>"))
    fig.update_layout(barmode="stack", barcornerradius=0, legend=dict(orientation="h", x=0, y=1.02, yanchor="bottom"),
                      margin=dict(t=130), bargap=0.15)
    fig.update_xaxes(title_text="Share of scored institutions (%)", range=[0, 100], ticksuffix="%", showgrid=True)
    fig.update_yaxes(showgrid=False, showticklabels=False)

    if mode == "score_range":
        main = shares.idxmax()
        title = f"{shares.max():.0f}% of {category} institutions score between {main.replace('-', ' and ')} in {year}"
        insight = (f"On the fixed 0-100 scale, {category} {year} scores fall " + ", ".join(
            f"{p:.0f}% in {n}" for n, p in shares.items()) + f" (n = {s['n']}); most institutions sit in the "
                   f"{main} quarter of the scale.")
    else:
        title = f"{category} {year} quartile cut points: Q1 {s['q1']:.1f}, median {s['median']:.1f}, Q3 {s['q3']:.1f}"
        insight = (f"Statistical quartiles split the {s['n']} {category} {year} institutions into four groups of about "
                   f"25% each by construction ({', '.join(f'{p:.0f}%' for p in shares)}); what they tell us are the "
                   f"cut points: a quarter score below {s['q1']:.1f}, half below {s['median']:.1f}, and the top "
                   f"quarter above {s['q3']:.1f}.")
    finish(fig, title, f"One bar = all {s['n']} institutions · each piece = the share scoring in that range "
                       f"({'fixed quarters of the 0-100 scale' if mode == 'score_range' else 'this year’s statistical quartiles'})"
                       f" · the biggest piece is in colour", height=400, legend_title="Score group")
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

    wide, narrow = table["iqr"].idxmax(), table["iqr"].idxmin()
    fig = go.Figure()
    for c in table.index[::-1]:          # highest median drawn at the top; the widest box (the answer) in colour
        t = scored[scored["category_std"].eq(c)]
        col = CATEGORICAL[0] if c == wide else OTHER
        fig.add_trace(go.Box(
            x=t["score"], name=c, orientation="h", marker_color=col, line_color=col,
            fillcolor=tint(col, 0.25 if c == wide else 0.12),
            boxpoints="outliers", customdata=np.stack([t["canonical_name"], t["rank_raw"]], axis=1),
            hovertemplate="<b>%{customdata[0]}</b><br>Rank %{customdata[1]} · score %{x:.2f}<extra>" + c + "</extra>"))
        fig.add_annotation(x=float(table.at[c, "max"]) + 1, y=c, text=f"middle half spans {table.at[c, 'iqr']:.1f} pts",
                           showarrow=False, xanchor="left", font=dict(size=11, color=INK if c == wide else INK_SECONDARY))
    fig.update_layout(showlegend=False)
    fig.update_xaxes(title_text="Overall score (0-100, within each category)", showgrid=True,
                     range=[float(table["min"].min()) - 2, float(table["max"].max()) + 22])
    fig.update_yaxes(title_text="Category", showgrid=False)

    title = (f"{wide} has the most spread-out scores in {year}: its middle half spans {table.at[wide, 'iqr']:.1f} "
             f"points (IQR)")
    insight = (f"In {year}, {wide} has the widest spread of scores (IQR {table.at[wide, 'iqr']:.1f}, SD "
               f"{table.at[wide, 'std']:.1f}) and {narrow} the narrowest (IQR {table.at[narrow, 'iqr']:.1f}); "
               f"{table.index[0]} has the highest median ({table['median'].iloc[0]:.1f}).")
    if no_scores:
        insight += f" No scores are published for {', '.join(no_scores)}."
    finish(fig, title, f"One box per category ({year}) · the box is the middle half of its scores (IQR): a wider box = "
                       f"more spread out · line in the box = middle value (median) · dots = far-out scores · the "
                       f"answer is in colour", note=CROSS_CATEGORY_NOTE, height=max(420, 170 + 34 * len(table)))
    method = (f"For each category ranked in {year} we take the published overall scores and draw a box plot: the box "
              f"runs from Q1 to Q3 (the middle half), the line inside is the median, whiskers reach the furthest "
              f"scores within 1.5 × IQR of the box, and dots beyond are outliers. Spread is measured by the IQR "
              f"(Q3 − Q1) and the standard deviation. Each category has its own parameter weights, so we compare "
              f"how spread out scores are, not which category is 'better'. Categories without published scores: "
              f"{', '.join(no_scores) if no_scores else 'none'}.")
    return ChartResult(fig, table.reset_index(), insight, method, "box-and-whisker plot")


def coverage_by_category_year() -> ChartResult:
    """Answers questions like: "Which ranking categories did NIRF publish in which years, and how big is each list?"

    Definition: the number of institutions NIRF listed in each category-year (exact ranks and
    band-only ranks both count; a blank cell = NIRF published no ranking for that category that year).
    Method: count the rows of the master table per category and year and draw the counts as a
    category x year grid; darker = a longer list. Categories are ordered by their first year.
    """
    df = load_master()
    years = sorted(df["year"].unique().tolist())
    g = df.groupby(["category_std", "year"]).agg(listed=("institution_key", "size"),
                                                  exact=("rank", lambda s: int(s.notna().sum())),
                                                  scored=("score", lambda s: int(s.notna().sum())))
    first = df.groupby("category_std")["year"].min()
    order = sorted(first.index, key=lambda c: (first[c], -int(g.loc[c, "listed"].max()), c))
    z, text, hover = [], [], []
    for c in order:
        zr, tr, hr = [], [], []
        for y in years:
            if (c, y) in g.index:
                r = g.loc[(c, y)]
                zr.append(int(r["listed"]))
                tr.append(str(int(r["listed"])))
                hr.append(f"{int(r['listed'])} listed · {int(r['exact'])} with an exact rank · "
                          f"{int(r['scored'])} with a score")
            else:
                zr.append(None)
                tr.append("")
                hr.append("no ranking published")
        z.append(zr)
        text.append(tr)
        hover.append(hr)
    fig = go.Figure(go.Heatmap(
        z=z, x=[str(y) for y in years], y=order, text=text, texttemplate="%{text}", customdata=hover,
        colorscale=[[i / (len(RAMP) - 1), c] for i, c in enumerate(RAMP)], textfont=dict(size=11),
        colorbar=dict(title=dict(text="Institutions listed")),
        hovertemplate="<b>%{y}</b> %{x}<br>%{customdata}<extra></extra>"))
    fig.update_yaxes(autorange="reversed", showgrid=False, showline=False, ticks="", title_text="Category")
    fig.update_xaxes(showgrid=False, showline=False, ticks="", side="top", title_text="Year", type="category")
    n_pairs = len(g)
    newest = [c for c in order if first[c] == first.max()]
    biggest = g["listed"].idxmax()
    title = f"NIRF grew from {int(first.eq(min(years)).sum())} ranking lists in {min(years)} to " \
            f"{int((g.reset_index()['year'] == max(years)).sum())} in {max(years)}"
    insight = (f"The master table holds {n_pairs} category-year lists across {len(order)} categories; the longest "
               f"is {biggest[0]} {biggest[1]} ({int(g.loc[biggest, 'listed'])} institutions) and the newest "
               f"category is {', '.join(newest)} (first published in {first.max()}).")
    method = ("We count the rows of the cleaned master table for every category and year (every listed institution, "
              "whether NIRF gave an exact rank or only a band). Blank cells are years in which NIRF did not publish "
              "that category, which is why categories are compared only in the years they share.")
    finish(fig, title, "Institutions listed per category and year · blank = category not published that year",
           height=max(420, 180 + 30 * len(order)), legend_title="Institutions listed")
    fig.update_layout(margin=dict(t=130, l=200))
    table = g.reset_index().rename(columns={"category_std": "category", "listed": "institutions_listed",
                                            "exact": "with_exact_rank", "scored": "with_score"})
    return ChartResult(fig, table, insight, method, "matrix heatmap")
