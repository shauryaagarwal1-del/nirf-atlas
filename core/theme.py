"""The one Plotly look used by every NIRF Atlas chart: the "nirf" template, palettes and the source note.

Importing this module registers the template and makes it Plotly's default, so a chart looks the
same whichever engine drew it. The look matches the dashboard's "National Observatory" style
(.streamlit/config.toml and assets/style.css): deep navy ink, teal for data, marigold for highlights,
a serif display font for titles (Fraunces) and a clean sans-serif (Inter) for everything else.

Design choices (kept deliberately quiet so the data stands out):
  * a white card surface, hairline grid on the value axis only, thin 2 px lines, 8 px markers;
  * a colour-blind-safe categorical palette in a FIXED order (slot 1 is always teal, slot 2 marigold,
    slot 3 indigo ...). The order was checked with a colour-vision simulation so neighbouring colours
    stay distinguishable for the common forms of colour blindness, in light and in dark mode.
    Charts with more than 8 groups fold the rest into "Other" instead of inventing colours;
  * one teal light-to-dark scale for amounts (maps, heatmaps) and a coral-grey-teal scale for +/- values
    (teal = moved up / gained, coral = moved down / lost);
  * every chart ends with the note "Source: NIRF, Ministry of Education, Govt. of India";
  * dark mode is not an automatic colour flip: dark_variant() swaps every light colour for its own
    dark step (chosen and checked against the dark surface), so the same chart reads well on both;
  * themed() is the one place that turns a chart into what the page draws: the theme's colours, a
    transparent background (the card's surface shows through) and labels on coloured marks in deep
    navy or white, whichever has the higher contrast on that mark.
"""

from __future__ import annotations

import base64
import re
import textwrap

import numpy as np
import plotly.graph_objects as go
import plotly.io as pio

FONT = "Inter, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
DISPLAY_FONT = "Fraunces, Georgia, 'Times New Roman', serif"
MONO_FONT = "'JetBrains Mono', 'SFMono-Regular', Consolas, monospace"

# Surfaces and ink (light mode). The chart surface is the white of the dashboard's cards.
SURFACE = "#ffffff"
INK = "#141b3d"             # deep navy
INK_SECONDARY = "#4a5274"
INK_MUTED = "#6a7090"     # 4.5:1 on white (notes, leader lines)
GRID = "#e9ebf2"
AXIS = "#c8ccda"

# Brand colours: teal carries data, marigold highlights, indigo is the third voice.
TEAL = "#0e9c8c"
MARIGOLD = "#e39a12"
INDIGO = "#4a50c8"
CORAL = "#e0564f"
MARIGOLD_INK = "#925c00"    # marigold for TEXT in a chart (a label in the marigold of its line): 6:1 on white

# Categorical palette, fixed order (teal, marigold, indigo, coral, sky, olive, orchid, brown).
CATEGORICAL = [TEAL, MARIGOLD, INDIGO, CORAL, "#2f8fd8", "#7f8c1f", "#b35bc4", "#a8642a"]
OTHER = "#b4b8c8"           # "Other" groups and context marks (e.g. institutions outside the top N)
CONTEXT = "#e6e8f0"         # very light: "ranked but not highlighted" cells

# Sequential teal ramp (light = little, dark = a lot) and the diverging pair.
RAMP = ["#d3f1ec", "#b9e3db", "#9ed4cb", "#83c6bb", "#66b8ab", "#45aa9b", "#0e9c8c",
        "#0d897b", "#0c776b", "#0a655b", "#08544c", "#07433d", "#05332f"]
SEQUENTIAL = [[i / (len(RAMP) - 1), c] for i, c in enumerate(RAMP)]
UP = TEAL                   # moved up / gained / positive
DOWN = CORAL                # moved down / lost / negative
NEUTRAL = "#cfd3e0"         # no change
DIVERGING = [[0.0, "#e0565b"], [0.25, "#f0a8a7"], [0.5, "#f2f3f7"], [0.75, "#94c8c0"], [1.0, "#0e9c8c"]]

