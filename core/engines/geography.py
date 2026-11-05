"""Geography engine: where the ranked institutions are and how that changes (Annexure A section 2, Q2.1-Q2.5).

Functions
  state_counts()                 institutions per state in the top N of one year (ranked horizontal bar chart)
  state_share_over_time()        each state's share of the top N, year by year (multi-series line chart)
  state_representation_change()  change in a state's top-N count between two years (ranked horizontal bar
                                 chart, bars left of zero = lost places)
  compare_states()               rank distributions of chosen states per year (box-and-whisker plot + a thin
                                 line through the yearly medians)
  new_entrants_by_state()        institutions appearing for the first time, by state (bar chart of totals, or
                                 a stacked bar chart split by year)
  state_map()                    institutions per state in the top N, on the map of India, with a year slider and
                                 a play button that animates the map from the first to the last year (choropleth map)
  state_vs_state()               two (or more) states head to head: ranked institutions per year and median rank
                                 per year, one panel above the other (vertically aligned time-series charts)
  state_rank_boxes()             all the ranks of each chosen state over the chosen years, side by side
                                 (box-and-whisker plot)

Every chart type is one of the types listed in docs/allowed_charts.md.

"In the top N" means the rank is certainly N or better: an exact rank <= N, or a NIRF band whose
worst rank is <= N (a 76-100 row is in the top 100; a 101-150 row is not). States are the official
names after cleaning (e.g. Pondicherry -> Puducherry).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from core.data import (NirfInputError, category_years, change_years, check_category, check_states, check_year,
                       check_years, filter_df, fmt_years, list_sizes, load_master, n_years, short_name)
from core.geo import FEATURE_KEY, india_geojson, polygon_frame, state_polygons
from core.result import ChartResult
from core.stats import signed
from core.theme import (AXIS, CATEGORICAL, CONTEXT, DOWN, GRID, INK, INK_MUTED, INK_SECONDARY, RAMP, SURFACE, TEAL,
                        TITLE_WRAP, UP, color_map, finish, ordinal_ramp, tint, wrap_text)

MAX_LINES = 8          # states drawn as their own line; the rest are summed as "Other states"
MAX_STATES = 8
MAX_VS_STATES = 4


def _top(df: pd.DataFrame, top_n: int) -> pd.DataFrame:
    """Rows certainly within the top `top_n` of their list."""
    if int(top_n) < 1:
        raise NirfInputError("top_n must be at least 1.")
    return df[df["rank_upper"].le(int(top_n)).fillna(False).astype(bool)]


def _cap_top_n(cat: pd.DataFrame, top_n: int, category: str, years: list[int]) -> tuple[int, str | None]:
    """(top_n, None), or (the list size, a sentence) when top_n is larger than every list of these years.

    'Top 500' of a list with 200 places would count every ranked institution and then speak of 500
    places, so the top 200 is used instead and the answer says so.
    """
    if int(top_n) < 1:
        raise NirfInputError("top_n must be at least 1.")
    sizes = list_sizes(category, years)                    # the national list, also under a state / type filter
    if sizes.empty or int(top_n) <= sizes.max():
        return int(top_n), None
    size = int(sizes.max())
    if len(years) == 1:
        lists = f"lists {size} institutions in {years[0]}"
    else:
        lists = f"lists {'' if sizes.nunique() == 1 else 'at most '}{size} institutions a year"
    return size, f"{category} {lists}, so the top {size} is used."


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
    top_n, capped = _cap_top_n(cat, top_n, category, [year])
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
    fig.update_yaxes(title_text="State / UT", showgrid=False)

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
    if capped:
        insight = f"{capped} {insight}"
    last = top["rank"].max()
    sharing = top[top["rank"].eq(last)]
    if len(top) > top_n and len(sharing) > 1:      # NIRF skips ranks after a tie, so only a tie at the end adds
        insight += (f" The top {top_n} holds {len(top)} institutions because {len(sharing)} share rank {int(last)}: "
                    f"{_join([short_name(n, 40) for n in sharing['canonical_name']])}.")
    note = _list_note(cat, top_n, [year])
    finish(fig, title, f"{category} ranking {year} · {len(top)} institutions in the top {top_n}", note=note,
           height=max(380, 160 + 24 * len(table)))
    method = (f"We take the {category} list of {year} and keep institutions whose rank is certainly {top_n} or "
              f"better (exact rank ≤ {top_n}, or a NIRF band ending at or before {top_n}). We count them per "
              f"state (official state names after cleaning) and sort from most to fewest. Share = state count / "
              f"{len(top)} × 100.")
    return ChartResult(fig, table, insight, method, "bar chart")


def _join(names) -> str:
    """['A'] -> 'A'; ['A', 'B', 'C'] -> 'A, B and C' (ties are named together, never hidden)."""
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _leading(counts: pd.Series, k: int = 3) -> list[str]:
    """The (up to) k states with the highest counts, without cutting through a tie.

    If the k-th place is shared with states outside the k, only the states strictly above that tie are
    named (at least the leader or leaders), so no state is picked arbitrarily from a tie.
    """
    s = counts.sort_values(ascending=False)
    if len(s) <= k:
        return s.index.tolist()
    cut = s.iloc[k - 1]
    if s.iloc[k] < cut:
        return s.index[:k].tolist()
    above = s[s > cut].index.tolist()
    return above or s[s.eq(s.iloc[0])].index.tolist()


def _state_year_counts(cat: pd.DataFrame, years: list[int], top_n: int) -> pd.DataFrame:
    top = _top(cat, top_n)
    counts = top.groupby(["year", "state"]).size().unstack(fill_value=0).reindex(years, fill_value=0)
    return counts


def state_share_over_time(category: str = "Overall", top_n: int = 100) -> ChartResult:
    """Answers questions like: "How is the geographical distribution of top-ranked institutions changing
    from 2017 to 2025?" (Q2.2)

    Definition: a state's share in a year = its institutions in the top N / all institutions in the
    top N that year x 100 (so the shares of a year add up to 100%).
    Method: compute every state's share per year; draw the 8 states with the most top-N places over
    all years as their own line and add the rest together as one "Other states" line (multi-series
    line chart: one line with markers per state, so each state's rise or fall can be read directly).
    """
    df = load_master()
    category = check_category(category, df)
    years = change_years(category, df)
    cat = filter_df(df, categories=category)
    top_n, capped = _cap_top_n(cat, top_n, category, years)
    counts = _state_year_counts(cat, years, top_n)
    shares = counts.div(counts.sum(axis=1), axis=0) * 100

    order = counts.sum().sort_values(ascending=False).index.tolist()
    main = order[:MAX_LINES]
    plot = shares[main].copy()
    plot_counts = counts[main].copy()
    if len(order) > MAX_LINES:
        plot["Other states"] = shares[order[MAX_LINES:]].sum(axis=1)
        plot_counts["Other states"] = counts[order[MAX_LINES:]].sum(axis=1)
    colors = color_map(list(plot.columns), other_label="Other states")

    fig = go.Figure()
    for s in plot.columns:
        other = s == "Other states"
        fig.add_trace(go.Scatter(
            x=plot.index, y=plot[s], name=s, mode="lines+markers",
            line=dict(color=colors[s], dash="dot" if other else "solid"), marker=dict(color=colors[s]),
            customdata=plot_counts[s],
            hovertemplate=f"<b>{s}</b> %{{x}}<br>%{{y:.1f}}% of the top {top_n} (%{{customdata}} institutions)<extra></extra>"))
    fig.update_yaxes(title_text=f"Share of the {category} top {top_n} (%)", range=[0, plot.max().max() * 1.08],
                     ticksuffix="%")
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
    hidden = [s for s in dict.fromkeys([gain, loss]) if s not in main]
    if hidden:
        title = title[:-1] + "; inside 'Other states')" if gain in hidden else title
        insight += f" {_join(hidden)} {'is' if len(hidden) == 1 else 'are'} part of the 'Other states' line."
    if capped:
        insight = f"{capped} {insight}"
    table = shares.round(1).stack().rename("share_pct").reset_index()
    table["institutions"] = counts.stack().values
    table = table[table["institutions"].gt(0)].sort_values(["year", "share_pct"], ascending=[True, False])
    note = _list_note(cat, top_n, years)
    finish(fig, title, f"{category} ranking {fmt_years(years)} · one line per state (top {len(main)} states "
           f"by top-{top_n} places; the rest summed as 'Other states')", note=note, legend_title="State")
    method = (f"For each year we count the institutions of every state that are certainly in the {category} top "
              f"{top_n}, and divide by the total for that year (× 100), so each year's shares add up to 100%. "
              f"The {len(main)} states with the most top-{top_n} places over all years get their own line; the "
              f"other {max(len(order) - MAX_LINES, 0)} states are added together as 'Other states' (dotted grey "
              f"line) so the chart stays readable. A multi-series line chart puts every state on the same 0% "
              f"baseline, so each state's rise or fall can be read and compared directly.")
    return ChartResult(fig, table.reset_index(drop=True), insight, method, "multi-series line chart")


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
    available = change_years(category, df)
    start_year = check_year(available[0] if start_year is None else start_year, category, df)
    end_year = check_year(available[-1] if end_year is None else end_year, category, df)
    if start_year >= end_year:
        raise NirfInputError(f"The start year ({start_year}) must be before the end year ({end_year}).")
    cat = filter_df(df, categories=category, years=[start_year, end_year])
    top_n, capped = _cap_top_n(cat, top_n, category, [start_year, end_year])
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
    fig.update_yaxes(title_text="State / UT", showgrid=False)
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
    if capped:
        insight = f"{capped} {insight}"
    finish(fig, title, f"{category} ranking · labels show the number of institutions {start_year} → {end_year}",
           note=_list_note(cat, top_n, [start_year, end_year]), height=max(380, 170 + 26 * len(moved)),
           legend_title="Change")
    method = (f"For {start_year} and {end_year} we count, per state, the institutions certainly in the {category} "
              f"top {top_n}. Change = count in {end_year} − count in {start_year}: positive means the state "
              f"gained places. States with no change are not drawn but are listed in the table. Because the top "
              f"{top_n} always has the same number of places, one state's gain is another state's loss.")
    return ChartResult(fig, table, insight, method, "bar chart")


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
                   f"{more} had the most institutions with an exact rank ({pooled.at[more, 'avg_per_year']:.1f} per year vs "
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
    return ChartResult(fig, table, insight, method, "box-and-whisker plot")


def new_entrants_by_state(category: str = "Overall", years=None, by_year: bool = True) -> ChartResult:
    """Answers questions like: "Which states have produced the largest number of newly appearing
    institutions in the rankings?" (Q2.5)

    Definition: a new entrant is an institution appearing in the category's ranked list (exact rank
    or band) for the first time, in a year when the category already existed the year before.
    Method: count new entrants per state and year and add them up per state; states sorted by their
    total. by_year=True splits each state's bar into years (stacked bar chart, darker = later);
    by_year=False draws one plain bar per state (bar chart) with the yearly split in the hover text.
    """
    df = load_master()
    category = check_category(category, df)
    available = category_years(category, df)
    years = check_years(available[1:] if years is None and len(available) > 1 else years, category, df)
    if len(available) > 1 and years != [available[0]]:
        years = [y for y in years if y != available[0]]       # nobody is new in the first year: not in the span
    cat = filter_df(df, categories=category, years=years)
    new = cat[cat["is_new_entrant"]]
    if new.empty:
        raise NirfInputError(f"No new {category} entrants in {fmt_years(years)} ({category} starts in "
                             f"{available[0]}, and nobody counts as new in the first year).")
    counts = new.groupby(["state", "year"]).size().unstack(fill_value=0)
    counts = counts.reindex(columns=[y for y in years if y in counts.columns])
    totals = counts.sum(axis=1).sort_values(ascending=True)
    counts = counts.loc[totals.index]

    fig = go.Figure()
    if by_year:
        shades = dict(zip(counts.columns, ordinal_ramp(len(counts.columns))))
        for y in counts.columns:
            fig.add_trace(go.Bar(
                y=counts.index, x=counts[y], name=str(y), orientation="h", marker_color=shades[y],
                marker_line=dict(width=1, color=SURFACE),
                hovertemplate=f"<b>%{{y}}</b><br>{y}: %{{x}} new institutions<extra></extra>"))
        fig.add_trace(go.Scatter(
            y=totals.index, x=totals.values, mode="text", text=[f"  {v}" for v in totals.values],
            textposition="middle right", textfont=dict(color=INK_SECONDARY, size=11), showlegend=False,
            hoverinfo="skip", cliponaxis=False))
        fig.update_layout(barmode="stack", barcornerradius=0)
    else:
        split = ["<br>".join(f"{y}: {v}" for y, v in row.items() if v) for _, row in counts.iterrows()]
        examples = new.sort_values("rank_upper").groupby("state")["canonical_name"].apply(
            lambda n: ", ".join(short_name(x, 34) for x in n.head(3)) + (f" (+{len(n) - 3} more)" if len(n) > 3 else ""))
        fig.add_trace(go.Bar(
            y=totals.index, x=totals.values, orientation="h", marker_color=CATEGORICAL[0], name="New entrants",
            text=totals.values, textposition="outside", cliponaxis=False, showlegend=False,
            customdata=np.stack([split, examples.reindex(totals.index).fillna("")], axis=1),
            hovertemplate=("<b>%{y}</b><br>%{x} new institutions<br>%{customdata[0]}"
                           "<br><i>Best placed: %{customdata[1]}</i><extra></extra>")))
    fig.update_xaxes(title_text=f"New {category} entrants, {fmt_years(years)}", showgrid=True,
                     range=[0, totals.max() * 1.12])
    fig.update_yaxes(title_text="State / UT", showgrid=False)

    ranked = totals.iloc[::-1]
    total = int(ranked.sum())
    top3 = ranked.head(3)
    lead = ranked[ranked.eq(ranked.iloc[0])].index.tolist()
    title = (f"{_join(lead)} produced the most new {category} entrants ({ranked.iloc[0]}"
             f"{' each' if len(lead) > 1 else ''}, {fmt_years(years)})")
    insight = (f"Of {total} institutions that entered the {category} ranking for the first time in {fmt_years(years)}, "
               f"{_join(lead)} produced the most ({ranked.iloc[0]}{' each' if len(lead) > 1 else ''}, "
               f"{100 * ranked.iloc[0] / total:.0f}%{' each' if len(lead) > 1 else ''})")
    rest = top3[~top3.index.isin(lead)]
    insight += (", followed by " + " and ".join(f"{s} ({v})" for s, v in rest.items()) + "." if len(rest) else ".")
    per_year = new.groupby("year").size()
    busiest = int(per_year.idxmax())
    table = counts.iloc[::-1].copy()
    table.columns = [str(c) for c in table.columns]
    table["total"] = table.sum(axis=1)
    table = table.reset_index()
    how = ("bar = new institutions per state, split by year (darker = later)" if by_year else
           "bar = new institutions per state over the chosen years (hover for the split by year)")
    finish(fig, title, f"{category} ranking · {how}",
           note=f"Busiest year: {busiest} ({per_year.max()} new entrants). Years when NIRF lengthened the list "
                f"add more entrants.", height=max(380, 170 + 22 * len(totals)), legend_title="Year" if by_year else None)
    method = (f"An institution is a new entrant in the year it first appears in the {category} ranked list "
              f"(exact rank or band), provided the {category} list already existed the year before, so nobody is "
              f"'new' in {available[0]}, the category's first year. We count new entrants per state and year and "
              f"sort states by their total. "
              + ("Each bar is split by year (a stacked bar chart). " if by_year else
                 "One plain bar per state (a ranked bar chart) keeps the comparison of totals simple; the hover "
                 "text gives the split by year. ")
              + "Years in which NIRF lengthened the list (e.g. more ranks or bands published) naturally bring more "
                "new entrants.")
    return ChartResult(fig, table, insight, method, "stacked bar chart" if by_year else "bar chart")


# ---------- the map of India ----------

def _map_year(rows: pd.DataFrame, top_n: int) -> pd.DataFrame:
    """One year's numbers per state: top-N count, share, best institution, median exact rank, all ranked."""
    top = _top(rows, top_n).sort_values(["rank_upper", "canonical_name"])
    g = top.groupby("state")
    out = pd.DataFrame({
        "institutions": g.size(),
        "best_institution": g["canonical_name"].first(),
        "best_rank": g["rank_raw"].first(),
        "median_rank": g["rank"].median(),
        "exact_ranks": g["rank"].count(),
    })
    out["share_pct"] = (100 * out["institutions"] / max(len(top), 1)).round(1)
    out["ranked_in_list"] = rows.groupby("state").size().reindex(out.index)
    return out


