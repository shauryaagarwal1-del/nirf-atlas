"""Geography engine: where the ranked institutions are and how that changes (Annexure A section 2, Q2.1-Q2.5).

Functions
  state_counts()                 institutions per state in the top N of one year (horizontal bar)
  state_share_over_time()        each state's share of the top N, year by year (stacked area)
  state_representation_change()  change in a state's top-N count between two years (diverging bar)
  compare_states()               rank distributions of chosen states per year (box + median line)
  new_entrants_by_state()        institutions appearing for the first time, by state and year (stacked bar)

"In the top N" means the rank is certainly N or better: an exact rank <= N, or a NIRF band whose
worst rank is <= N (a 76-100 row is in the top 100; a 101-150 row is not). States are the official
names after cleaning (e.g. Pondicherry -> Puducherry).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from core.data import (NirfInputError, category_years, check_category, check_states, check_year, check_years,
                       filter_df, fmt_years, load_master, short_name)
from core.result import ChartResult
from core.stats import signed
from core.theme import CATEGORICAL, DOWN, INK_SECONDARY, UP, color_map, finish, ordinal_blues

MAX_AREAS = 7          # states drawn in their own colour; the rest are summed as "Other states"
MAX_STATES = 8


def _top(df: pd.DataFrame, top_n: int) -> pd.DataFrame:
    """Rows certainly within the top `top_n` of their list."""
    if int(top_n) < 1:
        raise NirfInputError("top_n must be at least 1.")
    return df[df["rank_upper"].le(int(top_n)).fillna(False).astype(bool)]


def _list_note(cat: pd.DataFrame, top_n: int, years: list[int]) -> str | None:
    """Explain when a list has fewer certain positions than top_n (e.g. Law ranks only 40)."""
    short: dict[int, list[int]] = {}
    for y in years:
        last = cat.loc[cat["year"].eq(y), "rank_upper"].max()
        if pd.notna(last) and last < top_n:
            short.setdefault(int(last), []).append(y)
    if not short:
        return None
    parts = "; ".join(f"{n} in {fmt_years(ys)}" for n, ys in short.items())
    return f"NIRF ranks fewer than {top_n} here ({parts}), so every ranked institution is counted."


def state_counts(year: int | None = None, category: str = "Overall", top_n: int = 100) -> ChartResult:
    """Answers questions like: "Which states have the most institutions in the top 100 in 2025?" (Q2.1)

    Definition: number of institutions of each state certainly ranked within the top N of the
    chosen category and year.
    Method: filter the year's list to ranks <= N, count institutions per state, sort from most to
    fewest. Share = state count / all top-N institutions x 100.
    """
    df = load_master()
    category = check_category(category, df)
    year = check_year(category_years(category, df)[-1] if year is None else year, category, df)
    cat = filter_df(df, categories=category, years=year)
    top = _top(cat, top_n).sort_values("rank_upper")
    if top.empty:
        raise NirfInputError(f"No {category} institution has a certain rank within the top {top_n} in {year}.")

    g = top.groupby("state")
    table = pd.DataFrame({
        "institutions": g.size(),
        "best_rank": g["rank_raw"].first(),
        "examples": g["canonical_name"].apply(lambda s: ", ".join(short_name(n, 40) for n in s.head(5))
                                              + (f" (+{len(s) - 5} more)" if len(s) > 5 else "")),
    }).sort_values(["institutions", "state"], ascending=[False, True]).reset_index()
    table.insert(2, "share_pct", (100 * table["institutions"] / len(top)).round(1))

    plot = table.iloc[::-1]
    fig = go.Figure(go.Bar(
        x=plot["institutions"], y=plot["state"], orientation="h", marker_color=CATEGORICAL[0],
        text=plot["institutions"], textposition="outside", cliponaxis=False, name="Institutions",
        customdata=np.stack([plot["share_pct"], plot["best_rank"], plot["examples"]], axis=1),
        hovertemplate=("<b>%{y}</b><br>%{x} institutions (%{customdata[0]}% of the top " + str(top_n) + ")"
                       "<br>Best rank: %{customdata[1]}<br>%{customdata[2]}<extra></extra>")))
    fig.update_xaxes(title_text=f"Institutions in the {category} top {top_n}, {year}", showgrid=True,
                     range=[0, table["institutions"].max() * 1.12])
    fig.update_yaxes(title_text=None, showgrid=False)

    lead = table[table["institutions"].eq(table["institutions"].max())]["state"].tolist()
    top3 = table.head(3)
    who = _join(lead)
    group = f"top-{top_n}" if cat["rank_upper"].max() >= top_n else "ranked"
    title = (f"{who} {'has' if len(lead) == 1 else 'share'} the most {category} {group} institutions "
             f"in {year} ({table['institutions'].max()})")
    insight = (f"In {year}, {who} {'has' if len(lead) == 1 else 'share'} the most institutions in the {category} "
               f"top {top_n} ({table['institutions'].max()}{' each' if len(lead) > 1 else ''}); the top three states ("
               f"{', '.join(f'{s} {c}' for s, c in zip(top3['state'], top3['institutions']))}) hold "
               f"{top3['share_pct'].sum():.0f}% of the {len(top)} places, spread over {len(table)} states/UTs.")
    note = _list_note(cat, top_n, [year])
    finish(fig, title, f"{category} ranking {year} · {len(top)} institutions in the top {top_n}", note=note,
           height=max(380, 160 + 24 * len(table)))
    method = (f"We take the {category} list of {year} and keep institutions whose rank is certainly {top_n} or "
              f"better (exact rank ≤ {top_n}, or a NIRF band ending at or before {top_n}). We count them per "
              f"state (official state names after cleaning) and sort from most to fewest. Share = state count / "
              f"{len(top)} × 100.")
    return ChartResult(fig, table, insight, method, "bar")


def _join(names) -> str:
    """['A'] -> 'A'; ['A', 'B', 'C'] -> 'A, B and C' (ties are named together, never hidden)."""
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _state_year_counts(cat: pd.DataFrame, years: list[int], top_n: int) -> pd.DataFrame:
    top = _top(cat, top_n)
    counts = top.groupby(["year", "state"]).size().unstack(fill_value=0).reindex(years, fill_value=0)
    return counts


def state_share_over_time(category: str = "Overall", top_n: int = 100) -> ChartResult:
    """Answers questions like: "How is the geographical distribution of top-ranked institutions changing
    from 2017 to 2025?" (Q2.2)

    Definition: a state's share in a year = its institutions in the top N / all institutions in the
    top N that year x 100 (so the shares of a year add up to 100%).
    Method: compute every state's share per year; draw the 7 states with the most top-N places over
    all years in their own colour and add the rest together as "Other states" (stacked area).
    """
    df = load_master()
    category = check_category(category, df)
    years = category_years(category, df)
    cat = filter_df(df, categories=category)
    counts = _state_year_counts(cat, years, top_n)
    shares = counts.div(counts.sum(axis=1), axis=0) * 100

    order = counts.sum().sort_values(ascending=False).index.tolist()
    main = order[:MAX_AREAS]
    plot = shares[main].copy()
    plot_counts = counts[main].copy()
    if len(order) > MAX_AREAS:
        plot["Other states"] = shares[order[MAX_AREAS:]].sum(axis=1)
        plot_counts["Other states"] = counts[order[MAX_AREAS:]].sum(axis=1)
    colors = color_map(list(plot.columns), other_label="Other states")

    fig = go.Figure()
    for s in plot.columns:
        fig.add_trace(go.Scatter(
            x=plot.index, y=plot[s], name=s, mode="lines", stackgroup="one", line=dict(width=0.8, color=colors[s]),
            fillcolor=colors[s], customdata=plot_counts[s],
            hovertemplate=f"<b>{s}</b> %{{x}}<br>%{{y:.1f}}% of the top {top_n} (%{{customdata}} institutions)<extra></extra>"))
    fig.update_yaxes(title_text=f"Share of the {category} top {top_n} (%)", range=[0, 100], ticksuffix="%")
    fig.update_xaxes(title_text="Year", dtick=1)
    fig.update_layout(hovermode="x unified")

    a, z = years[0], years[-1]
    diff = (shares.loc[z] - shares.loc[a]).sort_values()
    gain, loss = diff.index[-1], diff.index[0]
    leader = shares.loc[z].idxmax()
    title = (f"{gain} gained the largest share of the {category} top {top_n} from {a} to {z} "
             f"({signed(diff[gain], 1)} points)")
    insight = (f"{gain}'s share of the {category} top {top_n} grew from {shares.at[a, gain]:.0f}% in {a} to "
               f"{shares.at[z, gain]:.0f}% in {z} (the largest gain), while {loss} fell from "
               f"{shares.at[a, loss]:.0f}% to {shares.at[z, loss]:.0f}%; {leader} holds the largest share in {z} "
               f"({shares.at[z, leader]:.0f}%).")
    table = shares.round(1).stack().rename("share_pct").reset_index()
    table["institutions"] = counts.stack().values
    table = table[table["institutions"].gt(0)].sort_values(["year", "share_pct"], ascending=[True, False])
    note = _list_note(cat, top_n, years)
    finish(fig, title, f"{category} ranking {fmt_years(years)} · top {len(main)} states shown separately",
           note=note, legend_title="State")
    method = (f"For each year we count the institutions of every state that are certainly in the {category} top "
              f"{top_n}, and divide by the total for that year (× 100), so each year's shares add up to 100%. "
              f"The {len(main)} states with the most top-{top_n} places over all years get their own colour; the "
              f"other {max(len(order) - MAX_AREAS, 0)} states are added together as 'Other states' so the chart "
              f"stays readable. A stacked area shows both each state's share and how the whole mix shifts.")
    return ChartResult(fig, table.reset_index(drop=True), insight, method, "area")


def state_representation_change(category: str = "Overall", start_year: int | None = None,
                                end_year: int | None = None, top_n: int = 100) -> ChartResult:
    """Answers questions like: "Which states have improved their representation in the top 100 over time?" (Q2.3)

    Definition: change = (institutions in the top N in end_year) - (institutions in the top N in
    start_year), per state. Positive = the state gained places.
    Method: count top-N institutions per state in both years, subtract, and sort; states with no
    change are left out of the chart but kept in the table.
    """
    df = load_master()
    category = check_category(category, df)
    available = category_years(category, df)
    start_year = check_year(available[0] if start_year is None else start_year, category, df)
    end_year = check_year(available[-1] if end_year is None else end_year, category, df)
    if start_year >= end_year:
        raise NirfInputError(f"The start year ({start_year}) must be before the end year ({end_year}).")
    cat = filter_df(df, categories=category, years=[start_year, end_year])
    counts = _state_year_counts(cat, [start_year, end_year], top_n).T
    table = counts.rename(columns={start_year: f"count_{start_year}", end_year: f"count_{end_year}"})
    table.columns.name = None
    table["change"] = table[f"count_{end_year}"] - table[f"count_{start_year}"]
    table = table.sort_values(["change", f"count_{end_year}"], ascending=[False, False]).reset_index()
    moved = table[table["change"].ne(0)].iloc[::-1]
    if moved.empty:
        raise NirfInputError(f"No state changed its number of {category} top-{top_n} institutions between "
                             f"{start_year} and {end_year}.")

    fig = go.Figure(go.Bar(
        x=moved["change"], y=moved["state"], orientation="h",
        marker_color=[UP if c > 0 else DOWN for c in moved["change"]],
        text=[f"{a} → {b}" for a, b in zip(moved[f"count_{start_year}"], moved[f"count_{end_year}"])],
        textposition="outside", cliponaxis=False, showlegend=False,
        customdata=np.stack([moved[f"count_{start_year}"], moved[f"count_{end_year}"]], axis=1),
        hovertemplate=(f"<b>%{{y}}</b><br>{start_year}: %{{customdata[0]}} institutions<br>{end_year}: "
                       f"%{{customdata[1]}} institutions<br>Change: %{{x:+d}}<extra></extra>")))
    for name, c, show in (("Gained places", UP, (moved["change"] > 0).any()),
                          ("Lost places", DOWN, (moved["change"] < 0).any())):
        if show:
            fig.add_trace(go.Bar(x=[None], y=[None], name=name, marker_color=c, orientation="h"))
    lo, hi = min(0, moved["change"].min()), max(0, moved["change"].max())
    pad = 0.22 * (hi - lo)
    fig.update_xaxes(title_text=f"Change in top-{top_n} institutions ({end_year} − {start_year})", showgrid=True,
                     range=[lo - (pad if lo < 0 else 0), hi + (pad if hi > 0 else 0)], zeroline=True,
                     zerolinecolor=INK_SECONDARY, dtick=1 if hi - lo <= 12 else None)
    fig.update_yaxes(title_text=None, showgrid=False)
    fig.update_layout(barmode="overlay", legend=dict(orientation="h", x=0, y=1.0, yanchor="bottom"))

    best, worst = table["change"].max(), table["change"].min()
    winners = _join(table.loc[table["change"].eq(best), "state"])
    losers_ = _join(table.loc[table["change"].eq(worst), "state"])
    gainers, losers = int((table["change"] > 0).sum()), int((table["change"] < 0).sum())
    if best > 0:
        title = (f"{winners} gained the most {category} top-{top_n} places, {start_year}→{end_year} "
                 f"({signed(best)})")
        detail = table[table["change"].eq(best)].iloc[0]
        insight = (f"Between {start_year} and {end_year}, {winners} improved {category} top-{top_n} representation "
                   f"the most ({signed(best)}" + (f", {detail[f'count_{start_year}']} → "
                                                  f"{detail[f'count_{end_year}']})" if (table['change'] == best).sum() == 1 else ")"))
    else:
        title = f"No state gained {category} top-{top_n} places, {start_year}→{end_year}"
        insight = f"Between {start_year} and {end_year}, no state gained places in the {category} top {top_n}"
    insight += (f"; {losers_} lost the most ({signed(worst)}). {gainers} states gained, "
                f"{losers} lost and {len(table) - gainers - losers} stayed the same."
                if worst < 0 else "; no state lost places.")
    finish(fig, title, f"{category} ranking · labels show the number of institutions {start_year} → {end_year}",
           note=_list_note(cat, top_n, [start_year, end_year]), height=max(380, 170 + 26 * len(moved)),
           legend_title="")
    method = (f"For {start_year} and {end_year} we count, per state, the institutions certainly in the {category} "
              f"top {top_n}. Change = count in {end_year} − count in {start_year}: positive means the state "
              f"gained places. States with no change are not drawn but are listed in the table. Because the top "
              f"{top_n} always has the same number of places, one state's gain is another state's loss.")
    return ChartResult(fig, table, insight, method, "bar")


def compare_states(states=("Karnataka", "Tamil Nadu"), category: str = "Overall", years=None) -> ChartResult:
    """Answers questions like: "How do the rankings of institutions in Karnataka compare with those in
    Tamil Nadu?" (Q2.4)

    Definition: the exact ranks of all ranked institutions located in each chosen state.
    Method: per year and state, a box plot of those ranks (median line, box = middle 50%, whiskers
    and dots for the rest) plus a line through each state's yearly median rank. Lower = better, so
    the rank axis is reversed. Exact ranks only: band-only positions (e.g. 101-150) have no number.
    """
    df = load_master()
    category = check_category(category, df)
    years = check_years(years, category, df)
    states = check_states(states, df)
    if not states:
        raise NirfInputError("Please choose at least one state.")
    if len(states) > MAX_STATES:
        raise NirfInputError(f"Please choose at most {MAX_STATES} states.")
    sub = filter_df(df, categories=category, years=years, states=states)
    exact = sub[sub["rank"].notna()].copy()
    missing = [s for s in states if s not in set(exact["state"])]
    if missing:
        raise NirfInputError(f"{', '.join(missing)} has no institution with an exact {category} rank in "
                             f"{fmt_years(years)}.")
    exact["rank"] = exact["rank"].astype(float)

    colors = color_map(states)
    fig = go.Figure()
    for s in states:
        t = exact[exact["state"].eq(s)]
        fig.add_trace(go.Box(
            x=t["year"], y=t["rank"], name=s, legendgroup=s, offsetgroup=s, marker_color=colors[s],
            line_color=colors[s], fillcolor="rgba(0,0,0,0)", boxpoints="all", jitter=0.4, pointpos=0,
            customdata=np.stack([t["canonical_name"], t["rank_raw"]], axis=1),
            hovertemplate="<b>%{customdata[0]}</b><br>%{x}: rank %{customdata[1]}<extra>" + s + "</extra>"))
    med = exact.groupby(["state", "year"])["rank"].agg(["median", "size"]).reset_index()
    for s in states:
        m = med[med["state"].eq(s)]
        fig.add_trace(go.Scatter(
            x=m["year"], y=m["median"], mode="lines", name=f"{s} median", legendgroup=s, showlegend=False,
            line=dict(color=colors[s], width=1.5), customdata=m["size"],
            hovertemplate=f"<b>{s}</b> %{{x}}<br>Median rank %{{y:.1f}} of %{{customdata}} institutions<extra></extra>"))
    fig.update_layout(boxmode="group", boxgap=0.25, boxgroupgap=0.1)
    fig.update_yaxes(title_text="Exact rank (1 = best, shown at the top)", autorange="reversed")
    fig.update_xaxes(title_text="Year", dtick=1)

    pooled = exact.groupby("state").agg(median_rank=("rank", "median"), mean_rank=("rank", "mean"),
                                        best_rank=("rank", "min"), ranked_rows=("rank", "size"))
    pooled["avg_per_year"] = pooled["ranked_rows"] / len(years)
    banded = sub[sub["rank"].isna()].groupby("state").size()
    pooled["band_only_rows"] = banded.reindex(pooled.index, fill_value=0)
    pooled = pooled.reindex(states)
    better = pooled["median_rank"].idxmin()
    more = pooled["avg_per_year"].idxmax()
    span = fmt_years(years)
    if len(states) == 1:
        title = f"{states[0]}: median {category} rank {pooled.at[states[0], 'median_rank']:.0f} over {span}"
        insight = (f"Over {span}, {states[0]} had on average {pooled.at[states[0], 'avg_per_year']:.1f} institutions "
                   f"with an exact {category} rank per year, with a median rank of "
                   f"{pooled.at[states[0], 'median_rank']:.0f} (best {pooled.at[states[0], 'best_rank']:.0f}).")
    else:
        other = [s for s in states if s != better]
        title = f"{better}'s institutions rank better in {category} (median {pooled.at[better, 'median_rank']:.0f})"
        insight = (f"Over {span}, {better}'s {category}-ranked institutions had the best median rank "
                   f"({pooled.at[better, 'median_rank']:.0f} vs "
                   + ", ".join(f"{pooled.at[s, 'median_rank']:.0f} for {s}" for s in other) + "), while "
                   f"{more} had the most ranked institutions ({pooled.at[more, 'avg_per_year']:.1f} per year vs "
                   + ", ".join(f"{pooled.at[s, 'avg_per_year']:.1f}" for s in states if s != more) + ").")
    table = med.rename(columns={"median": "median_rank", "size": "institutions"})
    table = table.merge(exact.groupby(["state", "year"])["rank"].agg(best_rank="min", worst_rank="max")
                        .astype(int).reset_index(), on=["state", "year"])
    finish(fig, title, f"{category} ranking, {span} · box = middle 50% of ranks, line = median rank",
           note="Exact ranks only; institutions NIRF lists only in a band (e.g. 101-150) are not drawn.",
           legend_title="State")
    method = (f"For every year we collect the exact {category} ranks of institutions located in "
              f"{', '.join(states)}. Each box shows that year's ranks of one state: the line inside is the median "
              f"(middle value), the box spans Q1 to Q3 (middle half), dots are individual institutions. A thin line "
              f"joins each state's yearly medians. The insight pools all years: the median rank (lower = better) "
              f"and the average number of ranked institutions per year, because a state with many institutions "
              f"naturally also has more of them further down the list. Band-only positions "
              f"({int(pooled['band_only_rows'].sum())} rows) have no exact rank and are left out.")
    return ChartResult(fig, table, insight, method, "box")


def new_entrants_by_state(category: str = "Overall", years=None) -> ChartResult:
    """Answers questions like: "Which states have produced the largest number of newly appearing
    institutions in the rankings?" (Q2.5)

    Definition: a new entrant is an institution appearing in the category's ranked list (exact rank
    or band) for the first time, in a year when the category already existed the year before.
    Method: count new entrants per state and year; one horizontal bar per state, split into years
    (darker = later), states sorted by their total.
    """
    df = load_master()
    category = check_category(category, df)
    available = category_years(category, df)
    years = check_years(available[1:] if years is None and len(available) > 1 else years, category, df)
    cat = filter_df(df, categories=category, years=years)
    new = cat[cat["is_new_entrant"]]
    if new.empty:
        raise NirfInputError(f"No new {category} entrants in {fmt_years(years)} ({category} starts in "
                             f"{available[0]}, and nobody counts as new in the first year).")
    counts = new.groupby(["state", "year"]).size().unstack(fill_value=0)
    counts = counts.reindex(columns=[y for y in years if y in counts.columns])
    totals = counts.sum(axis=1).sort_values(ascending=True)
    counts = counts.loc[totals.index]

    shades = dict(zip(counts.columns, ordinal_blues(len(counts.columns))))
    fig = go.Figure()
    for y in counts.columns:
        fig.add_trace(go.Bar(
            y=counts.index, x=counts[y], name=str(y), orientation="h", marker_color=shades[y],
            marker_line=dict(width=1, color="#fcfcfb"),
            hovertemplate=f"<b>%{{y}}</b><br>{y}: %{{x}} new institutions<extra></extra>"))
    fig.add_trace(go.Scatter(
        y=totals.index, x=totals.values, mode="text", text=[f"  {v}" for v in totals.values],
        textposition="middle right", textfont=dict(color=INK_SECONDARY, size=11), showlegend=False,
        hoverinfo="skip", cliponaxis=False))
    fig.update_layout(barmode="stack", barcornerradius=0)
    fig.update_xaxes(title_text=f"New {category} entrants, {fmt_years(years)}", showgrid=True,
                     range=[0, totals.max() * 1.12])
    fig.update_yaxes(title_text=None, showgrid=False)

    ranked = totals.iloc[::-1]
    total = int(ranked.sum())
    top3 = ranked.head(3)
    title = f"{ranked.index[0]} produced the most new {category} entrants ({ranked.iloc[0]}, {fmt_years(years)})"
    insight = (f"Of {total} institutions that entered the {category} ranking for the first time in {fmt_years(years)}, "
               f"{ranked.index[0]} produced the most ({ranked.iloc[0]}, {100 * ranked.iloc[0] / total:.0f}%), "
               f"followed by " + " and ".join(f"{s} ({v})" for s, v in top3.iloc[1:].items()) + ".")
    per_year = new.groupby("year").size()
    busiest = int(per_year.idxmax())
    table = counts.iloc[::-1].copy()
    table.columns = [str(c) for c in table.columns]
    table["total"] = table.sum(axis=1)
    table = table.reset_index()
    finish(fig, title, f"{category} ranking · bar = new institutions per state, split by year (darker = later)",
           note=f"Busiest year: {busiest} ({per_year.max()} new entrants). Years when NIRF lengthened the list "
                f"add more entrants.", height=max(380, 170 + 22 * len(totals)), legend_title="Year")
    method = (f"An institution is a new entrant in the year it first appears in the {category} ranked list "
              f"(exact rank or band), provided the {category} list already existed the year before, so nobody is "
              f"'new' in {available[0]}, the category's first year. We count new entrants per state and year, "
              f"sort states by their total, and split each bar by year. Years in which NIRF lengthened the list "
              f"(e.g. more ranks or bands published) naturally bring more new entrants.")
    return ChartResult(fig, table, insight, method, "bar")