# The same roles, stepped for the dark surface (navy cards). Same hues, same order.
DARK_SURFACE = "#151b34"
_DARK = {
    SURFACE: DARK_SURFACE, INK: "#eef0fa", INK_SECONDARY: "#b6bbd6", INK_MUTED: "#7e85a8",
    GRID: "#242b4b", AXIS: "#3b4369", OTHER: "#5d6488", CONTEXT: "#2a3254", NEUTRAL: "#4a5276",
    MARIGOLD_INK: "#f6c766",
    **dict(zip(CATEGORICAL, ["#14a090", "#c4860a", "#7479e6", "#de5850", "#3a92d8", "#8a9726", "#b468c7",
                             "#c97a3d"])),
    **dict(zip(RAMP, ["#1b3a4a", "#1d4a55", "#1e5a61", "#1e6b6c", "#1d7c78", "#1a8e84", "#14a090",
                      "#42ae9e", "#60bbad", "#7ac9bc", "#92d7cb", "#aae5da", "#c2f3ea"])),
    **dict(zip([c for _, c in DIVERGING], ["#de5850", "#824a56", "#2a3152", "#2d6771", "#14a090"])),
}
_DARK = {k.lower(): v for k, v in _DARK.items()}

SOURCE_NOTE = "Source: NIRF, Ministry of Education, Govt. of India"
CROSS_CATEGORY_NOTE = ("Note: each category has its own parameter weights, so scores are comparable "
                       "only within a category.")

_MARGIN_BOTTOM = 96
_MARGIN_TOP = 104
# Plotly never wraps a title, so a long answer-title would run off the right edge on a laptop screen.
# Titles longer than this many characters are broken over lines; each extra line gets more top margin.
TITLE_WRAP, SUBTITLE_WRAP, TITLE_LINE = 90, 130, 26