def _map_title(t: pd.DataFrame, category: str, group: str, year: int) -> str:
    if t.empty:
        return f"No {category} institution is certainly in the {group} in {year}"
    best = int(t["institutions"].max())
    lead = t.index[t["institutions"].eq(best)].tolist()
    return (f"{_join(lead)} {'leads' if len(lead) == 1 else 'lead'} the {category} {group} in {year} with {best} "
            f"institution{'s' if best != 1 else ''}{' each' if len(lead) > 1 else ''}")


def _map_hover(state: str, row, top_n: int, ranked_any: int) -> str:
    """The hover text of one state on the map (a state with no top-N institution gets a short line)."""
    if row is None:
        extra = (f"{ranked_any} ranked in this list, none in the top {top_n}" if ranked_any else
                 "No institution ranked in this list")
        return f"<b>{state}</b><br>{extra}"
    n = int(row["institutions"])
    median = f"{row['median_rank']:g}" if pd.notna(row["median_rank"]) else "n/a (band only)"
    of = f" (of {int(row['exact_ranks'])} exact ranks)" if 0 < row["exact_ranks"] < n else ""
    return (f"<b>{state}</b><br><b>{n}</b> institution{'s' if n != 1 else ''} in the top {top_n} "
            f"({row['share_pct']:g}% of the list)<br>Best: {short_name(row['best_institution'], 44)} "
            f"(rank {row['best_rank']})<br>Median rank: {median}{of}")


