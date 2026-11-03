"""The one Plotly look used by every NIRF Atlas chart: the "nirf" template, palettes and the source note.

Importing this module registers the template and makes it Plotly's default, so a chart looks the
same whichever engine drew it. Design choices (kept deliberately quiet so the data stands out):
  * a light surface, hairline grid on the value axis only, thin 2 px lines, 8 px markers;
  * a colour-blind-safe categorical palette in a FIXED order (slot 1 is always blue, slot 2 orange ...);
    the order was checked so neighbouring colours stay distinguishable for the common forms of colour
    blindness. Charts with more than 8 groups fold the rest into "Other" instead of inventing colours;
  * one blue light-to-dark scale for amounts (maps, heatmaps) and a blue-grey-red scale for +/- values
    (blue = moved up / gained, red = moved down / lost);
  * every chart ends with the note "Source: NIRF, Ministry of Education, Govt. of India".
"""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio

FONT = "Inter, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"

# Surfaces and ink.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
BORDER = "rgba(11,11,11,0.10)"

# Categorical palette, fixed order (blue, orange, aqua, yellow, magenta, green, violet, red).
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
OTHER = "#b5b3ab"           # "Other" groups and context marks (e.g. institutions outside the top N)
CONTEXT = "#e1e0d9"         # very light: "ranked but not highlighted" cells

# Sequential blue ramp (light = little, dark = a lot) and the diverging pair.
BLUES = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5",
         "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]
SEQUENTIAL = [[i / (len(BLUES) - 1), c] for i, c in enumerate(BLUES)]
UP = "#2a78d6"              # moved up / gained / positive
DOWN = "#e34948"            # moved down / lost / negative
NEUTRAL = "#d4d2ca"         # no change
DIVERGING = [[0.0, "#b3261e"], [0.25, "#e88a84"], [0.5, "#f0efec"], [0.75, "#86b6ef"], [1.0, "#184f95"]]

SOURCE_NOTE = "Source: NIRF, Ministry of Education, Govt. of India"
CROSS_CATEGORY_NOTE = ("Note: each category has its own parameter weights, so scores are comparable "
                       "only within a category.")

_MARGIN_BOTTOM = 96


def ordinal_blues(n: int) -> list[str]:
    """n ordered shades of blue (for ordered groups such as years or quartiles), light to dark.

    Starts at a mid-light step so even the lightest shade stays visible on the white surface.
    """
    steps = BLUES[2:]
    if n <= 1:
        return [steps[len(steps) // 2]]
    return [steps[round(i * (len(steps) - 1) / (n - 1))] for i in range(n)]


def color_map(names, other_label: str = "Other") -> dict[str, str]:
    """Fixed colour per name in the order given (first name = slot 1). 'Other' is always grey."""
    out, slot = {}, 0
    for n in names:
        if n == other_label:
            out[n] = OTHER
        elif n not in out:
            out[n] = CATEGORICAL[slot % len(CATEGORICAL)]
            slot += 1
    return out


_axis = dict(
    showline=True, linecolor=AXIS, linewidth=1, ticks="outside", tickcolor=AXIS, ticklen=4,
    tickfont=dict(color=INK_SECONDARY, size=12), title=dict(font=dict(color=INK_SECONDARY, size=13), standoff=10),
    gridcolor=GRID, gridwidth=1, zeroline=False, automargin=True,
)

pio.templates["nirf"] = go.layout.Template(
    layout=dict(
        font=dict(family=FONT, size=13, color=INK),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        colorway=CATEGORICAL,
        title=dict(x=0, xref="container", xanchor="left", pad=dict(l=20), y=0.97, yref="container", yanchor="top",
                   font=dict(size=17, color=INK), subtitle=dict(font=dict(size=13, color=INK_SECONDARY))),
        xaxis=dict(_axis, showgrid=False),
        yaxis=dict(_axis, showgrid=True),
        legend=dict(title=dict(font=dict(size=12, color=INK_SECONDARY)), font=dict(size=12, color=INK),
                    bgcolor="rgba(0,0,0,0)", itemsizing="constant", tracegroupgap=4,
                    traceorder="normal"),
        hoverlabel=dict(bgcolor="white", bordercolor=AXIS, align="left",
                        font=dict(family=FONT, size=12, color=INK)),
        hovermode="closest",
        margin=dict(l=72, r=32, t=96, b=_MARGIN_BOTTOM),
        bargap=0.28,
        barcornerradius=4,
        colorscale=dict(sequential=SEQUENTIAL, diverging=DIVERGING),
        coloraxis=dict(colorbar=dict(outlinewidth=0, thickness=12, tickfont=dict(color=INK_SECONDARY))),
    ),
    data=dict(
        scatter=[go.Scatter(line=dict(width=2), marker=dict(size=8, line=dict(width=1, color=SURFACE)))],
        bar=[go.Bar(marker=dict(line=dict(width=0)), textfont=dict(color=INK_SECONDARY, size=11))],
        histogram=[go.Histogram(marker=dict(line=dict(width=1, color=SURFACE)))],
        box=[go.Box(line=dict(width=1.5), marker=dict(size=5, opacity=0.6))],
        heatmap=[go.Heatmap(colorscale=SEQUENTIAL, xgap=2, ygap=2)],
    ),
)
pio.templates.default = "nirf"


def add_source_note(fig: go.Figure, note: str | None = None) -> go.Figure:
    """Write the NIRF source line (and an optional extra note line) at the bottom-left of the chart."""
    text = SOURCE_NOTE if not note else f"{note}<br>{SOURCE_NOTE}"
    bottom = fig.layout.margin.b if fig.layout.margin.b is not None else _MARGIN_BOTTOM
    if note and bottom < _MARGIN_BOTTOM + 16:
        bottom = _MARGIN_BOTTOM + 16
        fig.update_layout(margin=dict(b=bottom))
    fig.add_annotation(text=text, xref="paper", yref="paper", x=0, y=0, xanchor="left", yanchor="bottom",
                       yshift=-bottom + 6, showarrow=False, align="left",
                       font=dict(size=11, color=INK_MUTED))
    return fig


def finish(fig: go.Figure, title: str, subtitle: str | None = None, note: str | None = None,
           height: int = 520, legend_title: str | None = None) -> go.Figure:
    """Apply the template, the answer-style title (+ subtitle), legend title and the source note."""
    fig.update_layout(
        template="nirf", height=height,
        title=dict(text=title, subtitle=dict(text=subtitle or "")),
    )
    if legend_title is not None:
        fig.update_layout(legend_title_text=legend_title)
    return add_source_note(fig, note)