def ordinal_ramp(n: int) -> list[str]:
    """n ordered shades of teal (for ordered groups such as years or quartiles), light to dark.

    Starts at a mid step so even the lightest shade keeps at least 2:1 contrast on the white surface.
    """
    steps = RAMP[4:]
    if n <= 1:
        return [steps[len(steps) // 2]]
    return [steps[round(i * (len(steps) - 1) / (n - 1))] for i in range(n)]


def tint(color: str, alpha: float) -> str:
    """A see-through version of a hex colour, e.g. a light fill behind a box plot."""
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


# Highlighted points never rely on colour alone: each highlight colour also has its own marker shape
# (grey context dots stay circles), so the groups can be told apart in greyscale or with colour blindness.
_SYMBOLS = {MARIGOLD: "diamond", UP: "triangle-up", DOWN: "triangle-down"}


def highlight_marker(color: str, size: float, opacity: float = 0.85) -> dict:
    """Marker for a highlight group in a scatterplot: its colour plus a distinct shape and a thin outline."""
    symbol = _SYMBOLS.get(color, "circle")
    if symbol == "circle":
        return dict(color=color, size=size, opacity=opacity)
    return dict(color=color, size=size + 2, opacity=1, symbol=symbol, line=dict(width=1, color=SURFACE))


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

_COLORBAR = dict(outlinewidth=0, thickness=12, tickfont=dict(color=INK_SECONDARY, size=11),
                 title=dict(font=dict(size=12, color=INK_SECONDARY)))

pio.templates["nirf"] = go.layout.Template(
    layout=dict(
        font=dict(family=FONT, size=13, color=INK),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        colorway=CATEGORICAL,
        title=dict(x=0, xref="container", xanchor="left", pad=dict(l=20), y=0.97, yref="container", yanchor="top",
                   font=dict(family=DISPLAY_FONT, size=19, color=INK, weight=600),
                   subtitle=dict(font=dict(family=FONT, size=13, color=INK_SECONDARY))),
        xaxis=dict(_axis, showgrid=False),
        yaxis=dict(_axis, showgrid=True),
        legend=dict(title=dict(font=dict(size=12, color=INK_SECONDARY)), font=dict(size=12, color=INK),
                    bgcolor="rgba(0,0,0,0)", itemsizing="constant", tracegroupgap=4,
                    traceorder="normal"),
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=AXIS, align="left",
                        font=dict(family=FONT, size=12, color=INK)),
        hovermode="closest",
        margin=dict(l=72, r=32, t=_MARGIN_TOP, b=_MARGIN_BOTTOM),
        bargap=0.28,
        barcornerradius=4,
        colorscale=dict(sequential=SEQUENTIAL, diverging=DIVERGING),
        coloraxis=dict(colorbar=dict(outlinewidth=0, thickness=12, tickfont=dict(color=INK_SECONDARY, size=11),
                                     title=dict(font=dict(size=12, color=INK_SECONDARY)))),
    ),
    data=dict(
        scatter=[go.Scatter(line=dict(width=2), marker=dict(size=8, line=dict(width=1, color=SURFACE)))],
        bar=[go.Bar(marker=dict(line=dict(width=0)), textfont=dict(color=INK_SECONDARY, size=11))],
        histogram=[go.Histogram(marker=dict(line=dict(width=1, color=SURFACE)))],
        box=[go.Box(line=dict(width=1.5), marker=dict(size=5, opacity=0.6))],
        heatmap=[go.Heatmap(colorscale=SEQUENTIAL, xgap=2, ygap=2, colorbar=_COLORBAR)],
        choropleth=[go.Choropleth(colorbar=_COLORBAR)],
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


def add_lollipops(fig: go.Figure, values, labels, colors, customdata=None, hovertemplate: str | None = None,
                  text=None, row: int | None = None, col: int | None = None) -> go.Figure:
    """Horizontal lollipop chart: a thin stem from 0 to each value and a dot at its end.

    Reads like a bar chart (length = value) but with less ink, so long sorted lists stay calm.
    `colors` is one colour per value; each colour's stems are drawn as one trace (no legend entry).
    """
    values, labels, colors = list(values), list(labels), list(colors)
    where = dict(row=row, col=col) if row is not None else {}
    for c in dict.fromkeys(colors):
        xs, ys = [], []
        for v, lab, cc in zip(values, labels, colors):
            if cc == c:
                xs += [0, v, None]
                ys += [lab, lab, None]
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=c, width=2), hoverinfo="skip",
                                 showlegend=False), **where)
    fig.add_trace(go.Scatter(
        x=values, y=labels, mode="markers+text" if text is not None else "markers", text=text,
        textposition="middle right", textfont=dict(size=11, color=INK_SECONDARY), cliponaxis=False,
        marker=dict(color=colors, size=11, line=dict(width=0)), customdata=customdata,
        hovertemplate=hovertemplate, showlegend=False), **where)
    return fig


def jitter(n: int, width: float = 0.28, seed: int = 0):
    """n small random sideways offsets in [-width, +width] for a jittered strip chart.

    Fixed seed: the same data always gives the same picture (dots do not jump on every reload).
    """
    return np.random.default_rng(seed).uniform(-width, width, n)