def state_map(year: int | None = None, category: str = "Overall", top_n: int = 100) -> ChartResult:
    """Answers questions like: "Where in India are the top-100 institutions of 2025, and how has that map
    changed from 2017 to 2025?" (Q2.1 and Q2.2 on the map)

    Definition: for every state/UT, the number of its institutions certainly ranked within the top N of
    the chosen category and year (same rule as state_counts), plus its best institution and the median
    of its exact ranks (the middle value; band-only rows have no exact rank).
    Method: count per state for every year of the category and colour each state by its count (darker
    teal = more, grey = none). The colour scale is fixed from 0 to the highest count of ANY year, so a
    colour means the same number in every year. A year slider and a play button step through the years;
    the map opens on the chosen year, which the title and the answer describe.
    """
    df = load_master()
    category = check_category(category, df)
    years = category_years(category, df)
    year = check_year(years[-1] if year is None else year, category, df)
    if int(top_n) < 1:
        raise NirfInputError("top_n must be at least 1.")
    top_n = int(top_n)
    cat = filter_df(df, categories=category)
    per_year = {y: _map_year(cat[cat["year"].eq(y)], top_n) for y in years}
    ranked_any = cat.groupby(["year", "state"]).size()
    if per_year[year].empty:
        raise NirfInputError(f"No {category} institution has a certain rank within the top {top_n} in {year}.")

    states = sorted(state_polygons())
    shape = polygon_frame(pd.DataFrame({"state": states}))          # one row per polygon (DNH & DD has two)
    zmax = max(int(t["institutions"].max()) for t in per_year.values() if not t.empty)
    # 0 = grey ("none in the top N"); 1..zmax = the teal ramp from a mid step, so 1 is clearly not grey.
    step, ramp = 0.5 / zmax, RAMP[3:]
    scale = [[0, CONTEXT], [step, CONTEXT]] + [[step + (1 - step) * i / (len(ramp) - 1), c]
                                               for i, c in enumerate(ramp)]
    group = f"top {top_n}" if cat["rank_upper"].max() >= top_n else "ranked list"

    def frame_values(y: int) -> tuple[list[int], list[str]]:
        t = per_year[y]
        z = shape["state"].map(t["institutions"]).fillna(0).astype(int).tolist()
        text = [_map_hover(s, t.loc[s] if s in t.index else None, top_n, int(ranked_any.get((y, s), 0)))
                for s in shape["state"]]
        return z, text

    z, text = frame_values(year)
    fig = go.Figure(go.Choropleth(
        geojson=india_geojson(), featureidkey=FEATURE_KEY, locations=shape["polygon"], z=z, text=text,
        zmin=0, zmax=zmax, colorscale=scale, marker_line=dict(color=SURFACE, width=0.7),
        hovertemplate="%{text}<extra></extra>", name="Institutions",
        colorbar=dict(title=dict(text=f"Institutions<br>in the {group}", side="top",
                                 font=dict(size=12, color=INK_SECONDARY)),
                      thickness=12, len=0.6, x=0.97, xanchor="right", y=0.55, outlinewidth=0,
                      tickfont=dict(color=INK_SECONDARY, size=11), dtick=max(1, round(zmax / 6)))))
    fig.update_geos(visible=False, fitbounds="locations", projection_type="mercator", bgcolor="rgba(0,0,0,0)")
    titles = {y: _map_title(per_year[y], category, group, y) for y in years}

    if len(years) > 1:
        frames = []
        for y in years:
            fz, ftext = frame_values(y)
            frames.append(go.Frame(name=str(y), data=[go.Choropleth(z=fz, text=ftext)], traces=[0],
                                   layout=dict(title=dict(text=wrap_text(titles[y], TITLE_WRAP)[0]))))
        fig.frames = frames
        play = dict(frame=dict(duration=1100, redraw=True), transition=dict(duration=0), fromcurrent=True,
                    mode="immediate")
        jump = dict(frame=dict(duration=0, redraw=True), transition=dict(duration=0), mode="immediate")
        fig.update_layout(
            margin=dict(l=16, r=16, b=170),
            updatemenus=[dict(
                type="buttons", direction="left", x=0, y=0, xanchor="left", yanchor="top", pad=dict(t=40, r=10),
                showactive=False, bgcolor=SURFACE, bordercolor=AXIS, borderwidth=1, font=dict(color=INK, size=12),
                buttons=[dict(label="▶ Play", method="animate", args=[None, play]),
                         dict(label="❚❚ Pause", method="animate",
                              args=[[None], dict(frame=dict(duration=0, redraw=False), mode="immediate")])])],
            sliders=[dict(
                active=years.index(year), x=0.2, len=0.8, y=0, yanchor="top", pad=dict(t=26, b=0),
                bgcolor=GRID, activebgcolor=TEAL, bordercolor=AXIS, borderwidth=1, tickcolor=AXIS,
                font=dict(color=INK_SECONDARY, size=11),
                currentvalue=dict(prefix="Year ", font=dict(color=INK, size=13), xanchor="right"),
                steps=[dict(label=str(y), method="animate", args=[[str(y)], jump]) for y in years])])
    else:
        fig.update_layout(margin=dict(l=16, r=16))

    t = per_year[year]
    leaders = _leading(t["institutions"])
    lead_share = t.loc[leaders, "share_pct"].sum()
    none = sum(s not in t.index for s in states)
    insight = (f"In {year}, the {int(t['institutions'].sum())} places of the {category} {group} are spread over "
               f"{len(t)} states/UTs; " + _join([f"{s} ({int(t.at[s, 'institutions'])})" for s in leaders])
               + (f" {'holds' if len(leaders) == 1 else 'hold'} the most ({lead_share:.0f}%"
                  f"{' together' if len(leaders) > 1 else ''}), and {none} states/UTs have none."))
    if len(years) > 1:
        both = pd.concat([per_year[years[0]]["institutions"], per_year[years[-1]]["institutions"]], axis=1,
                         keys=["a", "z"]).fillna(0).astype(int)
        gain = both["z"] - both["a"]
        if gain.max() > 0:
            best = gain.index[gain.eq(gain.max())].tolist()
            insight += (f" Press play to watch {years[0]} → {years[-1]}: "
                        + (f"{best[0]} gained the most places ({both.at[best[0], 'a']} → {both.at[best[0], 'z']})."
                           if len(best) == 1 else
                           f"{_join(best[:3])}{' and others' if len(best) > 3 else ''} gained the most places "
                           f"({signed(gain.max())} each)."))

    table = pd.concat([per_year[y].assign(year=y) for y in years]).rename_axis("state").reset_index()
    table["best_institution"] = table["best_institution"].map(lambda n: short_name(n, 60))
    table["chosen_year"] = table["year"].eq(year)
    table = (table.sort_values(["chosen_year", "year", "institutions", "state"], ascending=[False, True, False, True])
             [["year", "state", "institutions", "share_pct", "best_institution", "best_rank", "median_rank",
               "ranked_in_list"]].reset_index(drop=True))
    note = _list_note(cat, top_n, [year])
    note = (f"{note} " if note else "") + ("Grey = no institution in the top list. The colour scale is fixed over "
                                           "all years. Boundaries as drawn in the open-source GeoJSON (docs/sources.md).")
    finish(fig, titles[year],
           f"{category} ranking · colour = institutions in the {group} · hover a state for its best institution and "
           f"median rank" + (f" · ▶ Play animates {fmt_years(years)}" if len(years) > 1 else ""),
           note=note, height=700)
    method = (f"For every year of the {category} ranking we keep institutions whose rank is certainly {top_n} or "
              f"better (exact rank ≤ {top_n}, or a NIRF band ending at or before {top_n}) and count them per state. "
              f"Each state is coloured by its count: grey = none, light to dark teal = few to many. The colour scale "
              f"runs from 0 to {zmax}, the highest count of any year, and stays fixed while the map plays, so the "
              f"same colour always means the same number. Hover text: the count, the state's share of the list "
              f"(count / all {group} places × 100), its best-ranked institution and the median of its exact ranks "
              f"(the middle value when sorted; band-only rows have no exact rank). State names are matched to the "
              f"map's polygons through the geo_name column of data/mappings/state_map.csv. A choropleth map shows "
              f"at a glance where the top institutions are concentrated; small UTs (Delhi, Chandigarh, Puducherry) "
              f"are tiny on a map, so the table (and the 'States with the most institutions' bar chart) gives the "
              f"same numbers as a ranked list.")
    return ChartResult(fig, table, insight, method, "choropleth map")


