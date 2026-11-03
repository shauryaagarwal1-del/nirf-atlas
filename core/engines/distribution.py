"""Distribution engine: how scores are spread and how groups compare (Annexure A section 6, Q6.1-Q6.5).

Functions
  top10_vs_rest()          scores of the top 10 vs everyone else (violin plot with a box inside, or
                           view="histogram": overlapping histogram)
  dispersion_by_year()     how spread out the scores are in each year (box-and-whisker plot per year, or
                           view="sd": line chart of the standard deviation)
  parameter_variability()  which parameter varies most across institutions (ranked bar chart of the
                           coefficient of variation, or view="box": box-and-whisker plot per parameter)
  median_iqr_over_time()   median and IQR per year (point plot with error bars: point = median, bar = Q1 to Q3)
  score_by_state()         score distribution of each state (box-and-whisker plot per state, sorted by median)

Every chart type is one of the types listed in docs/allowed_charts.md.

Scores exist only for institutions with an exact rank (NIRF does not publish scores for band-only
positions), so every function says how many institutions it used.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from core.data import (LABELS, SHORT, NirfInputError, category_year, category_years, check_category, filter_df,
                       fmt_years, load_master, parameters_of)
from core.engines import trends
from core.result import ChartResult
from core.stats import describe, signed
from core.theme import CATEGORICAL, INK_SECONDARY, finish


def _scored(category: str, year) -> tuple[pd.DataFrame, str, int]:
    rows, category, year = category_year(category, year)
    scored = rows[rows["score"].notna()].copy()
    if scored.empty:
        raise NirfInputError(f"NIRF published no overall scores for {category} {year} (only ranks), so there is "
                             f"no score distribution to show.")
    return scored, category, year


def _check_view(view: str, allowed: dict[str, str]) -> str:
    view = str(view).lower()
    if view not in allowed:
        raise NirfInputError("view must be " + " or ".join(f"'{k}' ({v})" for k, v in allowed.items()) + ".")
    return view


def top10_vs_rest(year: int | None = None, category: str = "Overall", top: int = 10,
                  view: str = "violin") -> ChartResult:
    """Answers questions like: "How does the score distribution differ between the top 10 and the remaining
    institutions?" (Q6.1)

    Definition: two groups of one category-year: exact rank <= top ("Top 10") and every other
    institution with a published score ("Rest").
    Method: view="violin" (default) draws one violin per group: its width shows how many
    institutions have each score (a mirrored smooth density curve), and the box inside marks the
    median and the middle 50% (Q1 to Q3); every institution is a dot. view="histogram" draws the
    two groups as overlapping, semi-transparent histograms on the same score bins. The table gives
    n, mean, median, SD, IQR, min and max per group.
    """
    view = _check_view(view, {"violin": "violin plot with a box inside", "histogram": "overlapping histogram"})
    scored, category, year = _scored(category, year)
    top = int(top)
    scored["group"] = np.where(scored["rank"].le(top).fillna(False).astype(bool), f"Top {top}", "Rest")
    names = [f"Top {top}", "Rest"]
    counts = scored["group"].value_counts()
    if counts.get(names[0], 0) < 2 or counts.get("Rest", 0) < 2:
        raise NirfInputError(f"{category} {year} has too few scored institutions to split into the top {top} and the rest.")
    last = int(scored["rank"].max())
    rest_label = f"Rest (ranks {top + 1}-{last})"
    colors = {names[0]: CATEGORICAL[0], "Rest": CATEGORICAL[1]}

    stats_rows = {g: describe(scored.loc[scored["group"].eq(g), "score"]) for g in names}
    table = pd.DataFrame(stats_rows).T[["n", "mean", "median", "std", "q1", "q3", "iqr", "min", "max"]]
    table.index = [names[0], rest_label]
    table = table.astype(float).round(2).rename_axis("group").reset_index()
    table["n"] = table["n"].astype(int)

    fig = go.Figure()
    for g in names:
        t = scored[scored["group"].eq(g)]
        label = rest_label if g == "Rest" else g
        common = dict(name=label, marker_color=colors[g],
                      customdata=np.stack([t["canonical_name"], t["rank_raw"]], axis=1),
                      hovertemplate="<b>%{customdata[0]}</b><br>Rank %{customdata[1]} · score %{y:.2f}<extra></extra>")
        if view == "violin":
            fig.add_trace(go.Violin(
                y=t["score"], x=[label] * len(t), line_color=colors[g], fillcolor=colors[g], opacity=0.55,
                box=dict(visible=True, fillcolor="rgba(255,255,255,0.55)", line=dict(color=INK_SECONDARY, width=1.5),
                         width=0.16),
                meanline=dict(visible=False), points="all", pointpos=0, jitter=0.5,
                marker=dict(size=5, opacity=0.75, color=INK_SECONDARY), spanmode="hard", scalemode="width", **common))
        else:
            common["hovertemplate"] = f"<b>{label}</b><br>Score %{{x}}<br>%{{y}} institutions<extra></extra>"
            common.pop("customdata")
            fig.add_trace(go.Histogram(
                x=t["score"], xbins=dict(start=np.floor(scored["score"].min() / 2.5) * 2.5,
                                         end=scored["score"].max() + 2.5, size=2.5),
                opacity=0.6, **common))
    if view == "violin":
        fig.update_yaxes(title_text="Overall score (0-100)")
        fig.update_xaxes(title_text="Group")
        fig.update_layout(showlegend=False, violingap=0.35)
    else:
        fig.update_xaxes(title_text="Overall score (0-100)")
        fig.update_yaxes(title_text="Number of institutions")
        fig.update_layout(barmode="overlay", bargap=0.04, legend=dict(orientation="h", x=0, y=1.0, yanchor="bottom"))

    a, b = stats_rows[names[0]], stats_rows["Rest"]
    gap = a["min"] - b["max"]
    title = (f"The top {top}'s median score ({a['median']:.1f}) is {a['median'] - b['median']:.0f} points above the "
             f"rest ({b['median']:.1f}) in {category} {year}")
    insight = (f"In {category} {year}, the top {top} have a median score of {a['median']:.1f} (IQR {a['iqr']:.1f}) "
               f"against {b['median']:.1f} (IQR {b['iqr']:.1f}) for the other {b['n']} scored institutions. "
               + (f"Every top-{top} score is above every other score (gap {gap:.1f} points between the lowest top-{top} "
                  f"score and the highest of the rest). " if gap > 0 else "")
               + (f"The rest are {'more' if b['std'] > a['std'] else 'less'} spread out (SD {b['std']:.1f} vs "
                  f"{a['std']:.1f}).")
               + (" The rest are right-skewed: many institutions sit just above the cut-off and few higher up."
                  if b["skew"] > 0.5 else ""))
    finish(fig, title, f"{category} ranking {year} · {a['n'] + b['n']} institutions with a published score · "
           + ("violin = smoothed distribution, box = median and middle 50%, dots = institutions" if view == "violin"
              else "bars 2.5 points wide, overlapping"), legend_title="" if view == "histogram" else None)
    method = (f"We split the {a['n'] + b['n']} {category} institutions with a published score in {year} into the top "
              f"{top} (exact rank ≤ {top}) and the rest, and compare their score distributions. "
              + ("A violin plot is a box plot with the distribution's shape around it: the outline is a smoothed "
                 "density (KDE) mirrored on both sides, so a wide part means many institutions have that score; the "
                 "white box inside runs from Q1 to Q3 with a line at the median. "
                 if view == "violin" else
                 "The two histograms share the same 2.5-point bins and are drawn half-transparent on top of each other, "
                 "so their positions and shapes can be compared directly. ")
              + "The table gives each group's n, mean, median, SD, Q1, Q3, IQR, min and max. The groups are very "
              f"different in size ({a['n']} vs {b['n']}), so we compare shapes and medians, not counts.")
    return ChartResult(fig, table, insight, method, "violin plot" if view == "violin" else "overlapping histogram")


def dispersion_by_year(category: str = "Overall", top_n: int | None = None, view: str = "box") -> ChartResult:
    """Answers questions like: "Are NIRF scores more dispersed in one year than another?" (Q6.2)

    Definition: dispersion = how spread out the scores of one category-year are, measured by the
    standard deviation (SD, typical distance from the mean) and the interquartile range (IQR =
    Q3 - Q1, the width of the middle 50%).
    Method: view="box" (default): one box-and-whisker plot per year (box = Q1 to Q3, line =
    median, whiskers to the furthest score within 1.5 x IQR, dots beyond = outliers); a taller box
    = more dispersed. view="sd": line chart with markers of the SD per year. top_n (e.g. 100) keeps
    only exact ranks 1..top_n so every year compares the same number of places.
    """
    view = _check_view(view, {"box": "box-and-whisker plot per year", "sd": "line chart of the standard deviation"})
    df = load_master()
    category = check_category(category, df)
    years = category_years(category, df)
    scored = filter_df(df, categories=category)
    scored = scored[scored["score"].notna()]
    if top_n is not None:
        scored = scored[scored["rank"].le(int(top_n)).fillna(False).astype(bool)]
    if scored.empty:
        raise NirfInputError(f"NIRF publishes no overall scores for {category}.")
    years = [y for y in years if y in set(scored["year"])]
    table = pd.DataFrame({y: describe(scored.loc[scored["year"].eq(y), "score"]) for y in years}).T
    table["cv"] = table["std"] / table["mean"]
    table = (table[["n", "mean", "median", "std", "q1", "q3", "iqr", "min", "max", "range", "cv"]].astype(float)
             .round(3).rename_axis("year").reset_index())
    table["n"] = table["n"].astype(int)

    fig = go.Figure()
    if view == "box":
        for y in years:
            t = scored[scored["year"].eq(y)]
            fig.add_trace(go.Box(
                y=t["score"], x=[str(y)] * len(t), name=str(y), marker_color=CATEGORICAL[0], line_color=CATEGORICAL[0],
                boxpoints="outliers", customdata=np.stack([t["canonical_name"], t["rank_raw"]], axis=1),
                hovertemplate="<b>%{customdata[0]}</b><br>Rank %{customdata[1]} · score %{y:.2f}<extra>" + str(y)
                              + "</extra>"))
        fig.update_layout(showlegend=False)
        fig.update_yaxes(title_text="Overall score (0-100)")
    else:
        fig.add_trace(go.Scatter(
            x=table["year"], y=table["std"], mode="lines+markers", name="Standard deviation",
            marker_color=CATEGORICAL[0], line_color=CATEGORICAL[0],
            customdata=np.stack([table["iqr"], table["n"], table["mean"]], axis=1),
            hovertemplate=("<b>%{x}</b><br>SD %{y:.2f} around a mean of %{customdata[2]:.1f}<br>IQR %{customdata[0]:.2f}"
                           "<br>%{customdata[1]} institutions<extra></extra>")))
        fig.update_yaxes(title_text="Standard deviation of the overall score (points)", rangemode="tozero")
        fig.update_layout(showlegend=False)
    fig.update_xaxes(title_text="Year", type="category" if view == "box" else "linear", dtick=1)

    hi = table.loc[table["std"].idxmax()]
    lo = table.loc[table["std"].idxmin()]
    first, last = table.iloc[0], table.iloc[-1]
    trend = ("more" if last["std"] > first["std"] + 0.5 else "less" if last["std"] < first["std"] - 0.5
             else "about as")
    title = (f"{category} scores were most dispersed in {int(hi.year)} (SD {hi['std']:.1f}) and least in "
             f"{int(lo.year)} (SD {lo['std']:.1f})")
    insight = (f"{category} scores were most spread out in {int(hi.year)} (SD {hi['std']:.1f}, IQR {hi['iqr']:.1f}) and "
               f"least in {int(lo.year)} (SD {lo['std']:.1f}, IQR {lo['iqr']:.1f}); in {int(last.year)} they were "
               f"{trend} dispersed {'than' if trend != 'about as' else 'as'} in {int(first.year)} (SD {first['std']:.1f} → "
               f"{last['std']:.1f}).")
    ns = table.groupby("n")["year"].apply(fmt_years)
    if top_n is None and table["n"].max() > 1.1 * table["n"].min():
        insight += (" Careful: the number of scored institutions changes (" + "; ".join(f"{n} in {y}" for n, y in ns.items())
                    + "); set top_n=100 for a like-for-like comparison.")
    finish(fig, title, f"{category} ranking, {fmt_years(years)}"
           + (f" · exact ranks 1-{top_n} only" if top_n else "")
           + (" · box = middle 50%, line = median, dots = outliers (1.5 × IQR rule)" if view == "box"
              else " · standard deviation per year"))
    method = (f"For every year we take the {category} institutions with a published overall score"
              f"{f' and an exact rank of {top_n} or better' if top_n else ''} and measure the spread: standard "
              f"deviation (SD: the typical distance of a score from the mean, sample formula with n − 1) and IQR "
              f"(Q3 − Q1: the width of the middle half, not affected by a few extreme scores). "
              + ("Each year gets a box plot, so taller boxes and longer whiskers = more dispersed. "
                 if view == "box" else "The line joins the yearly SDs; IQR is in the hover. ")
              + "The table also has the coefficient of variation (SD / mean), which allows for a changing average.")
    return ChartResult(fig, table, insight, method, "box-and-whisker plot" if view == "box" else "line chart")


def parameter_variability(year: int | None = None, category: str = "Overall", view: str = "bar") -> ChartResult:
    """Answers questions like: "Which NIRF parameter exhibits the greatest variability across institutions?" (Q6.3)

    Definition: variability = coefficient of variation (CV = SD / mean): the spread relative to the
    parameter's own average. CV lets parameters with very different typical levels be compared
    fairly (PR usually sits far lower than GO). SD and IQR are also reported.
    Method: view="bar" (default): ranked bar chart of the CV per parameter, most variable first.
    view="box": one box-and-whisker plot per parameter (same order), showing the full spread.
    """
    view = _check_view(view, {"bar": "ranked bar chart of the CV", "box": "box-and-whisker plot per parameter"})
    rows, category, year = category_year(category, year)
    params = parameters_of(rows)
    if not params:
        raise NirfInputError(f"NIRF published no parameter scores for {category} {year}.")
    stats_ = {SHORT[p]: describe(rows[p]) for p in params}
    table = pd.DataFrame(stats_).T
    table["cv"] = table["std"] / table["mean"]
    table = (table[["n", "mean", "median", "std", "q1", "q3", "iqr", "min", "max", "cv"]].astype(float)
             .sort_values("cv", ascending=False).round(3).rename_axis("parameter").reset_index())
    table["n"] = table["n"].astype(int)
    long_names = {SHORT[p]: LABELS[p] for p in params}
    col_of = {SHORT[p]: p for p in params}

    fig = go.Figure()
    if view == "bar":
        t = table.iloc[::-1]
        fig.add_trace(go.Bar(
            x=t["cv"], y=t["parameter"], orientation="h", marker_color=CATEGORICAL[0], text=t["cv"].map("{:.2f}".format),
            textposition="outside", cliponaxis=False,
            customdata=np.stack([t["parameter"].map(long_names), t["std"], t["mean"], t["iqr"]], axis=1),
            hovertemplate=("<b>%{customdata[0]}</b><br>CV %{x:.2f} = SD %{customdata[1]:.1f} / mean "
                           "%{customdata[2]:.1f}<br>IQR %{customdata[3]:.1f}<extra></extra>"), showlegend=False))
        fig.update_xaxes(title_text="Coefficient of variation (SD / mean)", showgrid=True,
                         range=[0, table["cv"].max() * 1.15])
        fig.update_yaxes(title_text=None, showgrid=False)
    else:
        for name in table["parameter"]:
            v = rows[[col_of[name], "canonical_name", "rank_raw"]].dropna(subset=[col_of[name]])
            fig.add_trace(go.Box(
                y=v[col_of[name]], x=[name] * len(v), name=name, marker_color=CATEGORICAL[0],
                line_color=CATEGORICAL[0], boxpoints="outliers",
                customdata=np.stack([v["canonical_name"], v["rank_raw"]], axis=1),
                hovertemplate="<b>%{customdata[0]}</b><br>Rank %{customdata[1]}<br>" + name
                              + " %{y:.2f}<extra></extra>"))
        fig.update_layout(showlegend=False)
        fig.update_yaxes(title_text="Parameter score (0-100)")
        fig.update_xaxes(title_text="Parameter (most variable first, by CV)")

    hi, lo = table.iloc[0], table.iloc[-1]
    by_sd = table.sort_values("std", ascending=False).iloc[0]
    title = f"{hi['parameter']} varies the most across {category} institutions in {year} (CV {hi['cv']:.2f})"
    insight = (f"In {category} {year}, {long_names[hi['parameter']]} is the most variable parameter (CV {hi['cv']:.2f}: "
               f"SD {hi['std']:.1f} around a mean of {hi['mean']:.1f}) and {lo['parameter']} the least (CV {lo['cv']:.2f}: "
               f"SD {lo['std']:.1f} around {lo['mean']:.1f}).")
    if by_sd["parameter"] != hi["parameter"]:
        insight += (f" Measured by SD alone, {by_sd['parameter']} would come first ({by_sd['std']:.1f}), because it "
                    f"sits at a higher level.")
    finish(fig, title, f"{category} ranking {year} · {int(table['n'].max())} institutions · "
           + ("CV = SD / mean, so parameters with different averages can be compared" if view == "bar"
              else "box = middle 50%, dots = outliers (1.5 × IQR rule), sorted by CV"))
    method = (f"For each parameter of the {category} institutions of {year} we compute the mean, the standard deviation "
              f"(SD) and the coefficient of variation CV = SD / mean. CV measures spread relative to the average, so "
              f"a parameter that usually scores 25 and one that usually scores 70 can be compared fairly; IQR (Q3 − Q1) "
              f"is in the table as a robust check. "
              + ("Bars are sorted from the most to the least variable." if view == "bar"
                 else "One box per parameter, in the same order as the CV ranking."))
    return ChartResult(fig, table, insight, method, "bar chart" if view == "bar" else "box-and-whisker plot")


def median_iqr_over_time(category: str = "Overall", top_n: int | None = None) -> ChartResult:
    """Answers questions like: "How do the median and interquartile range of scores change over time?" (Q6.4)

    Definition: per year, the median score (middle value) and the IQR (Q3 - Q1, the range of the
    middle 50% of institutions).
    Method: point plot with error bars: the point is the median, the error bar runs from Q1 to Q3,
    one per year (drawn by trends.average_score_over_time with stat="median", show_spread=True).
    The insight compares the first and last year and names the years with the widest and
    narrowest IQR. top_n (e.g. 100) keeps only exact ranks 1..top_n.
    """
    r = trends.average_score_over_time(category, stat="median", top_n=top_n, show_spread=True)
    t = r.table.sort_values("year")
    a, z = t.iloc[0], t.iloc[-1]
    wide, narrow = t.loc[t["iqr"].idxmax()], t.loc[t["iqr"].idxmin()]
    cat = t["category"].iloc[0]
    title = (f"{cat}: median score {a['median']:.1f} → {z['median']:.1f} and IQR {a['iqr']:.1f} → {z['iqr']:.1f} "
             f"({int(a.year)}→{int(z.year)})")
    insight = (f"The median {cat} score went from {a['median']:.1f} in {int(a.year)} to {z['median']:.1f} in "
               f"{int(z.year)} ({signed(z['median'] - a['median'], 1)} points), and the IQR from {a['iqr']:.1f} to "
               f"{z['iqr']:.1f}: the middle half of institutions "
               + ("stayed about as spread out" if abs(z["iqr"] - a["iqr"]) < 0.5 else
                  f"became {'more' if z['iqr'] > a['iqr'] else 'less'} spread out")
               + f". The IQR was widest in {int(wide.year)} "
               f"({wide['iqr']:.1f}) and narrowest in {int(narrow.year)} ({narrow['iqr']:.1f}).")
    caveat = r.insight.split(" Careful:")
    if len(caveat) > 1:
        insight += " Careful:" + caveat[1]
    r.fig.update_layout(title_text=title)
    method = r.method + " The IQR (Q3 − Q1) is the length of each error bar."
    return ChartResult(r.fig, t.reset_index(drop=True), insight, method, r.chart_type)


def score_by_state(year: int | None = None, category: str = "Overall", min_institutions: int = 3) -> ChartResult:
    """Answers questions like: "How does the score distribution differ across states?" (Q6.5)

    Definition: the published overall scores of each state's institutions in one category-year.
    Only states with at least min_institutions scored institutions get a box (a box of one or two
    points says nothing about spread); the others are listed in the note.
    Method: one horizontal box-and-whisker plot per state, sorted by median (highest at the top),
    every institution drawn as a dot. The table gives n, median, IQR, mean, min and max per state.
    """
    scored, category, year = _scored(category, year)
    min_institutions = int(min_institutions)
    if min_institutions < 1:
        raise NirfInputError("min_institutions must be at least 1.")
    g = scored.groupby("state")["score"]
    table = pd.DataFrame({"n": g.size(), "median": g.median(), "q1": g.quantile(0.25), "q3": g.quantile(0.75),
                          "mean": g.mean(), "min": g.min(), "max": g.max()})
    table["iqr"] = table["q3"] - table["q1"]
    table = table.round(2).sort_values(["median", "n"], ascending=[False, False]).rename_axis("state").reset_index()
    shown = table[table["n"] >= min_institutions]
    small = table[table["n"] < min_institutions]
    if shown.empty:
        raise NirfInputError(f"No state has {min_institutions} or more scored {category} institutions in {year}.")

    fig = go.Figure()
    for _, s in shown.iloc[::-1].iterrows():
        t = scored[scored["state"].eq(s["state"])]
        label = f"{s['state']} ({int(s['n'])})"
        fig.add_trace(go.Box(
            x=t["score"], y=[label] * len(t), name=label, orientation="h", marker_color=CATEGORICAL[0],
            line_color=CATEGORICAL[0], boxpoints="all", jitter=0.4, pointpos=0, fillcolor="rgba(42,120,214,0.12)",
            marker=dict(size=6, opacity=0.75), customdata=np.stack([t["canonical_name"], t["rank_raw"]], axis=1),
            hovertemplate="<b>%{customdata[0]}</b><br>Rank %{customdata[1]} · score %{x:.2f}<extra>" + s["state"]
                          + "</extra>"))
    fig.update_layout(showlegend=False)
    fig.update_xaxes(title_text="Overall score (0-100)", showgrid=True)
    fig.update_yaxes(title_text=None, showgrid=False)

    best = shown.iloc[0]
    widest = shown.loc[shown["iqr"].idxmax()]
    title = (f"{best['state']} has the highest median {category} score in {year} ({best['median']:.1f}) among states "
             f"with {min_institutions}+ institutions")
    insight = (f"In {category} {year}, among the {len(shown)} states with at least {min_institutions} scored "
               f"institutions, {best['state']} has the highest median score ({best['median']:.1f}, n = {int(best['n'])}) "
               f"and {shown.iloc[-1]['state']} the lowest ({shown.iloc[-1]['median']:.1f}); {widest['state']} is the most "
               f"spread out (IQR {widest['iqr']:.1f}).")
    if len(small):
        insight += f" {len(small)} more states have fewer than {min_institutions} institutions and are only in the table."
    note = (f"Not drawn (fewer than {min_institutions} institutions): "
            + ", ".join(f"{s} ({n})" for s, n in zip(small["state"], small["n"])) if len(small) else None)
    if note and len(note) > 160:
        note = note[:157].rsplit(",", 1)[0] + ", …"
    finish(fig, title, f"{category} ranking {year} · one box per state, sorted by median · number in brackets = "
           f"institutions · dots = institutions", note=note, height=max(420, 170 + 34 * len(shown)))
    method = (f"We take the {len(scored)} {category} institutions with a published overall score in {year}, group them by "
              f"state and draw one box plot per state with at least {min_institutions} institutions (box = Q1 to Q3, "
              f"line = median, whiskers = furthest scores within 1.5 × IQR, every institution as a dot). States are "
              f"sorted by median because the median is not pulled by one very high or low scorer. Small states are "
              f"kept in the table but not drawn: a box of one or two values cannot show a spread.")
    return ChartResult(fig, table, insight, method, "box-and-whisker plot")