def label_points(fig: go.Figure, x, y, labels, x_range, y_range, avoid_x=(), avoid_y=(),
                 plot_size: tuple[int, int] = (780, 320), y_reversed: bool = False) -> go.Figure:
    """Name chosen points with labels that do not overlap each other, the marked points or the plot edge.

    Plotly places point labels blindly, so in a cluster they print on top of each other or run off the
    chart. Here each label (in the order given, most important first) tries a set of spots around its
    point (right, left, above, below, the diagonals, then a little further out) and takes the first-best
    spot: inside the plot, not on another label, covering as few points as possible, closest to its point.
    A thin leader line joins a label to its point. Positions are worked out in pixels for a plot area of
    about `plot_size` (width, height); `x_range`/`y_range` are fixed on the axes so the mapping holds.
    `avoid_x`/`avoid_y` are other points that labels should not cover.
    """
    (x0, x1), (y0, y1) = x_range, y_range
    width, height = plot_size

    def px(xv, yv):
        fy = (yv - y0) / (y1 - y0)
        return (xv - x0) / (x1 - x0) * width, (1 - fy if y_reversed else fy) * height

    points = [px(a, b) for a, b in zip(avoid_x, avoid_y)]
    placed: list[tuple[float, float, float, float]] = []
    char_w, box_h, gap = 5.7, 14, 7

    def hits(box, others):
        l, b, r, t = box
        return sum(not (r < ol or l > or_ or t < ob or b > ot) for ol, ob, or_, ot in others)

    for xv, yv, text in zip(x, y, labels):
        cx, cy = px(xv, yv)
        w = len(str(text)) * char_w + 6
        side, up = w / 2 + gap, box_h / 2 + gap
        # Candidate centres: right/left/above/below first, then further out (nearest first).
        spots = sorted(((dx, dy) for dx in (0, side, -side, side + 45, -side - 45, side + 110, -side - 110)
                        for dy in (0, up, -up, 2.3 * up, -2.3 * up, 3.6 * up, -3.6 * up, 5 * up, -5 * up)
                        if (dx, dy) != (0, 0) and (dx or abs(dy) >= up)),
                       key=lambda d: (abs(d[0]) - side if d[0] else 0) + abs(d[1]))
        best = None
        for order, (dx, dy) in enumerate(spots):
            box = (cx + dx - w / 2, cy + dy - box_h / 2, cx + dx + w / 2, cy + dy + box_h / 2)
            outside = box[0] < 0 or box[2] > width or box[1] < 0 or box[3] > height
            cover = sum(box[0] - 4 <= qx <= box[2] + 4 and box[1] - 4 <= qy <= box[3] + 4
                        for qx, qy in points if (qx, qy) != (cx, cy))
            cost = 1000 * hits(box, placed) + 1000 * outside + 25 * cover + order / 4
            if best is None or cost < best[0]:
                best = (cost, dx, dy, box)
        _, dx, dy, box = best
        placed.append(box)
        fig.add_annotation(x=xv, y=yv, text=str(text), showarrow=True, ax=dx, ay=-dy, arrowhead=0, arrowwidth=0.8,
                           arrowcolor=INK_MUTED, standoff=5, font=dict(size=10, color=INK_SECONDARY), bgcolor=tint(SURFACE, 0.75))
    fig.update_xaxes(range=list(x_range))
    fig.update_yaxes(range=[y1, y0] if y_reversed else [y0, y1])
    return fig


def rank_axis_words(fig: go.Figure, x: float = 0.004, top: float = 0.995, bottom: float = 0.005,
                    xref: str = "paper", yref: str = "paper") -> go.Figure:
    """Write "better" at the top and "worse" at the bottom of a reversed rank axis (rank 1 at the top),
    so nobody has to work out which way is up."""
    for text, y, anchor in (("better ▲", top, "top"), ("worse ▼", bottom, "bottom")):
        fig.add_annotation(x=x, y=y, xref=xref, yref=yref, text=f"<i>{text}</i>", showarrow=False, xanchor="left",
                           yanchor=anchor, font=dict(size=11, color=INK_SECONDARY))
    return fig


def showing(n: int, total: int, what: str = "institutions") -> str:
    """'showing 10 of 64 institutions' (or '' when everything is shown) for a chart subtitle."""
    return f"showing {n} of {total} {what}" if n < total else f"all {total} {what}"


def padded_range(values, pad: float = 0.06) -> tuple[float, float]:
    """(min, max) of the values with a margin of `pad` x the span on both sides (like Plotly's autorange)."""
    lo, hi = float(np.nanmin(values)), float(np.nanmax(values))
    span = (hi - lo) or 1.0
    return lo - pad * span, hi + pad * span