# ---------- state vs state ----------

def _vs_rows(states, category: str, years, top_n: int | None):
    """Checked inputs and the ranked rows of the chosen states (optionally only those in the top N)."""
    df = load_master()
    category = check_category(category, df)
    years = check_years(years, category, df)
    states = list(dict.fromkeys(check_states(states, df)))
    if len(states) < 2:
        raise NirfInputError("Please choose two different states to compare.")
    if len(states) > MAX_VS_STATES:
        raise NirfInputError(f"Please choose at most {MAX_VS_STATES} states to compare head to head.")
    sub = filter_df(df, categories=category, years=years, states=states)
    if top_n is not None:
        sub = _top(sub, top_n)
    what = f"{category} top-{top_n}" if top_n else f"{category}-ranked"
    missing = [s for s in states if s not in set(sub["state"])]
    if missing:
        raise NirfInputError(f"{_join(missing)} {'has' if len(missing) == 1 else 'have'} no {what} institution in "
                             f"{fmt_years(years)}.")
    return sub, category, years, states, what


def _vs_text(values: dict, fmt: str = "{:.1f}") -> str:
    """{'A': 1, 'B': 2} -> '1.0 vs 2.0' (in the order of the states)."""
    return " vs ".join(fmt.format(v) for v in values.values())


