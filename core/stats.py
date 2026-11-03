"""Small statistics helpers shared by the engines, each one explainable in a sentence.

  * describe(): count, mean, median, min, max, standard deviation, quartiles, IQR;
  * correlate(): Pearson r, Spearman rho, their p-values, R squared and the least-squares line;
  * strength() / p_text() / signed(): turn numbers into the plain words used in insights.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def describe(values: pd.Series) -> dict:
    """Standard summary of one numeric column (missing values ignored)."""
    v = pd.Series(values, dtype="float64").dropna()
    q1, q2, q3 = (v.quantile([0.25, 0.5, 0.75]).tolist() if len(v) else [np.nan] * 3)
    return {
        "n": int(len(v)),
        "mean": v.mean(),
        "median": q2,
        "min": v.min(),
        "max": v.max(),
        "std": v.std(ddof=1),       # sample standard deviation (divide by n - 1)
        "q1": q1,
        "q3": q3,
        "iqr": q3 - q1,
        "range": v.max() - v.min(),
        "skew": float(stats.skew(v, bias=False)) if len(v) > 2 else np.nan,
    }


def correlate(x: pd.Series, y: pd.Series) -> dict:
    """Pearson and Spearman correlation of two columns, plus the least-squares line y = a + b*x.

    Pearson r: how close the points are to a straight line (-1 to +1).
    Spearman rho: Pearson computed on the ranks, so it measures any steadily rising/falling pattern
    and is not pulled around by a few extreme values.
    p-value: the chance of a correlation at least this strong if there were truly no relation.
    R squared = r squared: the share of the variation in y that the straight line explains.
    """
    d = pd.DataFrame({"x": x, "y": y}).astype("float64").dropna()
    n = len(d)
    out = {"n": n, "pearson_r": np.nan, "pearson_p": np.nan, "spearman_rho": np.nan,
           "spearman_p": np.nan, "r2": np.nan, "slope": np.nan, "intercept": np.nan}
    if n < 3 or d["x"].nunique() < 2 or d["y"].nunique() < 2:
        return out
    pr = stats.pearsonr(d["x"], d["y"])
    sr = stats.spearmanr(d["x"], d["y"])
    slope, intercept = np.polyfit(d["x"], d["y"], 1)
    out.update(pearson_r=float(pr.statistic), pearson_p=float(pr.pvalue),
               spearman_rho=float(sr.statistic), spearman_p=float(sr.pvalue),
               r2=float(pr.statistic) ** 2, slope=float(slope), intercept=float(intercept))
    return out


def strength(r: float) -> str:
    """Words for the size of a correlation (Evans' scale): |r| < 0.2 very weak ... >= 0.8 very strong."""
    if pd.isna(r):
        return "undefined"
    a = abs(r)
    size = ("very weak" if a < 0.2 else "weak" if a < 0.4 else "moderate" if a < 0.6
            else "strong" if a < 0.8 else "very strong")
    return f"{size} {'positive' if r > 0 else 'negative'}"


def p_text(p: float) -> str:
    """p < 0.001, p = 0.023 ..."""
    if pd.isna(p):
        return "p not defined"
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}"


def places(change: float) -> str:
    """'+1 place', '-14 places' (rank change with the right plural)."""
    return f"{signed(change)} place{'' if abs(change) == 1 else 's'}"


def signed(x: float, digits: int = 0, unit: str = "") -> str:
    """+5, -3.2 (uses a real minus sign) with an optional unit."""
    if pd.isna(x):
        return "n/a"
    x = round(float(x), digits)
    s = f"{abs(x):,.{digits}f}"
    sign = "+" if x > 0 else "−" if x < 0 else "±"
    return f"{sign}{s}{unit}"