def wrap_text(text: str, width: int) -> tuple[str, int]:
    """Break plain text over lines of at most `width` characters with <br>; returns (text, extra lines).

    The lines are balanced (about equal length), so a title never ends with a stray word on its own line.
    """
    if len(text) <= width or "<" in text:
        return text, 0
    n = -(-len(text) // width)                                   # lines needed (ceiling division)
    w = -(-len(text) // n)
    while len(lines := textwrap.wrap(text, w, break_on_hyphens=False)) > n:
        w += 1
    return "<br>".join(lines), len(lines) - 1


# Full institution names for chart labels that had to be cut short (filled by core.data.chart_labels):
# finish() puts the full name in the hover text of every point drawn with such a label.
FULL_NAMES: dict[str, str] = {}


def _full_names_on_hover(fig: go.Figure) -> None:
    """Where a trace's points are labelled with a shortened name ('… University of Agricul…'), show the
    full name when the mouse is over the point: the label goes in hovertext and the template uses it."""
    for t in fig.data:
        tmpl = getattr(t, "hovertemplate", None)
        if not tmpl or getattr(t, "hovertext", None) is not None or t.type in ("heatmap", "choropleth"):
            continue
        for axis in ("y", "x"):
            values = getattr(t, axis, None)
            if values is None or f"%{{{axis}}}" not in tmpl:
                continue
            values = list(values)
            if any(isinstance(v, str) and v in FULL_NAMES for v in values):
                try:
                    t.hovertext = [FULL_NAMES.get(v, v) if isinstance(v, str) else v for v in values]
                except ValueError:       # a trace type without hovertext: keep the short label
                    break
                t.hovertemplate = tmpl.replace(f"%{{{axis}}}", "%{hovertext}")
                break


def with_surface(fig) -> go.Figure:
    """Set the chart's paper and plot colour on the figure itself (not only in the template).

    Streamlit fills in its own page colours when a figure leaves them to the template, which turned the
    white chart surface into a grey-blue box and hid the hairline grid. Setting them explicitly keeps the
    designed look; dark_variant() then swaps them for the dark surface.
    """
    fig.update_layout(paper_bgcolor=fig.layout.paper_bgcolor or SURFACE,
                      plot_bgcolor=fig.layout.plot_bgcolor or SURFACE)
    if any(t.type in ("choropleth", "scattergeo") for t in fig.data):
        fig.update_geos(bgcolor=fig.layout.geo.bgcolor or SURFACE)
    return fig


def finish(fig: go.Figure, title: str, subtitle: str | None = None, note: str | None = None,
           height: int = 520, legend_title: str | None = None) -> go.Figure:
    """Apply the template, the answer-style title (+ subtitle), legend title and the source note.

    A chart whose legend lists two or more entries always gets a legend title ("Key" when the engine
    gives none), and shortened institution names get their full name in the hover text.
    """
    title, extra = wrap_text(title, TITLE_WRAP)
    subtitle, extra_sub = wrap_text(subtitle or "", SUBTITLE_WRAP)
    top = (fig.layout.margin.t if fig.layout.margin.t is not None else _MARGIN_TOP) + TITLE_LINE * extra + 18 * extra_sub
    fig.update_layout(
        template="nirf", height=height + TITLE_LINE * extra + 18 * extra_sub, margin=dict(t=top),
        title=dict(text=title, subtitle=dict(text=subtitle)),
    )
    if legend_title is None and not fig.layout.legend.title.text:
        named = [t for t in fig.data if t.name and t.showlegend is not False]
        if len(named) > 1 and fig.layout.showlegend is not False:
            legend_title = "Key"
    if legend_title is not None:
        fig.update_layout(legend_title_text=legend_title)
    _full_names_on_hover(fig)
    with_surface(fig)
    return add_source_note(fig, note)


# ---------- dark mode ----------

_RGBA = re.compile(r"^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)$")


def _dark_color(value: str) -> str:
    """The dark-mode step of one light colour (hex or rgba tint); unknown colours stay as they are."""
    v = value.strip().lower()
    if v in _DARK:
        return _DARK[v]
    m = _RGBA.match(v)
    if m:
        key = "#" + "".join(f"{int(x):02x}" for x in m.groups()[:3])
        if key in _DARK:
            alpha = m.group(4) or "1"
            dark = _DARK[key]
            return f"rgba({int(dark[1:3], 16)},{int(dark[3:5], 16)},{int(dark[5:7], 16)},{alpha})"
    return value


def for_theme(color: str, dark: bool) -> str:
    """A palette colour as drawn in the current theme (its dark step when `dark`)."""
    return _dark_color(color) if dark else color


def _swap(node):
    if isinstance(node, dict):
        # A map's boundaries hold only coordinates (no colours): passed through as they are.
        return {k: v if k == "geojson" else _swap(v) for k, v in node.items()}
    if isinstance(node, (list, tuple)):
        return [_swap(v) for v in node]
    if isinstance(node, np.ndarray) and node.dtype.kind in "OU":
        return [_swap(v) for v in node.tolist()]
    if isinstance(node, str) and (node.startswith("#") or node.startswith("rgb")):
        return _dark_color(node)
    return node


def dark_variant(fig: go.Figure) -> dict:
    """The same chart for the dark theme: every palette colour replaced by its dark-mode step.

    Returns a plain figure dict (what st.plotly_chart accepts), so the original figure is untouched.
    """
    return _swap(fig.to_plotly_json())


# ---------- drawing a chart on the page ----------

CLEAR = "rgba(0,0,0,0)"
# The two text colours for labels printed ON a coloured mark (a bar, a slice, a heatmap cell).
_INKS = (INK, "#ffffff")


def _rgb(color) -> tuple[int, int, int] | None:
    """(r, g, b) of a hex or rgb()/rgba() colour string; None for anything else (named colours, scales)."""
    if not isinstance(color, str):
        return None
    c = color.strip().lower()
    if re.fullmatch(r"#[0-9a-f]{6}", c):
        return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
    if re.fullmatch(r"#[0-9a-f]{3}", c):
        return tuple(int(ch * 2, 16) for ch in c[1:])
    if c == "white":
        return 255, 255, 255
    m = _RGBA.match(c)
    return tuple(int(float(x)) for x in m.groups()[:3]) if m else None


def _luminance(rgb) -> float:
    """WCAG relative luminance: 0 = black, 1 = white (each channel linearised, green weighs most)."""
    def lin(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(a, b) -> float:
    """WCAG contrast ratio of two colours, from 1 (same) to 21 (black on white). 4.5 = readable text."""
    la, lb = sorted((_luminance(_rgb(a)), _luminance(_rgb(b))), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def ink_on(fill) -> str | None:
    """The text colour for a label printed on a mark of this colour; None if the colour is unknown.

    Deep navy or white, whichever reads better. On a few mid-tone colours neither reaches 4.5:1; there
    the label is black or white (one of the two always reaches at least 4.58:1, whatever the colour).
    """
    if _rgb(fill) is None:
        return None
    best = max(_INKS, key=lambda ink: contrast(ink, fill))
    if contrast(best, fill) >= 4.5:
        return best
    return max(("#000000", "#ffffff"), key=lambda ink: contrast(ink, fill))


def _scale_at(scale, t: float) -> tuple[float, float, float] | None:
    """The colour at position t (0..1) of a Plotly colour scale [[pos, colour], ...], interpolated in RGB."""
    stops = [(float(p), _rgb(c)) for p, c in scale]
    if not stops or any(c is None for _, c in stops):
        return None
    t = min(max(t, 0.0), 1.0)
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if p0 <= t <= p1:
            f = 0.0 if p1 == p0 else (t - p0) / (p1 - p0)
            return tuple(a + (b - a) * f for a, b in zip(c0, c1))
    return stops[-1][1] if t >= stops[-1][0] else stops[0][1]


def color_at(scale, t: float) -> str | None:
    """The colour at position t (0..1) of a Plotly colour scale, as a hex string (None if unknown)."""
    rgb = _scale_at(scale, t)
    return None if rgb is None else "#" + "".join(f"{round(x):02x}" for x in rgb)


def scale_positions(values, zmin: float, zmax: float, zmid: float | None = None) -> list[float]:
    """Where each value sits on a colour scale (0..1), the way Plotly maps z to colour (zmid centres it)."""
    lo, hi = float(zmin), float(zmax)
    if zmid is not None:
        half = max(hi - zmid, zmid - lo)
        lo, hi = zmid - half, zmid + half
    span = hi - lo or 1.0
    return [min(max((float(v) - lo) / span, 0.0), 1.0) for v in values]


def inks_on_scale(scale, values, zmin: float, zmax: float, zmid: float | None = None) -> list[str]:
    """The text colour for a label printed on each value's colour of a scale (deep navy or white per mark)."""
    return [ink_on(color_at(scale, t)) or INK for t in scale_positions(values, zmin, zmax, zmid)]


def _values(v):
    """A figure-dict array as numpy: Plotly stores numeric arrays as {"dtype", "bdata" (base64), "shape"}."""
    if isinstance(v, dict) and "bdata" in v:
        out = np.frombuffer(base64.b64decode(v["bdata"]), dtype=np.dtype(v["dtype"]))
        return out.reshape([int(n) for n in str(v["shape"]).split(",")]) if v.get("shape") else out
    return np.array(v, dtype=object)


_TEXT_FIELD = re.compile(r"^%\{text(?::([^}]*))?\}$")


def _heatmap_cell_inks(trace: dict, layout: dict) -> None:
    """Give every heatmap cell label the ink that reads best on that cell's own colour.

    Plotly picks one grey or white per cell, which is below 4.5:1 on the mid-teal cells. Here the cell
    colour is worked out the way Plotly does (value -> position between zmin and zmax -> colour scale)
    and each label is wrapped in a coloured span. Only labels drawn with texttemplate "%{text}" or
    "%{text:<format>}" are touched; the numbers themselves do not change.
    """
    m = _TEXT_FIELD.match(trace.get("texttemplate") or "")
    z, text = trace.get("z"), trace.get("text")
    if not m or z is None or text is None:
        return
    scale = trace.get("colorscale") or (layout.get("template", {}).get("data", {}).get("heatmap") or [{}])[0] \
        .get("colorscale") or layout.get("colorscale", {}).get("sequential")
    if not isinstance(scale, (list, tuple)):
        return
    zs = _values(z).astype(float)
    if zs.ndim != 2 or not np.isfinite(zs).any():
        return
    lo = trace.get("zmin") if trace.get("zmin") is not None else float(np.nanmin(zs))
    hi = trace.get("zmax") if trace.get("zmax") is not None else float(np.nanmax(zs))
    if trace.get("zmid") is not None:
        half = max(hi - trace["zmid"], trace["zmid"] - lo)
        lo, hi = trace["zmid"] - half, trace["zmid"] + half
    spec = m.group(1)
    rows = []
    labels = _values(text)
    for zrow, trow in zip(zs, labels):
        out = []
        for v, label in zip(zrow, trow):
            if label is None or (isinstance(label, float) and np.isnan(label)) or label == "":
                out.append("")
                continue
            try:
                shown = format(float(label), spec) if spec else str(label)
            except (TypeError, ValueError):
                shown = str(label)
            fill = None if not np.isfinite(v) else _scale_at(
                scale, 1 - (v - lo) / (hi - lo or 1) if trace.get("reversescale") else (v - lo) / (hi - lo or 1))
            ink = ink_on("#" + "".join(f"{round(x):02x}" for x in fill)) if fill else None
            out.append(f"<span style='color:{ink}'>{shown}</span>" if ink else shown)
        rows.append(out)
    hover = trace.get("hovertemplate") or ""
    if "%{text" in hover:                   # the hover keeps the plain label, not the coloured span
        if trace.get("customdata") is not None:
            return
        trace["customdata"] = labels.tolist()
        trace["hovertemplate"] = re.sub(r"%\{text(:[^}]*)?\}", r"%{customdata\1}", hover)
    trace["text"], trace["texttemplate"] = rows, "%{text}"


def _inside_label_inks(trace: dict) -> None:
    """Labels printed inside bars or pie slices get the ink that reads best on that bar's or slice's colour."""
    if trace.get("type") == "bar" and trace.get("textposition") == "inside":
        fill = (trace.get("marker") or {}).get("color")
    elif trace.get("type") == "pie" and trace.get("textposition") == "inside":
        fill = (trace.get("marker") or {}).get("colors")
    else:
        return
    if isinstance(fill, str):
        ink = ink_on(fill)
    elif isinstance(fill, (list, tuple, np.ndarray)) and len(fill):
        inks = [ink_on(c) for c in fill]
        ink = inks if all(inks) else None
    else:
        ink = None
    if ink:
        trace.setdefault("textfont", {})["color"] = ink


MAP_LABEL = "map-label"      # meta of a scattergeo text trace whose labels sit on the coloured states


def _map_label_inks(trace: dict, data: list) -> None:
    """Numbers printed on the states of a map get the ink that reads best on each state's own colour.

    The label trace carries the state's value in customdata; its map (the choropleth on the same geo axis)
    says how that value becomes a colour. Worked out after the dark-mode swap, so a state that is dark
    teal in the light theme and light teal in the dark one gets white and navy respectively.
    """
    if trace.get("type") != "scattergeo" or trace.get("meta") != MAP_LABEL or trace.get("customdata") is None:
        return
    geo = trace.get("geo", "geo")
    chor = next((t for t in data if t.get("type") == "choropleth" and t.get("geo", "geo") == geo), None)
    if not chor or not isinstance(chor.get("colorscale"), (list, tuple)):
        return
    zs = _values(chor["z"]).astype(float)
    lo = chor.get("zmin") if chor.get("zmin") is not None else float(np.nanmin(zs))
    hi = chor.get("zmax") if chor.get("zmax") is not None else float(np.nanmax(zs))
    values = _values(trace["customdata"]).astype(float).ravel()
    trace.setdefault("textfont", {})["color"] = inks_on_scale(chor["colorscale"], values, lo, hi, chor.get("zmid"))


def themed(fig: go.Figure, dark: bool) -> dict:
    """The chart exactly as it is drawn on the page, for the viewer's theme (a plain figure dict).

    * dark: every palette colour is swapped for its dark step (dark_variant);
    * the paper, plot and map backgrounds are transparent, so the chart sits on its card's own surface
      colour (set by the stylesheet, which follows the theme the moment it changes);
    * labels printed on coloured marks (heatmap cells, inside bars, pie slices, the states of a map) get deep
      navy or white, whichever reads better on that mark (at least 4.5:1 for the palette colours).
    The figure the engine returned is not changed.
    """
    out = dark_variant(fig) if dark else go.Figure(fig).to_plotly_json()   # both are copies
    layout = out.setdefault("layout", {})
    layout["paper_bgcolor"] = layout["plot_bgcolor"] = CLEAR
    for key in [k for k in layout if k.startswith("geo")]:
        layout[key]["bgcolor"] = CLEAR
    for trace in out.get("data", []):
        if trace.get("type") == "heatmap":
            _heatmap_cell_inks(trace, layout)
        elif trace.get("type") == "scattergeo":
            _map_label_inks(trace, out.get("data", []))
        else:
            _inside_label_inks(trace)
    return out