def state_vs_state(states=("Karnataka", "Tamil Nadu"), category: str = "Overall", years=None,
                   top_n: int | None = None) -> ChartResult:
    """Answers questions like: "Karnataka vs Tamil Nadu: which state has more ranked institutions, and whose
    institutions rank better, year by year?" (Q2.4 head to head)

    Definition: per state and year, (1) the number of its institutions in the category's ranked list
    (exact rank or band; with top_n, only those certainly within the top N) and (2) the median of their
    exact ranks (the middle rank when sorted; lower = better).
    Method: two time series one above the other on the same year axis: counts on top, median rank below
    (rank axis reversed, so up = better). The answer counts in how many years each state had more
    institutions and in how many it had the better median, and pools all years for the averages.
    """
    sub, category, years, states, what = _vs_rows(states, category, years, top_n)
    g = sub.groupby(["year", "state"])
    counts = g.size().unstack().reindex(index=years, columns=states).fillna(0).astype(int)
    medians = g["rank"].median().unstack().reindex(index=years, columns=states)
    exact_n = g["rank"].count().unstack().reindex(index=years, columns=states).fillna(0).astype(int)
    best = (sub.sort_values(["rank_upper", "canonical_name"]).groupby(["year", "state"])
            [["canonical_name", "rank_raw"]].first())

    colors = color_map(states)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.13,
                        subplot_titles=(f"How many {what} institutions each year",
                                        "Their median exact rank each year (1 = best, at the top)"))
    for s in states:
        b = [best.loc[(y, s)] if (y, s) in best.index else None for y in years]
        best_txt = [f"Best: {short_name(x['canonical_name'], 40)} (rank {x['rank_raw']})" if x is not None else
                    "No ranked institution" for x in b]
        fig.add_trace(go.Scatter(
            x=years, y=counts[s], name=s, legendgroup=s, mode="lines+markers", line=dict(color=colors[s]),
            marker=dict(color=colors[s]), customdata=best_txt,
            hovertemplate=f"<b>{s}</b> %{{x}}<br>%{{y}} {what} institutions<br>%{{customdata}}<extra></extra>"),
            row=1, col=1)
        fig.add_trace(go.Scatter(
            x=years, y=medians[s], name=s, legendgroup=s, showlegend=False, mode="lines+markers",
            line=dict(color=colors[s]), marker=dict(color=colors[s], symbol="diamond"), customdata=exact_n[s],
            hovertemplate=f"<b>{s}</b> %{{x}}<br>Median rank %{{y:g}} (of %{{customdata}} exact ranks)<extra></extra>"),
            row=2, col=1)
    fig.update_yaxes(title_text="Institutions", rangemode="tozero", row=1, col=1)
    fig.update_yaxes(title_text="Median rank", autorange="reversed", row=2, col=1)
    fig.update_xaxes(dtick=1, row=1, col=1)
    fig.update_xaxes(title_text="Year", dtick=1, row=2, col=1)
    fig.update_annotations(x=0, xanchor="left", font=dict(size=13, color=INK_SECONDARY))
    fig.update_layout(hovermode="x unified",
                      legend=dict(orientation="h", x=1, xanchor="right", y=1.0, yanchor="bottom"))

    n = len(years)
    avg = counts.mean()
    pooled = sub.groupby("state")["rank"].median().reindex(states)
    if pooled.isna().any():
        raise NirfInputError(f"{_join(pooled.index[pooled.isna()].tolist())} has no exact {category} rank in "
                             f"{fmt_years(years)} (NIRF lists only a band), so no median rank can be compared.")
    more_years = {s: int((counts[s] > counts.drop(columns=s).max(axis=1)).sum()) for s in states}
    both_med = medians.dropna()
    better_years = {s: int((both_med[s] < both_med.drop(columns=s).min(axis=1)).sum()) for s in states}
    more, better = avg.idxmax(), pooled.idxmin()
    span = fmt_years(years)
    if len(states) == 2:
        other_more = states[1] if more == states[0] else states[0]
        other_better = states[1] if better == states[0] else states[0]
        count_part = (f"{more} had more {what} institutions in {more_years[more]} of {n_years(n)} (on average "
                      f"{avg[more]:.1f} vs {avg[other_more]:.1f} a year)")
        rank_part = (f"a better (lower) median rank in {better_years[better]} of {n_years(len(both_med))} where both "
                     f"have one (pooled median {pooled[better]:g} vs {pooled[other_better]:g})")
        if more == better:
            title = f"{more} leads {other_more} on both the number and the rank of its {category} institutions"
            insight = f"Over {span}, {count_part}, and also had {rank_part}."
        else:
            title = f"{more} has more {category} institutions, but {better}'s rank better"
            insight = f"Over {span}, {count_part}, but {better}'s institutions had {rank_part}."
    else:
        title = f"{more} has the most {category} institutions; {better}'s have the best median rank"
        insight = (f"Over {span}, {more} had the most {what} institutions on average ({_vs_text(avg.to_dict())} a "
                   f"year for {', '.join(states)}), while {better} had the best pooled median rank "
                   f"({_vs_text(pooled.to_dict(), '{:g}')}).")

    table = pd.DataFrame({"institutions": counts.stack(), "median_rank": medians.stack(future_stack=True),
                          "exact_ranks": exact_n.stack()}).reset_index()
    names = best.reset_index().rename(columns={"canonical_name": "best_institution", "rank_raw": "best_rank"})
    table = table.merge(names, on=["year", "state"], how="left")
    table["best_institution"] = table["best_institution"].map(lambda x: short_name(x, 60) if pd.notna(x) else "")
    finish(fig, title, f"{category} ranking, {span} · {' vs '.join(states)}",
           note="Median of exact ranks only; band-only rows (e.g. 101-150) count in the top panel.", height=640,
           legend_title="State")
    method = (f"For each year we take the {category} institutions located in {_join(states)}"
              + (f" that are certainly in the top {top_n}" if top_n else " (exact rank or NIRF band)")
              + ". Top panel: how many there are per state. Bottom panel: the median of their exact ranks (sort "
                "the ranks, take the middle one; lower = better, so the axis is reversed). The answer counts the "
                "years in which each state had more institutions and the years in which it had the lower median, "
                "and pools all years for the averages (mean institutions per year, median of all exact ranks). "
                "Both numbers are shown because a state with many institutions naturally also has more of them "
                "further down the list. Vertically aligned time-series charts share one year axis, so the two "
                "measures can be read year by year.")
    return ChartResult(fig, table, insight, method, "vertically aligned time-series charts")


