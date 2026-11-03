"""Outliers engine: unusual institutions and performance gaps (Annexure A section 8, Q8.1-Q8.5).

Functions
  research_vs_overall_outliers()  research far above what the overall score predicts (scatterplot with the
                                  least-squares line; residual z-score > 2 highlighted and labelled)
  research_over_teaching()        RPC minus TLR per institution (ranked horizontal bar chart)
  unusual_score_jumps()           year-to-year score changes, |z| > 2 labelled (jittered strip chart over a
                                  box plot per year pair)
  strong_param_poor_rank()        top-quartile parameter but bottom-half rank (scatterplot of parameter vs rank)
  volatility_vs_peers()           rank standard deviation compared within peer bands (box-and-whisker plot
                                  per band with a jittered strip; 1.5 x IQR outliers labelled)

Every chart type is one of the types listed in docs/allowed_charts.md.

"Unusual" always has a stated, explainable rule: a z-score beyond +/-2 (more than two standard
deviations from the average, about 5% of values if they were normally distributed) or the box-plot
rule (more than 1.5 x IQR beyond the box). Outliers are a reason to look closer, not proof of error.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from core.data import (BAND_ORDER, LABELS, SHORT, NirfInputError, category_year, category_years, chart_labels,
                       check_category, check_column, filter_df, fmt_years, load_master)
from core.result import ChartResult
from core.stats import correlate, signed
from core.theme import (CATEGORICAL, DOWN, INK_SECONDARY, OTHER, UP, finish, jitter, label_points, padded_range,
                        tint)

HIGHLIGHT = CATEGORICAL[1]


def _two_columns(rows: pd.DataFrame, category: str, a: str, b: str) -> pd.DataFrame:
    d = rows.dropna(subset=[a, b]).copy()
    if len(d) < 5:
        raise NirfInputError(f"Only {len(d)} {category} institutions have both {SHORT[a]} and {SHORT[b]}; at least 5 "
                             f"are needed.")
    d[a], d[b] = d[a].astype(float), d[b].astype(float)
    return d


def research_vs_overall_outliers(year: int | None = None, category: str = "Overall", param: str = "rpc",
                                 z_threshold: float = 2.0) -> ChartResult:
    """Answers questions like: "Which institutions have unusually high research scores relative to their
    overall scores?" (Q8.1)

    Definition: the expected research score of an institution is read off the least-squares line
    of RPC on the overall score (fitted over all institutions of the category-year). Residual =
    actual RPC - expected RPC. Residual z-score = residual / SD of all residuals. "Unusually high"
    = residual z-score > z_threshold (default 2: more than two standard deviations above the line).
    Method: scatterplot of overall score (x) vs RPC (y) with the line; institutions above the
    threshold are highlighted and labelled. param can be any parameter (default RPC).
    """
    rows, category, year = category_year(category, year)
    p = check_column(param, category, rows)
    if p in ("score", "rank"):
        raise NirfInputError("param must be a parameter such as rpc, tlr, go, oi or pr.")
    d = _two_columns(rows, category, "score", p)
    c = correlate(d["score"], d[p])
    d["expected"] = c["intercept"] + c["slope"] * d["score"]
    d["residual"] = d[p] - d["expected"]
    d["residual_z"] = d["residual"] / d["residual"].std()
    d["label"] = d["institution_key"].map(chart_labels(d["institution_key"]))
    flagged = d[d["residual_z"] > z_threshold].sort_values("residual_z", ascending=False)

    fig = go.Figure()
    for mask, name, color, size in ((d["residual_z"] <= z_threshold, "Within the usual range", OTHER, 8),
                                    (d["residual_z"] > z_threshold, f"Unusually high (z > {z_threshold:g})", HIGHLIGHT, 11)):
        t = d[mask]
        fig.add_trace(go.Scatter(
            x=t["score"], y=t[p], mode="markers", name=name, marker=dict(color=color, size=size, opacity=0.9),
            customdata=np.stack([t["canonical_name"], t["rank_raw"], t["expected"], t["residual_z"]], axis=1),
            hovertemplate=(f"<b>%{{customdata[0]}}</b> (rank %{{customdata[1]}})<br>Overall score %{{x:.2f}}<br>"
                           f"{SHORT[p]} %{{y:.2f}} (line predicts %{{customdata[2]:.1f}})<br>Residual z-score "
                           f"%{{customdata[3]:.2f}}<extra></extra>")))
    xs = np.array([d["score"].min(), d["score"].max()])
    fig.add_trace(go.Scatter(x=xs, y=c["intercept"] + c["slope"] * xs, mode="lines", name="Least-squares line",
                             line=dict(color=INK_SECONDARY, width=2),
                             hovertemplate=(f"{SHORT[p]} = {c['intercept']:.2f} + {c['slope']:.3f} × score"
                                            "<extra></extra>")))
    fig.update_xaxes(title_text=LABELS["score"], showgrid=True)
    fig.update_yaxes(title_text=LABELS[p])
    fig.update_layout(legend=dict(orientation="h", x=0, y=1.0, yanchor="bottom"))
    shown = flagged.head(12)
    label_points(fig, shown["score"], shown[p], shown["label"], padded_range(d["score"]), padded_range(d[p]),
                 avoid_x=d["score"], avoid_y=d[p])

    if len(flagged):
        top = flagged.iloc[0]
        one = len(flagged) == 1
        title = (f"{len(flagged)} {category} institution{'' if one else 's'} in {year} {'has' if one else 'have'} "
                 f"{SHORT[p]} far above what {'its' if one else 'their'} overall score predicts")
        insight = (f"In {category} {year}, {len(flagged)} of {len(d)} institutions {'has' if one else 'have'} "
                   f"{SHORT[p]} more than "
                   f"{z_threshold:g} standard deviations above the line through all institutions: "
                   + ", ".join(f"{r.label} ({SHORT[p]} {r[p]:.1f} vs {r.expected:.1f} expected, z = {r.residual_z:.1f})"
                               for _, r in flagged.head(4).iterrows())
                   + (f" and {len(flagged) - 4} more." if len(flagged) > 4 else "."))
    else:
        top = d.loc[d["residual_z"].idxmax()]
        title = f"No {category} institution in {year} has {SHORT[p]} more than {z_threshold:g} SD above the line"
        insight = (f"In {category} {year}, no institution's {SHORT[p]} is more than {z_threshold:g} standard deviations above "
                   f"what its overall score predicts; the largest gap is {top['label']} ({SHORT[p]} {top[p]:.1f} vs "
                   f"{top['expected']:.1f} expected, z = {top['residual_z']:.1f}).")
    finish(fig, title, f"{category} ranking {year} · {len(d)} institutions · line = least-squares fit (r = "
           f"{c['pearson_r']:.2f}) · highlighted: residual z-score > {z_threshold:g}",
           note=f"The overall score contains {SHORT[p]} (weighted), so the line partly reflects how the score is built.")
    method = (f"We fit the least-squares line {SHORT[p]} = {c['intercept']:.2f} + {c['slope']:.3f} × overall score through "
              f"the {len(d)} {category} institutions of {year}. For each institution the residual = actual {SHORT[p]} − "
              f"the value on the line (its 'expected' {SHORT[p]} for that overall score). The residual z-score = residual "
              f"/ SD of all residuals ({d['residual'].std():.2f}). A z-score above {z_threshold:g} means the institution's "
              f"{SHORT[p]} is more than {z_threshold:g} standard deviations higher than institutions with a similar overall "
              f"score; with roughly normal residuals only about 2.5% would pass this by chance.")
    table = (d.sort_values("residual_z", ascending=False)
             [["label", "canonical_name", "rank_raw", "score", p, "expected", "residual", "residual_z"]]
             .rename(columns={"label": "institution", "canonical_name": "full_name", "rank_raw": "rank", p: SHORT[p]})
             .round(2).reset_index(drop=True))
    table["unusual"] = table["residual_z"] > z_threshold
    return ChartResult(fig, table, insight, method, "scatterplot")


def research_over_teaching(year: int | None = None, category: str = "Overall", n: int = 15) -> ChartResult:
    """Answers questions like: "Which institutions perform substantially better in research than in
    teaching?" (Q8.2)

    Definition: research advantage = RPC score - TLR score (both out of 100) for the same institution.
    Method: compute the difference for every institution of the category-year, sort from largest to
    smallest, and draw the n largest as a ranked horizontal bar chart (teal = RPC higher, coral =
    TLR still higher). The table has every institution and also the gap in z-scores, which allows for
    RPC usually being much lower than TLR.
    """
    rows, category, year = category_year(category, year)
    rpc = check_column("rpc", category, rows)
    tlr = check_column("tlr", category, rows)
    n = int(n)
    if n < 1:
        raise NirfInputError("n must be at least 1.")
    d = _two_columns(rows, category, rpc, tlr)
    d["difference"] = d[rpc] - d[tlr]
    d["z_difference"] = (d[rpc] - d[rpc].mean()) / d[rpc].std() - (d[tlr] - d[tlr].mean()) / d[tlr].std()
    d = d.sort_values(["difference", "rank"], ascending=[False, True])
    d["institution"] = d["institution_key"].map(chart_labels(d["institution_key"]))
    top = d.head(n).iloc[::-1]

    fig = go.Figure(go.Bar(
        x=top["difference"], y=top["institution"], orientation="h",
        marker_color=[UP if v > 0 else DOWN for v in top["difference"]],
        text=[f"RPC {a:.0f} · TLR {b:.0f}" for a, b in zip(top[rpc], top[tlr])], textposition="outside",
        cliponaxis=False, showlegend=False,
        customdata=np.stack([top["canonical_name"], top["rank_raw"], top[rpc], top[tlr]], axis=1),
        hovertemplate=("<b>%{customdata[0]}</b> (rank %{customdata[1]})<br>RPC %{customdata[2]:.2f} − TLR "
                       "%{customdata[3]:.2f} = %{x:+.2f}<extra></extra>")))
    for name, c, show in (("RPC higher than TLR", UP, (top["difference"] > 0).any()),
                          ("TLR still higher", DOWN, (top["difference"] <= 0).any())):
        if show:
            fig.add_trace(go.Bar(x=[None], y=[None], name=name, marker_color=c, orientation="h"))
    lo, hi = min(0, top["difference"].min()), max(0, top["difference"].max())
    pad = 0.35 * (hi - lo)   # room for the "RPC .. · TLR .." labels outside the bar ends, on both sides
    fig.update_xaxes(title_text="RPC − TLR (points)", showgrid=True, zeroline=True, zerolinecolor=INK_SECONDARY,
                     range=[lo - (pad if lo < 0 else 0), hi + (pad if hi > 0 else 0)])
    fig.update_yaxes(title_text=None, showgrid=False)
    fig.update_layout(barmode="overlay", legend=dict(orientation="h", x=0, y=1.0, yanchor="bottom"))

    positive = d[d["difference"] > 0]
    first = d.iloc[0]
    title = (f"Only {len(positive)} of {len(d)} {category} institutions in {year} score higher on research (RPC) than "
             f"teaching (TLR); {first['institution']} leads by {first['difference']:.0f} points"
             if len(positive) else
             f"No {category} institution in {year} scores higher on RPC than on TLR; {first['institution']} comes closest")
    insight = (f"In {category} {year}, {len(positive)} of {len(d)} institutions have a higher RPC than TLR score. The "
               f"largest research advantage is {first['canonical_name']} (RPC {first[rpc]:.1f} vs TLR {first[tlr]:.1f}, "
               f"{signed(first['difference'], 1)} points). Typically RPC is far below TLR (medians "
               f"{d[rpc].median():.1f} vs {d[tlr].median():.1f}), so even a small positive gap is rare.")
    finish(fig, title, f"{category} ranking {year} · the {len(top)} largest values of RPC − TLR · label = both scores",
           height=max(420, 170 + 30 * len(top)), legend_title="")
    method = (f"For each of the {len(d)} {category} institutions of {year} with both parameters published we compute "
              f"RPC − TLR (both are scored out of 100). A positive value means research and professional practice score "
              f"higher than teaching, learning and resources. We sort and show the {len(top)} largest. Because RPC is "
              f"usually much lower than TLR, the table also gives the gap in z-scores (z(RPC) − z(TLR), z = (value − mean) "
              f"/ SD), which measures research strength relative to other institutions rather than in raw points.")
    table = (d[["institution", "canonical_name", "rank_raw", "score", rpc, tlr, "difference", "z_difference"]]
             .rename(columns={"canonical_name": "full_name", "rank_raw": "rank", rpc: "RPC", tlr: "TLR"})
             .round(2).reset_index(drop=True))
    return ChartResult(fig, table, insight, method, "bar chart")


def unusual_score_jumps(category: str = "Overall", z_threshold: float = 2.0, max_labels: int = 12) -> ChartResult:
    """Answers questions like: "Which institutions experienced an unusually large year-to-year score change?" (Q8.3)

    Definition: score change = score in year Y - score in the previous published year (institutions
    scored in both). z-score of a change = (change - mean change that year) / SD of the changes that
    year; it is computed per year pair because NIRF's method changes can shift everyone's scores
    in a given year. "Unusual" = |z| > z_threshold (default 2).
    Method: one box plot per year pair with every institution's change drawn as a jittered dot on
    top (a jittered strip chart: dots spread sideways at random so they do not hide each other).
    Unusual changes are coloured (teal = jump up, coral = drop) and the max_labels largest are named.
    """
    df = load_master()
    category = check_category(category, df)
    years = category_years(category, df)
    cat = filter_df(df, categories=category)
    scores = cat[cat["score"].notna()].pivot(index="institution_key", columns="year", values="score")
    if scores.empty or len(years) < 2:
        raise NirfInputError(f"{category} has no published scores in two consecutive years.")
    parts = []
    for y0, y1 in zip(years[:-1], years[1:]):
        if y0 not in scores or y1 not in scores:
            continue
        ch = (scores[y1] - scores[y0]).dropna()
        if len(ch) < 5:
            continue
        parts.append(pd.DataFrame({"institution_key": ch.index, "pair": f"{y0}→{y1}", "year_from": y0, "year_to": y1,
                                   "score_from": scores.loc[ch.index, y0].values,
                                   "score_to": scores.loc[ch.index, y1].values, "change": ch.values,
                                   "z": ((ch - ch.mean()) / ch.std()).values}))
    if not parts:
        raise NirfInputError(f"{category} has too few institutions scored in consecutive years.")
    d = pd.concat(parts, ignore_index=True)
    names = cat.drop_duplicates("institution_key").set_index("institution_key")["canonical_name"]
    labels = chart_labels(d["institution_key"])
    d["institution"] = d["institution_key"].map(labels)
    d["full_name"] = d["institution_key"].map(names)
    d["unusual"] = d["z"].abs() > z_threshold
    pairs = list(dict.fromkeys(d["pair"]))
    pos = {p: i for i, p in enumerate(pairs)}
    d["x"] = d["pair"].map(pos) + jitter(len(d), 0.22)
    label_idx = set(d[d["unusual"]].assign(a=d["z"].abs()).nlargest(int(max_labels), "a").index)

    fig = go.Figure()
    for p in pairs:
        t = d[d["pair"].eq(p)]
        fig.add_trace(go.Box(y=t["change"], x=[pos[p]] * len(t), name=p, boxpoints=False, width=0.6,
                             fillcolor="rgba(0,0,0,0)", line=dict(color=INK_SECONDARY, width=1.2), showlegend=False,
                             hoverinfo="skip"))
    groups = ((~d["unusual"], "Usual change", OTHER, 6),
              (d["unusual"] & d["change"].gt(0), f"Unusual jump up (z > {z_threshold:g})", UP, 9),
              (d["unusual"] & d["change"].le(0), f"Unusual drop (z < −{z_threshold:g})", DOWN, 9))
    for mask, name, color, size in groups:
        t = d[mask]
        if t.empty:
            continue
        fig.add_trace(go.Scatter(
            x=t["x"], y=t["change"], mode="markers", name=name, marker=dict(color=color, size=size, opacity=0.8),
            customdata=np.stack([t["full_name"], t["pair"], t["score_from"], t["score_to"], t["z"]], axis=1),
            hovertemplate=("<b>%{customdata[0]}</b><br>%{customdata[1]}: %{customdata[2]:.2f} → %{customdata[3]:.2f}"
                           "<br>Change %{y:+.2f} points · z = %{customdata[4]:.2f}<extra></extra>")))
    fig.update_xaxes(title_text="Year pair (previous → next published year)", tickmode="array",
                     tickvals=list(range(len(pairs))), ticktext=pairs, range=[-0.6, len(pairs) - 0.4])
    fig.update_yaxes(title_text="Change in overall score (points)", zeroline=True, zerolinecolor=INK_SECONDARY)
    fig.update_layout(legend=dict(orientation="h", x=0, y=1.0, yanchor="bottom"))
    shown = d.loc[sorted(label_idx, key=lambda i: -abs(d.at[i, "z"]))]
    label_points(fig, shown["x"], shown["change"], shown["institution"], (-0.6, len(pairs) - 0.4),
                 padded_range(d["change"]), avoid_x=d["x"], avoid_y=d["change"])

    un = d[d["unusual"]].assign(a=d["z"].abs()).sort_values("a", ascending=False)
    big = un.iloc[0] if len(un) else d.loc[d["z"].abs().idxmax()]
    n_up, n_down = int((un["change"] > 0).sum()), int((un["change"] <= 0).sum())
    title = (f"{len(un)} unusual year-to-year score changes in {category}; the largest: {big['institution']} "
             f"{signed(big['change'], 1)} points ({big['pair']})")
    insight = (f"Out of {len(d)} year-to-year score changes in {category} ({fmt_years(years)}), {len(un)} are unusual "
               f"(|z| > {z_threshold:g}): {n_up} jumps up and {n_down} drops. The most extreme is {big['full_name']} in "
               f"{big['pair']} ({big['score_from']:.1f} → {big['score_to']:.1f}, {signed(big['change'], 1)} points, "
               f"z = {signed(big['z'], 1)}). Institutions with unusual changes more than once: "
               + (", ".join(f"{k} ({v}×)" for k, v in un["institution"].value_counts().loc[lambda s: s > 1].items())
                  or "none") + ".")
    finish(fig, title, f"{category} ranking · one box per year pair, every dot = one institution's score change · "
           f"labelled: the {min(len(un), int(max_labels))} largest |z|", height=580, legend_title="")
    method = (f"For each {category} institution with a published score in two consecutive published years, change = new "
              f"score − old score. Within each year pair we turn the changes into z-scores, z = (change − mean change) / "
              f"SD of the changes, so a year in which NIRF's method moved everyone up or down does not make every "
              f"institution look unusual. |z| > {z_threshold:g} = unusual (more than two standard deviations from that "
              f"year's typical change). The box plot shows each year's median and middle 50% of changes; dots are spread "
              f"sideways at random (jitter, fixed seed) so they do not cover each other.")
    table = (un if len(un) else d).drop(columns=["x", "a", "institution_key", "unusual"], errors="ignore")
    table = table[["institution", "full_name", "pair", "score_from", "score_to", "change", "z"]].round(2)
    return ChartResult(fig, table.reset_index(drop=True), insight, method, "jittered strip chart")


def strong_param_poor_rank(param: str = "go", year: int | None = None, category: str = "Overall",
                           max_labels: int = 10) -> ChartResult:
    """Answers questions like: "Which institutions have a strong parameter score but a relatively poor overall
    rank?" (Q8.4)

    Definition: "strong" = the parameter is in the top quartile of the category-year (at or above Q3,
    the 75th percentile); "relatively poor rank" = exact rank in the bottom half (worse than the
    median exact rank). Both cut-offs come from the same category-year.
    Method: scatterplot of the parameter (x) against the rank (y, reversed so rank 1 is at the top),
    with a dashed line at Q3 of the parameter and at the median rank; the bottom-right corner (strong
    parameter, poor rank) is highlighted and labelled.
    """
    rows, category, year = category_year(category, year)
    p = check_column(param, category, rows)
    if p in ("score", "rank"):
        raise NirfInputError("param must be a parameter such as tlr, rpc, go, oi or pr.")
    d = rows[rows["rank"].notna() & rows[p].notna()].copy()
    if len(d) < 8:
        raise NirfInputError(f"Only {len(d)} {category} institutions in {year} have an exact rank and {SHORT[p]}.")
    d["rank"] = d["rank"].astype(float)
    q3 = d[p].quantile(0.75)
    med_rank = d["rank"].median()
    d["flag"] = d[p].ge(q3) & d["rank"].gt(med_rank)
    d["label"] = d["institution_key"].map(chart_labels(d["institution_key"]))
    flagged = d[d["flag"]].sort_values(p, ascending=False)
    label_keys = set(flagged["institution_key"].head(int(max_labels)))

    fig = go.Figure()
    for mask, name, color, size in ((~d["flag"], "Other institutions", OTHER, 8),
                                    (d["flag"], f"Top-quartile {SHORT[p]}, bottom-half rank", HIGHLIGHT, 11)):
        t = d[mask]
        fig.add_trace(go.Scatter(
            x=t[p], y=t["rank"], mode="markers", name=name, marker=dict(color=color, size=size, opacity=0.85),
            customdata=np.stack([t["canonical_name"], t["score"]], axis=1),
            hovertemplate=(f"<b>%{{customdata[0]}}</b><br>Rank %{{y:.0f}} · overall score %{{customdata[1]:.2f}}"
                           f"<br>{SHORT[p]} %{{x:.2f}}<extra></extra>")))
    fig.add_vline(x=q3, line=dict(color=INK_SECONDARY, width=1, dash="dash"),
                  annotation_text=f"Q3 of {SHORT[p]} = {q3:.1f}", annotation_position="top right",
                  annotation_font=dict(size=11, color=INK_SECONDARY))
    fig.add_hline(y=med_rank, line=dict(color=INK_SECONDARY, width=1, dash="dash"),
                  annotation_text=f"median rank {med_rank:g}", annotation_position="bottom left",
                  annotation_font=dict(size=11, color=INK_SECONDARY))
    fig.update_xaxes(title_text=LABELS[p], showgrid=True)
    fig.update_yaxes(title_text="Rank (1 = best, at the top)")
    fig.update_layout(legend=dict(orientation="h", x=0, y=1.0, yanchor="bottom"))
    shown = flagged[flagged["institution_key"].isin(label_keys)]
    label_points(fig, shown[p], shown["rank"], shown["label"], padded_range(d[p]), padded_range(d["rank"]),
                 avoid_x=d[p], avoid_y=d["rank"], y_reversed=True)   # rank axis reversed: 1 = best, at the top

    strong = d[d[p].ge(q3)]
    title = (f"{len(flagged)} of the {len(strong)} {category} institutions with a top-quartile {SHORT[p]} in {year} are "
             f"ranked in the bottom half")
    insight = (f"In {category} {year}, {len(strong)} institutions have {SHORT[p]} at or above Q3 ({q3:.1f}); {len(flagged)} "
               f"of them still rank below the median rank ({med_rank:g})"
               + (": " + ", ".join(f"{r.label} ({SHORT[p]} {r[p]:.1f}, rank {r['rank']:.0f})"
                                   for _, r in flagged.head(4).iterrows())
                  + (f" and {len(flagged) - 4} more" if len(flagged) > 4 else "") + ". Their other parameters hold them back."
                  if len(flagged) else ", so a strong " + SHORT[p] + " almost always goes with a good rank."))
    finish(fig, title, f"{category} ranking {year} · {len(d)} institutions with an exact rank · highlighted: {SHORT[p]} ≥ Q3 "
           f"and rank worse than the median")
    method = (f"Among the {len(d)} {category} institutions of {year} with an exact rank and a published {SHORT[p]}, we call "
              f"{SHORT[p]} 'strong' when it is at or above Q3 (the 75th percentile, {q3:.1f}: the top quarter), and the rank "
              f"'relatively poor' when it is worse than the median rank ({med_rank:g}: the bottom half of the list). "
              f"Institutions meeting both conditions are highlighted. The rank axis is reversed so rank 1 is at the top; "
              f"the overall score (and so the rank) also depends on the other parameters and their weights.")
    table = (flagged[["label", "canonical_name", "state", "rank", "score", p]]
             .rename(columns={"label": "institution", "canonical_name": "full_name", p: SHORT[p]})
             .round(2).reset_index(drop=True))
    table["rank"] = table["rank"].astype(int)
    if table.empty:
        table = pd.DataFrame({"institution": ["none"], "note": [insight]})
    table.attrs.update(q3=q3, median_rank=med_rank)
    return ChartResult(fig, table, insight, method, "scatterplot")


def volatility_vs_peers(category: str = "Overall", min_years: int = 4) -> ChartResult:
    """Answers questions like: "Which institutions have unusually high ranking volatility compared with
    similar institutions?" (Q8.5)

    Definition: volatility = standard deviation (SD) of an institution's exact ranks over the years
    (needs at least min_years exact ranks). Peers = institutions in the same band of median rank
    (1-10, 11-25, 26-50, 51-100, 101-150, 151-200): lower down the list ranks naturally move more, so
    an institution is compared only with its peers. "Unusually high" = above Q3 + 1.5 x IQR of its
    peer band's SDs (the box-plot outlier rule).
    Method: box-and-whisker plot of rank SD per peer band, with every institution as a jittered dot;
    the unusual ones are highlighted and labelled.
    """
    df = load_master()
    category = check_category(category, df)
    years = category_years(category, df)
    min_years = int(min_years)
    if not 2 <= min_years <= len(years):
        raise NirfInputError(f"{category} has {len(years)} years ({fmt_years(years)}); min_years must be between 2 and "
                             f"{len(years)}.")
    cat = filter_df(df, categories=category, exact_ranks_only=True)
    g = cat.groupby("institution_key")["rank"]
    v = pd.DataFrame({"years": g.size(), "rank_sd": g.std().astype(float), "median_rank": g.median().astype(float),
                      "best": g.min().astype(float), "worst": g.max().astype(float)})
    v = v[v["years"] >= min_years].copy()
    if len(v) < 5:
        raise NirfInputError(f"Fewer than 5 {category} institutions have {min_years}+ years of exact ranks.")
    cuts = [(10, "1-10"), (25, "11-25"), (50, "26-50"), (100, "51-100"), (150, "101-150"), (200, "151-200"),
            (300, "201-300")]
    v["peer_band"] = v["median_rank"].map(lambda r: next(b for c, b in cuts if r <= c))
    bands = [b for b in BAND_ORDER if b in set(v["peer_band"])]
    stats_ = v.groupby("peer_band")["rank_sd"].quantile([0.25, 0.5, 0.75]).unstack()
    stats_.columns = ["q1", "median", "q3"]
    stats_["fence"] = stats_["q3"] + 1.5 * (stats_["q3"] - stats_["q1"])
    v = v.join(stats_, on="peer_band")
    v["unusual"] = v["rank_sd"] > v["fence"]
    v["times_peer_median"] = v["rank_sd"] / v["median"]
    v["institution"] = v.index.map(chart_labels(v.index))
    names = cat.drop_duplicates("institution_key").set_index("institution_key")["canonical_name"]
    v["full_name"] = v.index.map(names)
    pos = {b: i for i, b in enumerate(bands)}
    v["x"] = v["peer_band"].map(pos) + jitter(len(v), 0.2)

    fig = go.Figure()
    for b in bands:
        t = v[v["peer_band"].eq(b)]
        fig.add_trace(go.Box(y=t["rank_sd"], x=[pos[b]] * len(t), name=b, boxpoints=False, width=0.6,
                             fillcolor=tint(CATEGORICAL[0], 0.10), line=dict(color=CATEGORICAL[0], width=1.5),
                             showlegend=False, hoverinfo="skip"))
    for mask, name, color, size in ((~v["unusual"], "Within the usual range for its peers", OTHER, 7),
                                    (v["unusual"], "Unusually volatile (above Q3 + 1.5 × IQR)", HIGHLIGHT, 10)):
        t = v[mask]
        if t.empty:
            continue
        fig.add_trace(go.Scatter(
            x=t["x"], y=t["rank_sd"], mode="markers", name=name, marker=dict(color=color, size=size, opacity=0.85),
            customdata=np.stack([t["full_name"], t["median_rank"], t["best"], t["worst"], t["years"], t["median"]], axis=1),
            hovertemplate=("<b>%{customdata[0]}</b><br>Rank SD %{y:.1f} (peer median %{customdata[5]:.1f})<br>Median "
                           "rank %{customdata[1]:.0f} · best %{customdata[2]:.0f} · worst %{customdata[3]:.0f}<br>"
                           "%{customdata[4]} years with an exact rank<extra></extra>")))
    fig.update_xaxes(title_text="Peer band (by the institution's median rank)", tickmode="array",
                     tickvals=list(range(len(bands))), ticktext=bands, range=[-0.6, len(bands) - 0.4])
    fig.update_yaxes(title_text="Rank volatility: SD of exact ranks (places)")
    fig.update_layout(legend=dict(orientation="h", x=0, y=1.0, yanchor="bottom"))
    shown = v[v["unusual"]].sort_values("rank_sd", ascending=False)
    label_points(fig, shown["x"], shown["rank_sd"], shown["institution"], (-0.6, len(bands) - 0.4),
                 (0, padded_range(v["rank_sd"])[1]), avoid_x=v["x"], avoid_y=v["rank_sd"])

    un = v[v["unusual"]].sort_values("times_peer_median", ascending=False)
    top = un.iloc[0] if len(un) else v.sort_values("times_peer_median", ascending=False).iloc[0]
    title = (f"{len(un)} {category} institution{'s' if len(un) != 1 else ''} {'move' if len(un) != 1 else 'moves'} far "
             f"more than {'their' if len(un) != 1 else 'its'} peers; most: {top['institution']} (rank SD "
             f"{top['rank_sd']:.1f} vs {top['median']:.1f} typical)")
    insight = (f"Of the {len(v)} {category} institutions with at least {min_years} exact ranks, {len(un)} are unusually "
               f"volatile for their peer band"
               + (": " + ", ".join(f"{r.institution} (median rank {r.median_rank:.0f}, SD {r.rank_sd:.1f} vs peer median "
                                   f"{r['median']:.1f})" for _, r in un.head(4).iterrows())
                  + (f" and {len(un) - 4} more" if len(un) > 4 else "") if len(un) else "")
               + ". Typical volatility grows down the list: median rank SD "
               + ", ".join(f"{b} {stats_.at[b, 'median']:.1f}" for b in bands) + ".")
    finish(fig, title, f"{category} ranking, {fmt_years(years)} · institutions with {min_years}+ exact ranks · box = "
           f"peer band's middle 50% · highlighted: above Q3 + 1.5 × IQR of the peer band", height=560, legend_title="")
    method = (f"For each {category} institution with at least {min_years} years of exact ranks we compute the standard "
              f"deviation of those ranks (volatility: how far its rank typically is from its own average rank). Lower down "
              f"the list ranks naturally move more, so we compare like with like: peers = institutions whose median rank "
              f"falls in the same band (1-10, 11-25, 26-50, 51-100 ...). Within each peer band an institution is "
              f"'unusually volatile' when its SD is above Q3 + 1.5 × IQR of that band's SDs, the same rule a box plot uses "
              f"for outliers. Years where NIRF published only a band (e.g. 101-150) have no exact rank and are left out, "
              f"which can understate the volatility of institutions that drop out of the exact-rank list.")
    table = (v.sort_values(["unusual", "times_peer_median"], ascending=[False, False])
             [["institution", "full_name", "peer_band", "years", "median_rank", "best", "worst", "rank_sd", "median",
               "fence", "times_peer_median", "unusual"]]
             .rename(columns={"median": "peer_median_sd", "fence": "peer_fence_sd"}).round(2).reset_index(drop=True))
    return ChartResult(fig, table, insight, method, "box-and-whisker plot")
