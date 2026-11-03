"""Trends engine: how ranks and scores change over the years (Annexure A section 1, Q1.1-Q1.5).

Functions
  rank_trajectory()         rank of chosen institutions year by year (multi-series line chart, rank 1 on top)
  biggest_movers()          largest climbs / falls between two years (ranked horizontal bar chart)
  average_score_over_time() mean or median score per year (multi-series line chart with markers, or with
                            show_spread=True a point plot with error bars from Q1 to Q3)
  consistent_top_n()        who stayed in the top N in many years (matrix heatmap institution x year)
  top_n_race()              how this year's top N got there (multi-series line chart, top 3 highlighted)
  parameter_trends()        one institution's parameter scores and overall score year by year (multi-series
                            line chart)

Every chart type is one of the types listed in docs/allowed_charts.md.

Conventions: a smaller rank is better; improvement = old_rank - new_rank (positive = moved up).
Calculations that need a rank as a number use exact ranks only (NIRF publishes some positions only
as bands such as 101-150; those are shown as bands, never turned into invented numbers).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from core.data import (LABELS, SHORT, NirfInputError, category_years, chart_labels, check_category, check_year,
                       check_years, filter_df, find_institutions, fmt_years, load_master, parameters_of)
from core.result import ChartResult
from core.stats import places, signed
from core.theme import (CATEGORICAL, CONTEXT, CROSS_CATEGORY_NOTE, DOWN, INK, INK_SECONDARY, OTHER, SURFACE, UP,
                        color_map, finish)

MAX_LINES = 8


def _where_ranked(df: pd.DataFrame, key: str) -> str:
    rows = df[df["institution_key"].eq(key)]
    if rows.empty:
        return "it is not in any NIRF ranking list"
    parts = [f"{c} ({fmt_years(g['year'])})" for c, g in rows.groupby("category_std")]
    return "it is ranked in " + "; ".join(parts)


def rank_trajectory(institutions=None, category: str = "Overall", years=None) -> ChartResult:
    """Answers questions like: "How has the NIRF rank of IIT Madras changed from 2017 to 2025?" (Q1.1)

    Definition: the rank NIRF published for each institution in the chosen category, year by year.
    Method: one line per institution through its exact ranks. A year where NIRF published only a
    band (e.g. 101-150) is drawn as a faint vertical bar covering that band, not as a point, and a
    year where the institution is not ranked is left as a gap. The y-axis is reversed so rank 1 is
    at the top ("up = better"). Default institutions: the top 5 of the latest year.
    """
    df = load_master()
    category = check_category(category, df)
    years = check_years(years, category, df)
    cat = filter_df(df, years=years, categories=category)

    if institutions is None or (not isinstance(institutions, str) and len(list(institutions)) == 0):
        last = cat[cat["year"].eq(max(years)) & cat["rank"].notna()].sort_values(["rank", "canonical_name"])
        keys = last["institution_key"].head(5).tolist()
        chosen = f"the top 5 of {max(years)}"
    else:
        keys = find_institutions(institutions)
        chosen = None
    if len(keys) > MAX_LINES:
        raise NirfInputError(f"Please choose at most {MAX_LINES} institutions so every line keeps its own colour "
                             f"(you chose {len(keys)}).")
    labels = chart_labels(keys)
    present = set(cat["institution_key"])
    for k in keys:
        if k not in present:
            raise NirfInputError(f"{labels[k]} is not ranked in {category} in {fmt_years(years)}; "
                                 f"{_where_ranked(df, k)}.")

    grid = pd.MultiIndex.from_product([keys, years], names=["institution_key", "year"]).to_frame(index=False)
    cols = ["institution_key", "year", "canonical_name", "rank_raw", "rank", "rank_status", "rank_band_nirf",
            "rank_band", "score"]
    table = grid.merge(cat[cols].drop(columns="canonical_name"), on=["institution_key", "year"], how="left")
    table.insert(1, "institution", table["institution_key"].map(labels))
    table["rank_status"] = table["rank_status"].fillna("not ranked")

    colors = color_map([labels[k] for k in keys])
    fig = go.Figure()
    band_seen = False
    for k in keys:
        t = table[table["institution_key"].eq(k)]
        name, c = labels[k], colors[labels[k]]
        hover = [
            f"rank {r.rank_raw}" + (f" · score {r.score:.2f}" if pd.notna(r.score) else "")
            if pd.notna(r.rank) else
            (f"only band {r.rank_band_nirf} published" if r.rank_status == "band" else f"not ranked in {category}")
            for r in t.itertuples()
        ]
        fig.add_trace(go.Scatter(
            x=t["year"], y=t["rank"].astype("float"), name=name, mode="lines+markers", connectgaps=False,
            line=dict(color=c), marker=dict(color=c), legendgroup=name, customdata=hover,
            hovertemplate=f"<b>{name}</b><br>%{{x}}: %{{customdata}}<extra></extra>"))
        b = t[t["rank_status"].eq("band")]
        if len(b):
            lo = b["rank_band_nirf"].str.extract(r"^(\d+)")[0].astype(float)
            hi = b["rank_band_nirf"].str.extract(r"-(\d+)$")[0].astype(float)
            xs, ys, txt = [], [], []
            for yr, a, z, band in zip(b["year"], lo, hi, b["rank_band_nirf"]):
                xs += [yr, yr, None]
                ys += [a, z, None]
                txt += [band, band, None]
            fig.add_trace(go.Scatter(
                x=xs, y=ys, mode="lines", line=dict(color=c, width=7), opacity=0.35, legendgroup=name,
                showlegend=False, customdata=txt,
                hovertemplate=f"<b>{name}</b><br>%{{x}}: only band %{{customdata}} published<extra></extra>"))
            band_seen = True

    # Insight: change between each institution's first and last exact rank in the window.
    moves = []
    for k in keys:
        t = table[table["institution_key"].eq(k) & table["rank"].notna()].sort_values("year")
        if len(t):
            first, last = t.iloc[0], t.iloc[-1]
            moves.append(dict(name=labels[k], y0=int(first.year), r0=int(first["rank"]), y1=int(last.year),
                              r1=int(last["rank"]), change=int(first["rank"]) - int(last["rank"]),
                              best=int(t["rank"].min()), best_year=int(t.loc[t["rank"].idxmin(), "year"]),
                              n=int(len(t))))
    span = f"{min(years)}–{max(years)}" if len(years) > 1 else str(years[0])
    if len(keys) == 1:
        if moves:
            m = moves[0]
            title = f"{m['name']}: rank {m['r0']} in {m['y0']} → rank {m['r1']} in {m['y1']} ({category})"
            insight = (f"{m['name']} went from rank {m['r0']} in {m['y0']} to rank {m['r1']} in {m['y1']} in "
                       f"{category} ({places(m['change'])}); its best rank was {m['best']} "
                       f"(first reached in {m['best_year']}) and it had an exact rank in {m['n']} of {len(years)} years.")
        else:
            title = f"{labels[keys[0]]} appears in {category} only as a rank band"
            insight = (f"{labels[keys[0]]} never has an exact {category} rank in {span}; NIRF published only its "
                       f"rank band ({', '.join(table['rank_band_nirf'].dropna().unique())}).")
    else:
        up = max(moves, key=lambda m: m["change"]) if moves else None
        down = min(moves, key=lambda m: m["change"]) if moves else None
        if up and up["change"] > 0:
            title = f"{up['name']} climbed the most of these {len(keys)} in {category} ({places(up['change'])})"
            insight = (f"Of these {len(keys)} institutions, {up['name']} improved the most "
                       f"(rank {up['r0']} in {up['y0']} → {up['r1']} in {up['y1']}, {places(up['change'])})")
        else:
            title = f"None of these {len(keys)} institutions improved its {category} rank over {span}"
            insight = f"None of these {len(keys)} institutions ended the period with a better {category} rank than it started"
        if down and down["change"] < 0:
            insight += (f", while {down['name']} fell the most ({down['r0']} → {down['r1']}, "
                        f"{places(down['change'])}).")
        else:
            insight += ", and none of them fell."

    # Reversed rank axis (1 at the top) with a little padding so the best/worst markers are not cut off.
    bands = table["rank_band_nirf"].dropna().str.extract(r"^(\d+)-(\d+)$").astype(float)
    lo = np.nanmin([table["rank"].astype(float).min(), bands[0].min() if len(bands) else np.nan])
    hi = np.nanmax([table["rank"].astype(float).max(), bands[1].max() if len(bands) else np.nan])
    pad = max(0.5, 0.06 * (hi - lo))
    fig.update_yaxes(title_text="Rank (1 = best, shown at the top)", range=[hi + pad, max(lo - pad, 0.4)],
                     tickformat="d", dtick=1 if hi - lo <= 12 else None)
    fig.update_xaxes(title_text="Year", dtick=1, range=[min(years) - 0.4, max(years) + 0.4])
    fig.update_layout(hovermode="x unified" if len(keys) <= 3 else "closest")
    subtitle = f"{category} ranking, {span}" + (f" · {chosen}" if chosen else "")
    note = "Faint bars = years where NIRF published only a rank band; gaps = not ranked that year." if band_seen \
        else "Gaps = not ranked in this category that year."
    finish(fig, title, subtitle, note=note, legend_title="Institution")

    method = (f"For each chosen institution we take the rank NIRF published in {category} for every year in "
              f"{span}. Exact ranks are joined by a line; a year with only a published band (e.g. 101-150) is shown "
              f"as a bar covering the band (we never invent a number inside it); a year without a rank is a gap. "
              f"The change in the insight is first exact rank minus last exact rank (positive = moved up). "
              f"The y-axis is reversed so that rank 1 is at the top.")
    return ChartResult(fig, table.drop(columns="institution_key").reset_index(drop=True), insight, method,
                       "line chart" if len(keys) == 1 else "multi-series line chart")


def parameter_trends(institution: str = "IIT Madras", category: str = "Overall", years=None) -> ChartResult:
    """Answers questions like: "How have IIT Madras's five parameter scores changed over the years?"

    Definition: the score NIRF published for each parameter (TLR, RPC, GO, OI, PR; Research
    Institutions: QnR, QlR, SFC, OI, PR) and the overall score of ONE institution, year by year.
    Method: one line per parameter through the published values (a year without a score is a gap);
    the overall score is the dashed dark line. Change = last published value - first published value.
    All values are out of 100 and come from the same category, so they share one axis.
    """
    df = load_master()
    category = check_category(category, df)
    years = check_years(years, category, df)
    key = find_institutions(institution)[0]
    label = chart_labels([key])[key]
    rows = filter_df(df, years=years, categories=category)
    rows = rows[rows["institution_key"].eq(key)].sort_values("year")
    if rows.empty:
        raise NirfInputError(f"{label} is not ranked in {category} in {fmt_years(years)}; {_where_ranked(df, key)}.")
    params = parameters_of(rows)
    if not params:
        raise NirfInputError(f"NIRF published no parameter scores for {label} in {category} ({fmt_years(years)}).")
    cols = ["score"] + params
    table = rows[["year", "rank_raw"] + cols].rename(columns={"rank_raw": "rank"}).reset_index(drop=True)

    fig = go.Figure()
    colors = dict(zip(params, CATEGORICAL))
    for p in params:
        fig.add_trace(go.Scatter(
            x=table["year"], y=table[p], name=SHORT[p], mode="lines+markers", connectgaps=False,
            line=dict(color=colors[p]), marker=dict(color=colors[p]),
            hovertemplate=f"<b>{LABELS[p]}</b><br>%{{x}}: %{{y:.1f}}<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=table["year"], y=table["score"], name="Overall score", mode="lines+markers", connectgaps=False,
        line=dict(color=INK, width=2.5, dash="dash"), marker=dict(color=INK, symbol="diamond", size=9),
        customdata=table["rank"],
        hovertemplate="<b>Overall score</b><br>%{x}: %{y:.1f} (rank %{customdata})<extra></extra>"))
    fig.update_yaxes(title_text="Score (out of 100)", range=[0, 102])
    fig.update_xaxes(title_text="Year", dtick=1)
    fig.update_layout(hovermode="x unified")

    change = {}
    for c in cols:
        s = table.set_index("year")[c].dropna()
        if len(s) > 1:
            change[c] = (s.iloc[-1] - s.iloc[0], int(s.index[0]), int(s.index[-1]), s.iloc[0], s.iloc[-1])
    span = fmt_years(table["year"].tolist())
    if change and any(c in change for c in params):
        moved = {c: v for c, v in change.items() if c != "score"}
        up = max(moved, key=lambda c: moved[c][0])
        down = min(moved, key=lambda c: moved[c][0])
        g, y0, y1, a, z = moved[up]
        title = f"{label} in {category}: {SHORT[up]} gained the most ({signed(g, 1)} points, {y0}→{y1})"
        insight = (f"From {y0} to {y1}, {label}'s {SHORT[up]} went from {a:.1f} to {z:.1f} ({signed(g, 1)}), the "
                   f"largest gain among its parameters")
        if moved[down][0] < 0:
            d0 = moved[down]
            insight += f"; {SHORT[down]} fell the most, from {d0[3]:.1f} to {d0[4]:.1f} ({signed(d0[0], 1)})"
        if "score" in change:
            s0 = change["score"]
            insight += f". Its overall score went from {s0[3]:.1f} to {s0[4]:.1f} ({signed(s0[0], 1)})."
        else:
            insight += "."
    else:
        title = f"{label}'s parameter scores in {category} {span}"
        insight = f"{label} has parameter scores for only one year in {category} ({span}), so there is no change to show."
    finish(fig, title, f"{category} ranking, {span} · one line per parameter, dashed = overall score",
           note="Gaps = no published score that year (not ranked, or ranked only in a band).",
           legend_title="Parameter")
    method = (f"We take {label}'s rows in the {category} ranking for {span} and draw the published score of each "
              f"parameter ({', '.join(SHORT[p] for p in params)}) and the overall score, one line each, joined in "
              f"time order. Every value is out of 100. The overall score is a weighted sum of the parameters, with "
              f"{category}'s own weights, so a parameter with a large weight moves it more. Change = last published "
              f"value - first published value; years without a score are gaps, never filled in.")
    return ChartResult(fig, table, insight, method, "multi-series line chart")


def biggest_movers(category: str = "Overall", start_year: int | None = None, end_year: int | None = None,
                   direction: str = "up", n: int = 10) -> ChartResult:
    """Answers questions like: "Which institutions improved / declined the most in rank from 2017 to 2025?"
    (Q1.2, Q1.3, Q7.4)

    Definition: improvement = rank in start_year - rank in end_year (positive = moved up).
    Method: keep institutions with an exact rank in BOTH years (a band like 101-150 is not a number,
    so it cannot be subtracted), compute the improvement, sort, and keep the n largest climbs
    (direction="up"), falls ("down") or n of each ("both"). Defaults: first and last year of the category.
    """
    df = load_master()
    category = check_category(category, df)
    available = category_years(category, df)
    start_year = check_year(available[0] if start_year is None else start_year, category, df)
    end_year = check_year(available[-1] if end_year is None else end_year, category, df)
    if start_year >= end_year:
        raise NirfInputError(f"The start year ({start_year}) must be before the end year ({end_year}).")
    direction = str(direction).lower()
    if direction not in {"up", "down", "both"}:
        raise NirfInputError("direction must be 'up' (biggest climbs), 'down' (biggest falls) or 'both'.")
    n = int(n)
    if n < 1:
        raise NirfInputError("n must be at least 1.")

    cat = filter_df(df, categories=category, years=[start_year, end_year])
    exact = cat[cat["rank"].notna()]
    a = exact[exact["year"].eq(start_year)][["institution_key", "canonical_name", "state", "rank", "score"]]
    b = exact[exact["year"].eq(end_year)][["institution_key", "rank", "score"]]
    both = a.merge(b, on="institution_key", suffixes=("_start", "_end"))
    if both.empty:
        raise NirfInputError(f"No institution has an exact {category} rank in both {start_year} and {end_year}.")
    both["improvement"] = (both["rank_start"] - both["rank_end"]).astype(int)
    in_both_any = len(set(cat.loc[cat["year"].eq(start_year), "institution_key"])
                      & set(cat.loc[cat["year"].eq(end_year), "institution_key"]))

    ups = both[both["improvement"] > 0].sort_values(["improvement", "rank_end"], ascending=[False, True]).head(n)
    downs = both[both["improvement"] < 0].sort_values(["improvement", "rank_end"], ascending=[True, True]).head(n)
    pick = {"up": ups, "down": downs, "both": pd.concat([ups, downs])}[direction]
    if pick.empty:
        word = "improved" if direction == "up" else "declined"
        raise NirfInputError(f"No institution {word} its exact {category} rank between {start_year} and {end_year}.")
    # Plotly draws the first row at the bottom, so sort to put the biggest climb (or fall) at the top.
    pick = pick.sort_values("improvement", ascending=direction != "down")
    labels = chart_labels(pick["institution_key"])
    pick.insert(0, "institution", pick["institution_key"].map(labels))

    colors = [UP if v > 0 else DOWN for v in pick["improvement"]]
    fig = go.Figure(go.Bar(
        x=pick["improvement"], y=pick["institution"], orientation="h", marker_color=colors,
        text=[f"{int(s)} → {int(e)}" for s, e in zip(pick["rank_start"], pick["rank_end"])],
        textposition="outside", cliponaxis=False,
        customdata=np.stack([pick["canonical_name"], pick["state"], pick["rank_start"].astype(int),
                             pick["rank_end"].astype(int)], axis=1),
        hovertemplate=(f"<b>%{{customdata[0]}}</b> (%{{customdata[1]}})<br>{start_year}: rank %{{customdata[2]}}"
                       f"<br>{end_year}: rank %{{customdata[3]}}<br>Improvement: %{{x:+d}} places<extra></extra>"),
        showlegend=False))
    # Legend entries for the two colours (bars themselves carry no legend).
    for name, c, show in (("Moved up", UP, (pick["improvement"] > 0).any()),
                          ("Moved down", DOWN, (pick["improvement"] < 0).any())):
        if show:
            fig.add_trace(go.Bar(x=[None], y=[None], name=name, marker_color=c, orientation="h"))
    lo, hi = min(0, pick["improvement"].min()), max(0, pick["improvement"].max())
    pad = 0.18 * (hi - lo)   # room for the "old -> new" labels outside the bar ends
    fig.update_xaxes(title_text=f"Improvement in places ({start_year} rank − {end_year} rank)",
                     range=[lo - (pad if lo < 0 else 0), hi + (pad if hi > 0 else 0)], zeroline=True, zerolinecolor=INK_SECONDARY, zerolinewidth=1, showgrid=True)
    fig.update_yaxes(title_text=None, showgrid=False)
    fig.update_layout(barmode="overlay", legend=dict(orientation="h", x=0, y=1.0, yanchor="bottom"))

    top_up, top_down = (ups.iloc[0] if len(ups) else None), (downs.iloc[0] if len(downs) else None)
    n_up, n_down = int((both["improvement"] > 0).sum()), int((both["improvement"] < 0).sum())
    lead = top_up if direction in {"up", "both"} and top_up is not None else top_down
    verb = "climbed" if lead["improvement"] > 0 else "fell"
    title = (f"{labels[lead['institution_key']]} {verb} the most in {category}, {start_year}→{end_year} "
             f"({places(lead['improvement'])})")
    insight = (f"Between {start_year} and {end_year}, {lead['canonical_name']} {verb} the most in {category}: "
               f"from rank {int(lead['rank_start'])} to {int(lead['rank_end'])} ({places(lead['improvement'])}). "
               f"Of the {len(both)} institutions with an exact rank in both years, {n_up} moved up, {n_down} moved "
               f"down and {len(both) - n_up - n_down} kept the same rank.")
    excluded = in_both_any - len(both)
    method = (f"Improvement = rank in {start_year} − rank in {end_year}, so a positive number means the "
              f"institution moved up. Only institutions with an exact rank in both years can be compared "
              f"({len(both)} institutions); {excluded} more appear in both years but only inside a rank band in at "
              f"least one of them, so they are left out (a band like 101-150 is not a number). We sort by "
              f"improvement and show the {n} largest {'climbs' if direction == 'up' else 'falls' if direction == 'down' else 'climbs and falls'}. "
              f"Note: the length of NIRF's exact-rank list can change between years (e.g. Engineering ranked "
              f"200 exactly in 2019-2022 but 100 otherwise), which limits how far an institution can move.")
    finish(fig, title, f"{category} ranking · labels show rank {start_year} → {end_year}",
           height=max(380, 150 + 30 * len(pick)), legend_title="")
    table = pick.drop(columns="institution_key").rename(columns={"canonical_name": "full_name"})
    return ChartResult(fig, table.iloc[::-1].reset_index(drop=True), insight, method, "bar chart")


def average_score_over_time(categories="Overall", stat: str = "mean", top_n: int | None = None,
                            show_spread: bool = False) -> ChartResult:
    """Answers questions like: "How has the average NIRF score changed over time?" (Q1.4, Q6.4)

    Definition: for each category and year, the mean (or median) of the overall scores NIRF
    published, and the interquartile range (IQR: from the 25th to the 75th percentile Q1-Q3, i.e.
    where the middle 50% of institutions lie).
    Method: one line with markers per category through the yearly mean or median (a multi-series
    line chart; Q1, Q3 and n are in the hover). show_spread=True draws a point plot with error bars
    instead: the point is the mean or median, the bar runs from Q1 to Q3. Only institutions with a
    published score are used (NIRF does not publish scores for band-only positions). top_n (e.g.
    100) keeps only exact ranks 1..top_n so that every year compares the same number of places.
    """
    df = load_master()
    cats = [check_category(c, df) for c in ([categories] if isinstance(categories, str) else list(categories))]
    if not cats:
        raise NirfInputError("Please choose at least one category.")
    if len(cats) > MAX_LINES:
        raise NirfInputError(f"Please choose at most {MAX_LINES} categories.")
    stat = str(stat).lower()
    if stat not in {"mean", "median"}:
        raise NirfInputError("stat must be 'mean' or 'median'.")
    scored = filter_df(df, categories=cats)
    scored = scored[scored["score"].notna()]
    if top_n is not None:
        scored = scored[scored["rank"].le(int(top_n)).fillna(False).astype(bool)]
    no_score = [c for c in cats if c not in set(scored["category_std"])]
    if no_score:
        raise NirfInputError(f"NIRF publishes no overall scores for {', '.join(no_score)}, so there is no "
                             f"average to show.")

    g = scored.groupby(["category_std", "year"])["score"]
    table = pd.DataFrame({
        "n": g.size(), "mean": g.mean(), "median": g.median(), "q1": g.quantile(0.25), "q3": g.quantile(0.75),
        "min": g.min(), "max": g.max(),
    }).reset_index().rename(columns={"category_std": "category"})
    table["iqr"] = table["q3"] - table["q1"]
    table[["mean", "median", "q1", "q3", "min", "max", "iqr"]] = table[["mean", "median", "q1", "q3", "min", "max",
                                                                        "iqr"]].round(2)

    colors = color_map(cats)
    fig = go.Figure()
    # Point plot: shift categories a little sideways so their error bars do not hide each other.
    dodge = 0.12 if len(cats) > 1 else 0.0
    for i, c in enumerate(cats):
        t = table[table["category"].eq(c)]
        col = colors[c]
        common = dict(
            name=c, marker=dict(color=col), customdata=np.stack([t["q1"], t["q3"], t["n"], t["mean"], t["median"],
                                                                 t["year"]], axis=1),
            hovertemplate=(f"<b>{c}</b> %{{customdata[5]}}<br>Mean %{{customdata[3]:.2f}} · median "
                           f"%{{customdata[4]:.2f}}<br>Middle 50% (Q1 to Q3): %{{customdata[0]:.2f}} to "
                           f"%{{customdata[1]:.2f}}<br>Institutions with a score: %{{customdata[2]}}<extra></extra>"))
        if show_spread:
            offset = (i - (len(cats) - 1) / 2) * dodge
            fig.add_trace(go.Scatter(
                x=t["year"] + offset, y=t[stat], mode="markers",
                error_y=dict(type="data", symmetric=False, array=(t["q3"] - t[stat]).clip(lower=0),
                             arrayminus=(t[stat] - t["q1"]).clip(lower=0), color=col, thickness=1.5, width=5),
                **common))
        else:
            fig.add_trace(go.Scatter(x=t["year"], y=t[stat], mode="lines+markers", line=dict(color=col), **common))

    first = cats[0]
    t = table[table["category"].eq(first)].sort_values("year")
    a, z = t.iloc[0], t.iloc[-1]
    change = z[stat] - a[stat]
    title = (f"The {stat} {first} score {'rose' if change > 0 else 'fell' if change < 0 else 'did not change'} "
             f"from {a[stat]:.1f} in {int(a.year)} to {z[stat]:.1f} in {int(z.year)}")
    insight = (f"The {stat} {first} score went from {a[stat]:.1f} in {int(a.year)} to {z[stat]:.1f} in "
               f"{int(z.year)} ({signed(change, 1)} points); the middle 50% of institutions scored between "
               f"{z.q1:.1f} and {z.q3:.1f} in {int(z.year)} (IQR {z.iqr:.1f}, was {a.iqr:.1f}).")
    if len(cats) > 1:
        rises = {c: (lambda s: s.iloc[-1] - s.iloc[0])(table[table["category"].eq(c)].sort_values("year")[stat])
                 for c in cats}
        best = max(rises, key=rises.get)
        insight += f" Of the {len(cats)} categories, {best} changed the most upward ({signed(rises[best], 1)} points)."
    # Flag categories whose list length really changes (e.g. 100 vs 200), not a one-off tie at 100/101.
    ns_by_cat = table.groupby("category")["n"]
    uneven = [c for c in cats if ns_by_cat.get_group(c).max() > 1.1 * ns_by_cat.get_group(c).min()]
    if uneven and top_n is None:
        ns = table[table["category"].eq(uneven[0])].groupby("n")["year"].apply(fmt_years)
        insight += (f" Careful: the number of scored institutions changes over the years in {', '.join(uneven)} "
                    f"(e.g. {uneven[0]}: " + "; ".join(f"{n} in {y}" for n, y in ns.items()) +
                    "); set top_n=100 for a like-for-like comparison.")

    fig.update_yaxes(title_text=f"{stat.capitalize()} overall score (0-100)")
    fig.update_xaxes(title_text="Year", tickmode="array", tickvals=sorted(table["year"].unique()))
    if show_spread:
        subtitle = f"Point = {stat} score; error bar = middle 50% of institutions (Q1 to Q3)"
        chart = "point plot with error bars"
    else:
        subtitle = f"Line = {stat} score per year; hover for Q1, Q3 and the number of institutions"
        chart = "line chart" if len(cats) == 1 else "multi-series line chart"
    subtitle += f" · exact ranks 1-{top_n} only" if top_n else ""
    finish(fig, title, subtitle, note=CROSS_CATEGORY_NOTE if len(cats) > 1 else None, legend_title="Category")
    shown = (f"Each point shows the {stat}; its error bar runs from Q1 to Q3 and holds the middle half of "
             f"institutions, so a longer bar means scores are more spread out."
             if show_spread else
             f"One line with markers per category joins the yearly {stat}s; Q1, Q3 and the number of "
             f"institutions are in the hover (set show_spread=True to draw Q1-Q3 as error bars).")
    method = (f"For every category and year we take all institutions with a published overall score"
              f"{f' and an exact rank of {top_n} or better' if top_n else ''}, and compute the {stat} "
              f"(mean = sum / count; median = middle value after sorting), the 25th percentile Q1 and the 75th "
              f"percentile Q3. {shown} Scores of band-only positions are not published by NIRF, so they cannot "
              f"be included. NIRF has adjusted some sub-metrics over the years, so part of a change can come from "
              f"the method rather than the institutions.")
    return ChartResult(fig, table, insight, method, chart)


def consistent_top_n(category: str = "Overall", n: int = 10, min_years: int = 5) -> ChartResult:
    """Answers questions like: "Which institutions stayed in the top 10 across multiple years?" (Q1.5)

    Definition: an institution is "in the top n" in a year when its rank is certainly n or better
    (exact rank <= n, or a whole NIRF band within the top n).
    Method: count, per institution, the years it was in the top n; keep those with at least
    min_years such years. Heatmap: one row per institution, one column per year; dark cells = in the
    top n (labelled with the rank), light grey = ranked but outside the top n, blank = not ranked.
    """
    df = load_master()
    category = check_category(category, df)
    years = category_years(category, df)
    n, min_years = int(n), int(min_years)
    if n < 1:
        raise NirfInputError("n must be at least 1.")
    if not 1 <= min_years <= len(years):
        raise NirfInputError(f"{category} has rankings in {len(years)} years ({fmt_years(years)}), so min_years "
                             f"must be between 1 and {len(years)}.")
    cat = filter_df(df, categories=category)
    cat["in_top"] = cat["rank_upper"].le(n).fillna(False).astype(bool)
    counts = cat[cat["in_top"]].groupby("institution_key")["year"].nunique()
    keep = counts[counts >= min_years]
    if keep.empty:
        raise NirfInputError(f"No institution was in the {category} top {n} in at least {min_years} of "
                             f"{len(years)} years. Try a smaller min_years or a larger n.")
    mean_rank = cat[cat["in_top"] & cat["institution_key"].isin(keep.index)].groupby("institution_key")["rank_upper"].mean()
    order = (pd.DataFrame({"years": keep, "mean_rank": mean_rank}).sort_values(["years", "mean_rank"],
                                                                              ascending=[False, True]).index.tolist())
    labels = chart_labels(order)
    sub = cat[cat["institution_key"].isin(order)].set_index(["institution_key", "year"])

    z, text, hover = [], [], []
    for k in order:
        zr, tr, hr = [], [], []
        for y in years:
            if (k, y) in sub.index:
                r = sub.loc[(k, y)]
                pos = r["rank_raw"]
                kind = "rank" if pd.notna(r["rank"]) else "band"
                if r["in_top"]:
                    cell = (2, str(pos), f"{kind} {pos} (in the top {n})")
                else:
                    cell = (1, "", f"{kind} {pos} (outside the top {n})")
            else:
                cell = (0, "", f"not ranked in {category}")
            zr.append(cell[0])
            tr.append(cell[1])
            hr.append(cell[2])
        z.append(zr)
        text.append(tr)
        hover.append(hr)
    ylab = [labels[k] for k in order]
    fig = go.Figure(go.Heatmap(
        z=z, x=[str(y) for y in years], y=ylab, text=text, texttemplate="%{text}", customdata=hover,
        textfont=dict(color="white", size=11), zmin=0, zmax=2, showscale=False,
        colorscale=[[0, SURFACE], [0.33, SURFACE], [0.33, CONTEXT], [0.66, CONTEXT], [0.66, UP], [1, UP]],
        hovertemplate="<b>%{y}</b><br>%{x}: %{customdata}<extra></extra>"))
    for name, c in ((f"In the top {n} (number = rank)", UP), (f"Ranked, outside the top {n}", CONTEXT)):
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", name=name,
                                 marker=dict(symbol="square", size=12, color=c)))
    fig.update_yaxes(autorange="reversed", showgrid=False, showline=False, ticks="")
    fig.update_xaxes(showgrid=False, showline=False, ticks="", side="top", title_text=None)
    fig.update_layout(legend=dict(orientation="h", x=0, y=-0.02, yanchor="top"), margin=dict(t=120, b=110))

    always = [labels[k] for k in order if keep[k] == len(years)]
    title = (f"{len(order)} institutions were in the {category} top {n} in at least {min_years} of {len(years)} years")
    insight = (f"{len(order)} institutions were in the {category} top {n} in at least {min_years} of the "
               f"{len(years)} years ({fmt_years(years)}); "
               + (f"{len(always)} of them were there every year: {', '.join(always)}." if always
                  else f"none was there every year (most: {labels[order[0]]}, {keep[order[0]]} years)."))
    method = (f"For each year we mark an institution as 'in the top {n}' when its rank is certainly {n} or better "
              f"(an exact rank ≤ {n}, or a NIRF band whose worst rank is ≤ {n}). We count those years per "
              f"institution and keep everyone with at least {min_years}. Rows are sorted by the number of years in "
              f"the top {n}, then by average rank in those years.")
    finish(fig, title, f"{category} ranking, {fmt_years(years)} · sorted by years in the top {n}",
           height=max(380, 200 + 26 * len(order)))
    table = pd.DataFrame({"institution": ylab, "years_in_top_n": [int(keep[k]) for k in order],
                          "average_rank_when_in_top_n": [round(float(mean_rank[k]), 1) for k in order]})
    ranks = sub.reset_index().pivot(index="institution_key", columns="year", values="rank_raw").reindex(order)
    for y in years:
        table[str(y)] = ranks[y].tolist() if y in ranks else None
    return ChartResult(fig, table, insight, method, "matrix heatmap")



def top_n_race(category: str = "Overall", years=None, n: int = 10, highlight: int = 3,
               depth: int | None = None) -> ChartResult:
    """Answers questions like: "How did this year's top 10 get there?" (the home page overview chart)

    Definition: the n institutions with the best exact ranks in the last chosen year, followed back
    through their exact rank in every earlier year.
    Method: one line per institution through its exact ranks; a year with only a band or no rank is
    a gap. The y-axis is reversed (rank 1 at the top) and shows ranks 1 to `depth` (default 2.5 x n);
    a line that leaves the bottom was ranked below that (the hover still gives the real rank). The
    best `highlight` institutions are coloured and the rest drawn in grey, each named at the line end.
    """
    df = load_master()
    category = check_category(category, df)
    years = check_years(years, category, df)
    n, highlight = int(n), int(highlight)
    if not 2 <= n <= 20:
        raise NirfInputError("Choose between 2 and 20 institutions for the rank race.")
    highlight = max(0, min(highlight, n, MAX_LINES))
    cat = filter_df(df, years=years, categories=category, exact_ranks_only=True)
    last_year = max(years)
    last = cat[cat["year"].eq(last_year)].sort_values(["rank", "canonical_name"]).head(n)
    if last.empty:
        raise NirfInputError(f"NIRF published no exact {category} ranks in {last_year}.")
    keys = last["institution_key"].tolist()
    labels = chart_labels(keys)
    sub = cat[cat["institution_key"].isin(keys)]
    ranks = sub.pivot_table(index="institution_key", columns="year", values="rank", aggfunc="min").reindex(keys)
    ranks = ranks.reindex(columns=years)
    # Default depth 2.5 x n, but deep enough that every line's last-year rank is on the chart (with a
    # state filter "today's top 5" can be ranked 20-80 nationally).
    depth = int(depth) if depth else int(max(np.ceil(2.5 * n / 5), np.ceil(1.2 * last["rank"].max() / 5)) * 5)

    colors = {k: (CATEGORICAL[i] if i < highlight else OTHER) for i, k in enumerate(keys)}
    fig = go.Figure()
    # Grey context lines first so the coloured ones are drawn on top.
    for k in sorted(keys, key=lambda k: colors[k] != OTHER):
        r = ranks.loc[k].astype(float)
        name, c = labels[k], colors[k]
        strong = c != OTHER
        end = int(r[last_year])
        fig.add_trace(go.Scatter(
            x=years, y=r.values, mode="lines+markers", name=f"{end} · {name}", connectgaps=False,
            line=dict(color=c, width=2.5 if strong else 1.5), marker=dict(color=c, size=8 if strong else 6),
            opacity=1 if strong else 0.9, legendrank=end,
            customdata=[f"rank {int(v)}" if pd.notna(v) else "no exact rank" for v in r.values],
            hovertemplate=f"<b>{name}</b><br>%{{x}}: %{{customdata}}<extra></extra>"))
        fig.add_trace(go.Scatter(
            x=[last_year], y=[end], mode="text", text=[f"  {name}"], textposition="middle right",
            textfont=dict(size=11, color=INK if strong else INK_SECONDARY), cliponaxis=False, showlegend=False,
            hoverinfo="skip"))

    first_rank = {k: ranks.loc[k].dropna() for k in keys}
    moves = {k: int(s.iloc[0]) - int(s.iloc[-1]) for k, s in first_rank.items() if len(s) > 1}
    span = f"{min(years)}–{last_year}" if len(years) > 1 else str(last_year)
    leader = keys[0]
    lead_rank = int(ranks.at[leader, last_year])
    leader_years = int((ranks.loc[leader] == lead_rank).sum())
    if len(years) > 1 and moves:
        climber = max(moves, key=moves.get)
        s = first_rank[climber]
        climb = (f"; {labels[climber]} climbed the most, from rank {int(s.iloc[0])} in {int(s.index[0])} to "
                 f"{int(s.iloc[-1])} in {last_year} ({places(moves[climber])})" if moves[climber] > 0 else "")
        always = int(sum(ranks.loc[k].le(n).all() for k in keys))
        insight = (f"{labels[leader]} is rank {lead_rank} in {category} {last_year} and held that rank in {leader_years} of "
                   f"{len(years)} years{climb}. {always} of today's top {n} were in the top {n} in every year "
                   f"{span}.")
        title = (f"{labels[leader]} leads {category} {last_year}; {labels[climber]} made the biggest climb"
                 if moves[climber] > 0 else f"{labels[leader]} leads the {category} top {n} in {last_year}")
    else:
        insight = f"{labels[leader]} is rank {lead_rank} in {category} {last_year}."
        title = f"{labels[leader]} leads the {category} top {n} in {last_year}"

    fig.update_yaxes(title_text="Rank (1 = best, shown at the top)", range=[depth + 0.6, 0.4], tickvals=
                     [1] + list(range(5, depth + 1, 5)), zeroline=False)
    fig.update_xaxes(title_text="Year", dtick=1, range=[min(years) - 0.3, last_year + 0.3], showgrid=True)
    fig.update_layout(margin=dict(r=190), legend=dict(title_text=f"{last_year} rank · institution"),
                      hovermode="closest")
    finish(fig, title, f"{category} ranking, {span} · the top {n} of {last_year}, followed back in time",
           note=f"Gaps = no exact rank that year; a line leaving the bottom = ranked below {depth}.",
           legend_title=f"{last_year} rank · institution", height=560)

    table = pd.DataFrame({"institution": [labels[k] for k in keys]})
    for y in years:
        table[str(y)] = [ranks.at[k, y] for k in keys]
    table["change_first_to_last"] = [moves.get(k) for k in keys]
    method = (f"We take the {n} institutions with the best exact {category} ranks in {last_year} and look up their "
              f"exact rank in every year {span}. Each line joins those ranks; years with only a NIRF band or no rank "
              f"are gaps (never filled in). The y-axis is reversed so rank 1 is at the top and shows ranks 1-{depth}. "
              f"Change = first exact rank - last exact rank (positive = moved up).")
    return ChartResult(fig, table, insight, method, "multi-series line chart")
