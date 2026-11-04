"""Mobility engine: how institutions move between ranks and bands (Annexure A section 7, Q7.1-Q7.5).

Functions
  band_transitions()      how many institutions moved from each band in year A to each band in year B
                          (matrix heatmap read like a confusion matrix: diagonal = stayed in the same band)
  top10_entries_exits()   who entered or left the top 10 each year (table + time-series dot plot)
  band_retention()        % of institutions staying in the same band from one year to the next (line chart
                          with markers; by_band=True: one line per band)
  biggest_rank_moves()    largest climbs and falls between two years (lollipop chart, up and down coloured)
  up_down_same_counts()   how many moved up, down or kept their rank each year (stacked bar chart)

Every chart type is one of the types listed in docs/allowed_charts.md.

Mobility bands (used everywhere here): 1-10, 11-50, 51-100, 101+ and "Not ranked". A row belongs to a
band when its rank is certainly inside it: the exact rank, or NIRF's own band (a 51-75 or 76-100
row is in 51-100, a 101-150 row is in 101+). Institutions that NIRF lists only by band can therefore
be followed here too. Rank changes in places (up/down/same, biggest moves) need exact ranks.
Improvement = old rank - new rank (positive = moved up).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from core.data import (NirfInputError, category_years, chart_labels, check_category, check_year, filter_df,
                       fmt_years, load_master)
from core.engines import trends
from core.result import ChartResult
from core.stats import places
from core.theme import (CATEGORICAL, DOWN, INK, INK_SECONDARY, NEUTRAL, SEQUENTIAL, SURFACE, UP, add_lollipops,
                        finish, ordinal_ramp)

BANDS = ["1-10", "11-50", "51-100", "101+"]
NOT_RANKED = "Not ranked"


def _mobility_band(rank_upper: pd.Series) -> pd.Series:
    """1-10 / 11-50 / 51-100 / 101+ from the worst rank a row can have (exact rank or end of NIRF's band).

    Every NIRF band (51-75, 76-100, 101-150 ...) lies wholly inside one of these four, so the band is
    never a guess. Rows without any rank (rank withdrawn) get "Not ranked".
    """
    r = pd.to_numeric(rank_upper, errors="coerce")
    out = pd.Series(NOT_RANKED, index=r.index, dtype="object")
    out[r.le(10)] = "1-10"
    out[r.gt(10) & r.le(50)] = "11-50"
    out[r.gt(50) & r.le(100)] = "51-100"
    out[r.gt(100)] = "101+"
    return out


def _category_and_years(category: str, year_a, year_b) -> tuple[pd.DataFrame, str, int, int]:
    df = load_master()
    category = check_category(category, df)
    available = category_years(category, df)
    year_a = check_year(available[0] if year_a is None else year_a, category, df)
    year_b = check_year(available[-1] if year_b is None else year_b, category, df)
    if year_a >= year_b:
        raise NirfInputError(f"Year A ({year_a}) must be before year B ({year_b}).")
    return filter_df(df, categories=category), category, year_a, year_b


def _bands_by_year(cat: pd.DataFrame) -> pd.DataFrame:
    """institution_key x year table of mobility bands (missing = not in that year's list)."""
    t = cat.assign(band=_mobility_band(cat["rank_upper"]))
    return t.pivot(index="institution_key", columns="year", values="band")


def _consecutive_pairs(years: list[int]) -> list[tuple[int, int]]:
    """(previous, next) pairs of years in which the category was published (a gap year is skipped over)."""
    return list(zip(years[:-1], years[1:]))


def band_transitions(category: str = "Overall", year_a: int | None = None, year_b: int | None = None) -> ChartResult:
    """Answers questions like: "How many institutions moved from the 51-100 band into the top 50 between two
    selected years?" (Q7.1)

    Definition: each institution in the category list of year A or year B gets a band in both years:
    1-10, 11-50, 51-100, 101+ or "Not ranked" (absent from that year's list).
    Method: count institutions for every (band in A, band in B) pair and draw the counts as a matrix
    heatmap: rows = band in year A, columns = band in year B. It reads like a confusion matrix: the
    diagonal = stayed in the same band, cells right of it = moved down, left of it = moved up. The
    51-100 -> 1-10 and 51-100 -> 11-50 cells (outlined) answer "moved from 51-100 into the top 50".
    Defaults: the first and last year of the category.
    """
    cat, category, year_a, year_b = _category_and_years(category, year_a, year_b)
    bands = _bands_by_year(cat[cat["year"].isin([year_a, year_b])])
    bands = bands.reindex(columns=[year_a, year_b]).fillna(NOT_RANKED)
    order = BANDS + [NOT_RANKED]
    matrix = pd.crosstab(bands[year_a], bands[year_b]).reindex(index=order, columns=order, fill_value=0)

    names = chart_labels(bands.index)
    members = {(a, b): sorted(names[k] for k in g.index) for (a, b), g in bands.groupby([year_a, year_b])}
    z, text, hover = [], [], []
    for a in order:
        zr, tr, hr = [], [], []
        for b in order:
            n = int(matrix.at[a, b])
            if a == NOT_RANKED and b == NOT_RANKED:
                zr.append(None)
                tr.append("")
                hr.append("not applicable: only institutions ranked in at least one of the two years are counted")
                continue
            who = members.get((a, b), [])
            listing = "<br>".join(who[:12]) + (f"<br>… and {len(who) - 12} more" if len(who) > 12 else "")
            zr.append(n)
            tr.append(str(n) if n else "")
            hr.append(f"{n} institution{'s' if n != 1 else ''}" + (f"<br>{listing}" if n else ""))
        z.append(zr)
        text.append(tr)
        hover.append(hr)
    ylab = [f"{a}" for a in order]
    xlab = [f"{b}" for b in order]
    fig = go.Figure(go.Heatmap(
        z=z, x=xlab, y=ylab, text=text, texttemplate="%{text}", customdata=hover, colorscale=SEQUENTIAL,
        zmin=0, colorbar=dict(title=dict(text="Institutions")), textfont=dict(size=13),
        hovertemplate=f"<b>{year_a}: %{{y}} → {year_b}: %{{x}}</b><br>%{{customdata}}<extra></extra>"))
    # Outline the diagonal (stayed) and the Q7.1 cells (51-100 in A -> top 50 in B).
    for i, band in enumerate(BANDS):
        fig.add_shape(type="rect", x0=i - 0.5, x1=i + 0.5, y0=i - 0.5, y1=i + 0.5, line=dict(color=INK_SECONDARY,
                      width=1, dash="dot"))
    fig.add_shape(type="rect", x0=-0.5, x1=1.5, y0=1.5, y1=2.5, line=dict(color=CATEGORICAL[1], width=3))
    fig.update_yaxes(title_text=f"Band in {year_a}", autorange="reversed", showgrid=False, type="category")
    fig.update_xaxes(title_text=f"Band in {year_b}", side="top", showgrid=False, type="category")

    into_top50 = int(matrix.loc["51-100", ["1-10", "11-50"]].sum())
    into_top10 = int(matrix.at["51-100", "1-10"])
    movers = members.get(("51-100", "11-50"), []) + members.get(("51-100", "1-10"), [])
    ranked_both = matrix.loc[BANDS, BANDS]
    stayed = int(np.trace(ranked_both.values))
    total_both = int(ranked_both.values.sum())
    up = int(sum(ranked_both.iat[i, j] for i in range(4) for j in range(4) if j < i))
    down = int(sum(ranked_both.iat[i, j] for i in range(4) for j in range(4) if j > i))
    title = (f"{into_top50} {category} institution{'s' if into_top50 != 1 else ''} moved from the 51-100 band into the "
             f"top 50 between {year_a} and {year_b}")
    insight = (f"Between {year_a} and {year_b}, {into_top50} {category} institutions moved from the 51-100 band into the "
               f"top 50" + (f" ({into_top10} straight into the top 10)" if into_top10 else "")
               + (f": {', '.join(movers[:6])}" + (f" and {len(movers) - 6} more" if len(movers) > 6 else "") if movers else "")
               + f". Of the {total_both} institutions ranked in both years, {stayed} ({100 * stayed / total_both:.0f}%) "
               f"stayed in the same band, {up} moved to a better band and {down} to a worse one; "
               f"{int(matrix.loc[BANDS, NOT_RANKED].sum())} dropped out of the list and "
               f"{int(matrix.loc[NOT_RANKED, BANDS].sum())} were newly listed.")
    fig.update_layout(margin=dict(t=150))
    finish(fig, title, f"{category} ranking · rows = band in {year_a}, columns = band in {year_b} · dotted diagonal = "
           f"stayed · orange box = 51-100 → top 50", height=580)
    method = (f"Every institution in the {category} list of {year_a} or {year_b} gets a band in each year: 1-10, 11-50, "
              f"51-100, 101+ (from its exact rank or from NIRF's own band, e.g. 76-100 is inside 51-100) or 'Not "
              f"ranked' if it is not in that year's list. We count how many institutions fall in each (band in "
              f"{year_a}, band in {year_b}) pair, like a confusion matrix: the diagonal = stayed in the same band, left "
              f"of the diagonal = moved to a better band, right = moved to a worse band. 'Moved into the top 50' = "
              f"band 51-100 in {year_a} and band 1-10 or 11-50 in {year_b}. Hover a cell for the names.")
    table = matrix.copy()
    table.index = [f"{year_a}: {b}" for b in order]
    table.columns = [f"{year_b}: {b}" for b in order]
    table.iat[-1, -1] = 0
    table["total"] = table.sum(axis=1)
    table = table.rename_axis("band").reset_index()
    detail = bands.rename(columns={year_a: f"band_{year_a}", year_b: f"band_{year_b}"})
    detail.insert(0, "institution", detail.index.map(names))
    table.attrs["institutions"] = detail.reset_index(drop=True)
    return ChartResult(fig, table, insight, method, "matrix heatmap")


def top10_entries_exits(category: str = "Overall", top: int = 10) -> ChartResult:
    """Answers questions like: "Which institutions entered or exited the top 10 between consecutive years?" (Q7.2)

    Definition: "in the top 10" = rank certainly 10 or better. Entered in year Y = in the top 10 in Y
    but not in the previous published year; exited in Y = in the top 10 the previous year but not in Y.
    Method: a time-series dot plot with one row per institution that was ever in the top 10 and a
    dot in every year it was there; a teal triangle marks the year it entered and a coral cross the
    year it was no longer there. The table lists every entry and exit with the ranks before and after.
    """
    df = load_master()
    category = check_category(category, df)
    years = category_years(category, df)
    top = int(top)
    if top < 1:
        raise NirfInputError("top must be at least 1.")
    if len(years) < 2:
        raise NirfInputError(f"{category} has a ranking in only one year ({years[0]}), so nothing can enter or exit.")
    cat = filter_df(df, categories=category)
    cat["in_top"] = cat["rank_upper"].le(top).fillna(False).astype(bool)
    in_top = cat[cat["in_top"]].pivot_table(index="institution_key", columns="year", values="in_top",
                                            aggfunc="any").reindex(columns=years).fillna(False).astype(bool)
    rank_of = cat.pivot(index="institution_key", columns="year", values="rank_raw")
    labels = chart_labels(in_top.index)

    events = []
    for y0, y1 in _consecutive_pairs(years):
        for k in in_top.index:
            was, now = in_top.at[k, y0], in_top.at[k, y1]
            if was != now:
                events.append(dict(year=y1, change="entered" if now else "exited", institution=labels[k],
                                   rank_before=rank_of.at[k, y0] if (k in rank_of.index and pd.notna(rank_of.at[k, y0]))
                                   else "not ranked",
                                   rank_after=rank_of.at[k, y1] if (k in rank_of.index and pd.notna(rank_of.at[k, y1]))
                                   else "not ranked", key=k))
    ev = pd.DataFrame(events, columns=["year", "change", "institution", "rank_before", "rank_after", "key"])

    count = in_top.sum(axis=1)
    first = in_top.idxmax(axis=1)
    order = sorted(in_top.index, key=lambda k: (-count[k], first[k], labels[k]))
    ylab = {k: labels[k] for k in order}
    fig = go.Figure()
    xs, ys, hv = [], [], []
    for k in order:
        for y in years:
            if in_top.at[k, y]:
                xs.append(y)
                ys.append(ylab[k])
                hv.append(f"rank {rank_of.at[k, y]}")
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="markers", name=f"In the top {top}", customdata=hv,
                             marker=dict(color=CATEGORICAL[0], size=11, opacity=0.35),
                             hovertemplate="<b>%{y}</b><br>%{x}: %{customdata}<extra></extra>"))
    for change, name, symbol, color in (("entered", f"Entered the top {top}", "triangle-up", UP),
                                        ("exited", f"Left the top {top} (first year outside)", "x", DOWN)):
        e = ev[ev["change"].eq(change)]
        if len(e):
            fig.add_trace(go.Scatter(
                x=e["year"], y=e["key"].map(ylab), mode="markers", name=name,
                marker=dict(symbol=symbol, color=color, size=13, line=dict(width=1.5, color=color if symbol == "x" else SURFACE)),
                customdata=np.stack([e["rank_before"].astype(str), e["rank_after"].astype(str)], axis=1),
                hovertemplate=(f"<b>%{{y}}</b><br>%{{x}}: {change} (rank %{{customdata[0]}} → %{{customdata[1]}})"
                               "<extra></extra>")))
    fig.update_yaxes(title_text="Institution", autorange="reversed", showgrid=True, type="category",
                     categoryorder="array", categoryarray=[ylab[k] for k in order])
    fig.update_xaxes(title_text="Year", dtick=1, range=[years[0] - 0.5, years[-1] + 0.5], showgrid=True)
    fig.update_layout(legend=dict(orientation="h", x=0, y=1.0, yanchor="bottom"))

    always = [labels[k] for k in order if count[k] == len(years)]
    changes_years = ev.groupby("year").size()
    last_year = years[-1]
    last = ev[ev["year"].eq(last_year)]
    n_in = int(ev["change"].eq("entered").sum())
    n_out = int(ev["change"].eq("exited").sum())
    title = (f"{len(order)} different institutions were in the {category} top {top} in {fmt_years(years)}; "
             f"{len(always)} were there every year")
    insight = (f"Across {fmt_years(years)}, {len(order)} different institutions were in the {category} top {top}; "
               f"there were {n_in} entries and {n_out} exits, in {len(changes_years)} of {len(years) - 1} year-to-year "
               f"changes. {len(always)} institutions were in the top {top} every year.")
    if len(last):
        ins = last[last["change"].eq("entered")]["institution"].tolist()
        outs = last[last["change"].eq("exited")]["institution"].tolist()
        insight += (f" In {last_year}: " + (f"{', '.join(ins)} entered" if ins else "nobody entered")
                    + (f"; {', '.join(outs)} left." if outs else "; nobody left."))
    else:
        insight += f" The top {top} of {last_year} is the same group as in {years[-2]}."
    finish(fig, title, f"{category} ranking, {fmt_years(years)} · one row per institution · dot = in the top {top} "
           f"that year", height=max(420, 200 + 30 * len(order)), legend_title="Status")
    method = (f"For every year we mark which institutions are certainly in the {category} top {top} (exact rank ≤ {top}, "
              f"or a whole NIRF band within it). Comparing each year with the previous published year: entered = in "
              f"the top {top} now but not before; exited = in the top {top} before but not now. Each row of the dot "
              f"plot is one institution; a faint dot means 'in the top {top} that year', a triangle marks an entry and "
              f"a cross the first year outside. The table lists every entry and exit with the rank before and after.")
    table = ev.drop(columns="key").sort_values(["year", "change", "institution"]).reset_index(drop=True)
    if table.empty:
        table = pd.DataFrame({"year": [None], "change": ["none"], "institution": [f"the top {top} never changed"],
                              "rank_before": [None], "rank_after": [None]})
    return ChartResult(fig, table, insight, method, "time-series dot plot")