def state_rank_boxes(states=("Karnataka", "Tamil Nadu"), category: str = "Overall", years=None,
                     top_n: int | None = None) -> ChartResult:
    """Answers questions like: "How are the ranks of Karnataka's institutions spread compared with Tamil
    Nadu's?" (Q2.4 as one distribution per state)

    Definition: all exact ranks of the chosen states' institutions over the chosen years (an institution
    ranked in 5 of the years adds 5 ranks: one per institution-year).
    Method: one box per state: the line is the median, the box spans Q1 to Q3 (the middle 50%), the
    whiskers reach the furthest rank within 1.5 x IQR of the box, and every dot is one institution-year.
    Rank axis reversed (1 at the top).
    """
    sub, category, years, states, what = _vs_rows(states, category, years, top_n)
    exact = sub[sub["rank"].notna()].copy()
    missing = [s for s in states if s not in set(exact["state"])]
    if missing:
        raise NirfInputError(f"{_join(missing)} has no exact {category} rank in {fmt_years(years)} (only bands).")
    exact["rank"] = exact["rank"].astype(float)

    colors = color_map(states)
    fig = go.Figure()
    for s in states:
        t = exact[exact["state"].eq(s)]
        fig.add_trace(go.Box(
            y=t["rank"], name=s, marker_color=colors[s], line_color=colors[s], fillcolor=tint(colors[s], 0.14),
            boxpoints="all", jitter=0.55, pointpos=0, quartilemethod="linear",
            customdata=np.stack([t["canonical_name"].map(lambda x: short_name(x, 44)), t["year"], t["rank_raw"]], axis=1),
            hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}: rank %{customdata[2]}<extra>" + s + "</extra>"))
    fig.update_yaxes(title_text="Exact rank (1 = best, at the top)", autorange="reversed")
    fig.update_xaxes(title_text="State")

    g = exact.groupby("state")["rank"]
    table = pd.DataFrame({
        "institution_years": g.size(), "institutions": exact.groupby("state")["institution_key"].nunique(),
        "median_rank": g.median(), "q1": g.quantile(0.25), "q3": g.quantile(0.75),
        "best_rank": g.min().astype(int), "worst_rank": g.max().astype(int),
    }).reindex(states)
    table["iqr"] = table["q3"] - table["q1"]
    best_row = exact.sort_values("rank").groupby("state").first()
    table["best_institution"] = best_row["canonical_name"].map(lambda x: short_name(x, 60)).reindex(states)
    table = table.round(1).rename_axis("state").reset_index()

    t = table.set_index("state")
    better = t["median_rank"].idxmin()
    span = fmt_years(years)
    desc = {s: f"{t.at[s, 'median_rank']:g} (middle half {t.at[s, 'q1']:g}–{t.at[s, 'q3']:g})" for s in states}
    if len(states) == 2:
        other = states[1] if better == states[0] else states[0]
        title = f"{better}'s {category} institutions rank higher than {other}'s (median {t.at[better, 'median_rank']:g} " \
                f"vs {t.at[other, 'median_rank']:g})"
        insight = (f"Over {span}, {better}'s {what} institutions sit higher on the list: median rank {desc[better]} vs "
                   f"{desc[other]} for {other}. {_more_text(t, states)}")
    else:
        title = f"{better}'s {category} institutions have the best median rank ({t.at[better, 'median_rank']:g})"
        insight = (f"Over {span}, median ranks (middle half): " + "; ".join(f"{s} {desc[s]}" for s in states)
                   + f". {_more_text(t, states)}")
    finish(fig, title, f"{category} ranking, {span} · all chosen years pooled · box = middle 50% of ranks, "
           f"dot = one institution in one year", note="Exact ranks only; institutions NIRF lists only in a band "
           "(e.g. 101-150) are not drawn.", height=560, legend_title="State")
    fig.update_layout(showlegend=False)
    method = (f"We collect every exact {category} rank of institutions located in {_join(states)} over {span}"
              + (f", keeping only ranks within the top {top_n}" if top_n else "")
              + ". An institution ranked in several years adds one rank per year (institution-years). For each "
                "state the box plot shows the median (middle rank), Q1 and Q3 (the box: the middle 50% of ranks), "
                "whiskers to the furthest rank within 1.5 × IQR of the box, and every rank as a dot. Lower = better, "
                "so the axis is reversed. Comparing medians and boxes shows whose institutions sit higher on the "
                "list; the count of dots shows who has more of them. Band-only rows have no exact rank and are left "
                "out.")
    return ChartResult(fig, table, insight, method, "box-and-whisker plot")


def _more_text(t: pd.DataFrame, states: list[str]) -> str:
    """'Tamil Nadu has more exact ranks (171 vs 58 institution-years from 28 vs 15 institutions).'

    The state with the most comes first, so the numbers read in the same order as the sentence.
    """
    most = t["institution_years"].idxmax()
    order = [most] + [s for s in states if s != most]
    years_ = " vs ".join(str(int(t.at[s, "institution_years"])) for s in order)
    insts = " vs ".join(str(int(t.at[s, "institutions"])) for s in order)
    return (f"{most} has {'more' if len(states) == 2 else 'the most'} exact ranks ({years_} institution-years from "
            f"{insts} institutions).")
