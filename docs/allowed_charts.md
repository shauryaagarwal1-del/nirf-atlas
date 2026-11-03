# Allowed chart types

Every chart in NIRF Atlas must be one of the chart types taught in the DHV course, listed below, so that we can
explain each one in the viva. If the ideal chart for a question is not on this list, we use the closest allowed
type and say why in `docs/methods.md`.

The name in backticks is the exact value an engine puts in `ChartResult.chart_type`
(`tests/test_engines.py` reads this file and fails if an engine returns any other name).
Text after the dash lists the variants that count as the same chart type.

Not allowed (not taught): Sankey, radar/spider, parallel coordinates, treemap, sunburst, waterfall, funnel,
slope and dumbbell charts, and anything else not listed here.

## Comparisons and proportions
- `bar chart` - vertical, horizontal or ranked (sorted) bars
- `grouped bar chart`
- `stacked bar chart`
- `small-multiple bar charts`
- `dot plot` - linear or log scale
- `lollipop chart`
- `pie chart`
- `polar area chart` - also called a rose diagram

## Distributions
- `histogram` - equal-width or equal-frequency bins
- `stacked histogram`
- `overlapping histogram`
- `histogram with density curve`
- `KDE plot`
- `ECDF plot`
- `rank plot`
- `point plot with error bars`
- `box-and-whisker plot`
- `violin plot`
- `strip chart`
- `jittered strip chart`

## Relationships and matrices
- `scatterplot` - plain, grouped by colour/shape, or transparency-adjusted
- `bubble chart`
- `connected scatterplot`
- `matrix heatmap`
- `correlogram` - a correlation heatmap
- `confusion-matrix style table`

## Time series
- `time-series dot plot`
- `line chart` - with or without markers
- `multi-series line chart`
- `vertically aligned time-series charts`
- `area chart`
- `moving-average plot`
- `fitted curves`
- `LOWESS scatterplot`

## Maps
- `choropleth map`
- `proportional-symbol map` - also called a bubble map

## Others
- `PCA scatterplot`
- `process flowchart`