def band_retention(category: str = "Overall", by_band: bool = False) -> ChartResult:
    """Answers questions like: "What percentage of institutions remained in the same rank band from one year
    to the next?" (Q7.3)

    Definition: retention from year Y-1 to Y = institutions in the same mobility band (1-10, 11-50,
    51-100, 101+) in both years / institutions ranked in both years x 100. Institutions that enter or
    leave the list are counted separately (in the table), not as "changed band".
    Method: compute the retention for every pair of consecutive published years and draw a line
    chart with markers (by_band=True: one line per band, i.e. the share of each band's institutions
    that were still in that band a year later).
    """
    df = load_master()
    category = check_category(category, df)
    years = category_years(category, df)
    if len(years) < 2:
        raise NirfInputError(f"{category} has a ranking in only one year ({years[0]}), so there is no year-to-year change.")
    bands = _bands_by_year(filter_df(df, categories=category))
    rows = []
    for y0, y1 in _consecutive_pairs(years):
        a, b = bands[y0], bands[y1]
        both = a.notna() & b.notna() & a.ne(NOT_RANKED) & b.ne(NOT_RANKED)
        same = both & a.eq(b)
        row = dict(year_from=y0, year_to=y1, ranked_both=int(both.sum()), stayed=int(same.sum()),
                   retention_pct=round(100 * same.sum() / both.sum(), 1) if both.sum() else np.nan,
                   left_list=int((a.notna() & b.isna()).sum()), joined_list=int((a.isna() & b.notna()).sum()))
        for band in BANDS:
            base = both & a.eq(band)
            row[f"{band}_pct"] = round(100 * (base & b.eq(band)).sum() / base.sum(), 1) if base.sum() else np.nan
        rows.append(row)
    table = pd.DataFrame(rows)
    table["pair"] = table["year_from"].astype(str) + "→" + table["year_to"].astype(str)

    fig = go.Figure()
    hover = np.stack([table["pair"], table["stayed"], table["ranked_both"]] + [table[f"{b}_pct"] for b in BANDS], axis=1)
    band_hover = "".join(f"<br>{b}: %{{customdata[{i + 3}]}}%" for i, b in enumerate(BANDS))
    if by_band:
        colors = dict(zip(BANDS, ordinal_ramp(len(BANDS))[::-1]))
        for i, b in enumerate(BANDS):
            fig.add_trace(go.Scatter(
                x=table["year_to"], y=table[f"{b}_pct"], mode="lines+markers", name=b,
                line=dict(color=colors[b]), marker=dict(color=colors[b]), customdata=hover,
                hovertemplate=f"<b>{b}</b> %{{customdata[0]}}<br>%{{y:.1f}}% stayed in {b}<extra></extra>"))
    else:
        fig.add_trace(go.Scatter(
            x=table["year_to"], y=table["retention_pct"], mode="lines+markers", name="All bands",
            line=dict(color=CATEGORICAL[0]), marker=dict(color=CATEGORICAL[0]), customdata=hover,
            hovertemplate=("<b>%{customdata[0]}</b><br>%{y:.1f}% stayed in the same band (%{customdata[1]} of "
                           "%{customdata[2]})<br>By band:" + band_hover + "<extra></extra>")))
    fig.update_yaxes(title_text="Stayed in the same band (%)", range=[0, 105], ticksuffix="%")
    fig.update_xaxes(title_text="Year (compared with the previous published year)", dtick=1)

    avg = table["retention_pct"].mean()
    hi = table.loc[table["retention_pct"].idxmax()]
    lo = table.loc[table["retention_pct"].idxmin()]
    sticky = {b: table[f"{b}_pct"].mean() for b in BANDS}
    title = (f"On average {avg:.0f}% of {category} institutions stay in the same band from one year to the next")
    insight = (f"In {category}, on average {avg:.0f}% of the institutions ranked in two consecutive years stayed in the "
               f"same band (1-10, 11-50, 51-100, 101+); retention was highest for {hi['pair']} ({hi['retention_pct']:.0f}%) "
               f"and lowest for {lo['pair']} ({lo['retention_pct']:.0f}%). The top 10 is the most stable band "
               f"({sticky['1-10']:.0f}% stay on average) and 51-100 the least ({sticky['51-100']:.0f}%)."
               if max(sticky, key=sticky.get) == "1-10" and min(sticky, key=sticky.get) == "51-100" else
               f"In {category}, on average {avg:.0f}% of the institutions ranked in two consecutive years stayed in the "
               f"same band; retention was highest for {hi['pair']} ({hi['retention_pct']:.0f}%) and lowest for "
               f"{lo['pair']} ({lo['retention_pct']:.0f}%). Most stable band: {max(sticky, key=sticky.get)} "
               f"({max(sticky.values()):.0f}%), least stable: {min(sticky, key=sticky.get)} ({min(sticky.values()):.0f}%).")
    finish(fig, title, f"{category} ranking, {fmt_years(years)} · bands 1-10, 11-50, 51-100, 101+ · institutions "
           f"ranked in both years", legend_title="Band in the earlier year" if by_band else None,
           note="Wide bands keep institutions more easily than narrow ones (a 10-place band vs a 40-place band).")
    if not by_band:
        fig.update_layout(showlegend=False)
    method = (f"Each {category} institution gets a band every year (1-10, 11-50, 51-100, 101+; from its exact rank or "
              f"NIRF's own band). For each pair of consecutive published years we take the institutions ranked in both "
              f"years and compute retention = number in the same band in both years / number ranked in both years × 100. "
              f"Institutions that join or leave the list are counted in the table (joined_list, left_list) but not in "
              f"the percentage. by_band=True draws the same share separately for each starting band.")
    return ChartResult(fig, table, insight, method, "multi-series line chart" if by_band else "line chart")


