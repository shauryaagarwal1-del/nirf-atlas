"""ChartResult: the one thing every analysis engine returns.

Every engine function (core/engines/*.py) answers one kind of question and hands back the same
five pieces, so the dashboard pages and the chatbox can show any answer in the same way:
the chart, the numbers behind it, a one-line answer, how it was calculated, and the chart type.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import plotly.graph_objects as go


@dataclass
class ChartResult:
    fig: go.Figure          # the Plotly chart, already styled with the "nirf" template
    table: pd.DataFrame     # the exact rows/numbers the chart is drawn from
    insight: str            # 1-2 sentence plain-English answer, computed from the data
    method: str             # how it was calculated, in plain words (viva material)
    chart_type: str         # a name exactly as listed in docs/allowed_charts.md, e.g. "multi-series line chart"