def biggest_rank_moves(category: str = "Overall", year_a: int | None = None, year_b: int | None = None,
                       n: int = 10) -> ChartResult:
    """Answers questions like: "Which institutions experienced the largest upward and downward rank
    movements?" (Q7.4)

    Definition: improvement = rank in year A - rank in year B (positive = moved up).
    Method: the same calculation as trends.biggest_movers (institutions with an exact rank in both
    years; the n largest climbs and the n largest falls), drawn as a lollipop chart: a stem from
    zero to the change and a dot at its end, teal for climbs (right of zero) and coral for falls (left).
    Defaults: the first and last year of the category.
    """
    df = load_master()
    category = check_category(category, df)
    available = category_years(category, df)
    year_a = available[0] if year_a is None else year_a
    year_b = available[-1] if year_b is None else year_b
    base = trends.biggest_movers(category, year_a, year_b, direction="both", n=n)
    t = base.table.sort_values("improvement")           # falls at the bottom, climbs at the top
    year_a, year_b = int(year_a), int(year_b)

    fig = go.Figure()
    add_lollipops(
        fig, t["improvement"], t["institution"], [UP if v > 0 else DOWN for v in t["improvement"]],
        text=[f"{int(s)} → {int(e)}" for s, e in zip(t["rank_start"], t["rank_end"])],
        customdata=np.stack([t["full_name"], t["state"], t["rank_start"].astype(int), t["rank_end"].astype(int)], axis=1),
        hovertemplate=(f"<b>%{{customdata[0]}}</b> (%{{customdata[1]}})<br>{year_a}: rank %{{customdata[2]}}"
                       f"<br>{year_b}: rank %{{customdata[3]}}<br>Change: %{{x:+d}} places<extra></extra>"))
    # Labels to the left of the falls' dots so they do not run over the stems.
    fig.data[-1].textposition = ["middle right" if v > 0 else "middle left" for v in t["improvement"]]
    for name, c in (("Moved up", UP), ("Moved down", DOWN)):
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", name=name, marker=dict(color=c, size=11)))
    lo, hi = min(0, t["improvement"].min()), max(0, t["improvement"].max())
    pad = 0.22 * (hi - lo)
    fig.update_xaxes(title_text=f"Change in places ({year_a} rank − {year_b} rank)", showgrid=True, zeroline=True,
                     zerolinecolor=INK_SECONDARY, zerolinewidth=1, range=[lo - (pad if lo < 0 else 0), hi + pad])
    fig.update_yaxes(title_text="Institution", showgrid=False, type="category", categoryorder="array",
                     categoryarray=t["institution"].tolist())
    fig.update_layout(legend=dict(orientation="h", x=0, y=1.0, yanchor="bottom"))

    ups, downs = t[t["improvement"] > 0], t[t["improvement"] < 0]
    up, down = (ups.iloc[-1] if len(ups) else None), (downs.iloc[0] if len(downs) else None)
    parts = []
    if up is not None:
        parts.append(f"{up['full_name']} climbed the most ({int(up['rank_start'])} → {int(up['rank_end'])}, "
                     f"{places(up['improvement'])})")
    if down is not None:
        parts.append(f"{down['full_name']} fell the most ({int(down['rank_start'])} → {int(down['rank_end'])}, "
                     f"{places(down['improvement'])})")
    title = (f"Biggest {category} moves {year_a}→{year_b}: "
             + (f"{up['institution']} {places(up['improvement'])}" if up is not None else "")
             + (" · " if up is not None and down is not None else "")
             + (f"{down['institution']} {places(down['improvement'])}" if down is not None else ""))
    insight = f"Between {year_a} and {year_b} in {category}, " + " and ".join(parts) + "." + base.insight.split(".", 2)[-1]
    finish(fig, title, f"{category} ranking · the {len(ups)} largest climbs and {len(downs)} largest falls · labels "
           f"show rank {year_a} → {year_b}", height=max(420, 170 + 28 * len(t)), legend_title="Direction")
    method = base.method + (" Drawn as a lollipop chart (a bar chart with a thin stem and a dot), teal to the right of "
                            "zero for climbs and coral to the left for falls.")
    return ChartResult(fig, base.table, insight, method, "lollipop chart")


def up_down_same_counts(category: str = "Overall") -> ChartResult:
    """Answers questions like: "How many institutions moved up, moved down, or retained their positions each
    year?" (Q7.5)

    Definition: for each pair of consecutive published years, among institutions with an exact rank
    in both: moved up = new rank smaller than old (improvement = old - new > 0), moved down = new rank
    larger, same = identical rank.
    Method: count the three groups per year and draw a stacked bar chart (one bar per year, split
    into up / same / down). Institutions known only by band in either year cannot be placed exactly,
    so they are counted in the table as "not comparable".
    """
    df = load_master()
    category = check_category(category, df)
    years = category_years(category, df)
    if len(years) < 2:
        raise NirfInputError(f"{category} has a ranking in only one year ({years[0]}), so there is no year-to-year change.")
    cat = filter_df(df, categories=category)
    ranks = cat.pivot(index="institution_key", columns="year", values="rank")
    listed = cat.pivot(index="institution_key", columns="year", values="rank_raw").notna()
    rows = []
    for y0, y1 in _consecutive_pairs(years):
        a, b = ranks[y0], ranks[y1]
        both = a.notna() & b.notna()
        imp = (a - b)[both]
        in_both_lists = listed[y0] & listed[y1]
        rows.append(dict(year_from=y0, year_to=y1, moved_up=int((imp > 0).sum()), same=int((imp == 0).sum()),
                         moved_down=int((imp < 0).sum()), compared=int(both.sum()),
                         not_comparable=int((in_both_lists & ~both).sum()),
                         median_move=float(imp.abs().median()) if both.any() else np.nan))
    table = pd.DataFrame(rows)
    table["pair"] = table["year_from"].astype(str) + "→" + table["year_to"].astype(str)
    for c in ("moved_up", "same", "moved_down"):
        table[f"{c}_pct"] = (100 * table[c] / table["compared"]).round(1)

    fig = go.Figure()
    for col, name, color in (("moved_up", "Moved up", UP), ("same", "Same rank", NEUTRAL),
                             ("moved_down", "Moved down", DOWN)):
        fig.add_trace(go.Bar(
            x=table["pair"], y=table[col], name=name, marker_color=color,
            text=table[col], textposition="inside", insidetextanchor="middle",
            textfont=dict(color="white" if color != NEUTRAL else INK, size=11),
            customdata=np.stack([table[f"{col}_pct"], table["compared"]], axis=1),
            hovertemplate=(f"<b>%{{x}}</b><br>{name}: %{{y}} (%{{customdata[0]}}% of %{{customdata[1]}} compared)"
                           "<extra></extra>")))
    fig.update_layout(barmode="stack", legend=dict(orientation="h", x=0, y=1.0, yanchor="bottom"))
    fig.update_yaxes(title_text="Institutions with an exact rank in both years")
    fig.update_xaxes(title_text="Year pair (previous → next published year)")

    tot = table[["moved_up", "same", "moved_down"]].sum()
    most_up = table.loc[table["moved_up_pct"].idxmax()]
    balance = (tot["moved_up"] - tot["moved_down"]) / max(tot["moved_up"] + tot["moved_down"], 1)
    lead = ("about as many move up as down" if abs(balance) < 0.1 else
            "more move up than down" if balance > 0 else "more move down than up")
    title = (f"Year to year, {lead} among {category} institutions; only "
             f"{100 * tot['same'] / tot.sum():.0f}% keep the exact same rank")
    insight = (f"Across {len(table)} year-to-year changes in {category} ({fmt_years(years)}), {int(tot['moved_up'])} moves "
               f"were up, {int(tot['moved_down'])} down and {int(tot['same'])} kept the same rank "
               f"({100 * tot['same'] / tot.sum():.0f}%). The largest share moving up was in {most_up['pair']} "
               f"({most_up['moved_up_pct']:.0f}% of {int(most_up['compared'])}); the typical move is "
               f"{table['median_move'].median():.0f} places.")
    finish(fig, title, f"{category} ranking · institutions with an exact rank in both years · improvement = old rank − "
           f"new rank", legend_title="Rank change")
    method = (f"For each pair of consecutive published {category} years we take the institutions with an exact rank in "
              f"both years and compute improvement = old rank − new rank: positive = moved up, negative = moved down, "
              f"0 = same rank. We count each group and stack the three counts in one bar per year pair. Institutions "
              f"listed only by band in either year (e.g. 101-150) cannot be placed exactly; they are counted in the table "
              f"as not_comparable. Newcomers and drop-outs are not part of the comparison. Up and down counts tend to "
              f"balance: when one institution climbs past another, the other moves down (newcomers and leavers can "
              f"tip the balance).")
    return ChartResult(fig, table, insight, method, "stacked bar chart")
