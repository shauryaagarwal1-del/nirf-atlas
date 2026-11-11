"""India state boundaries for the choropleth maps, and the link from our state names to the map's polygons.

The boundaries are `assets/india_states.geojson` (current states and UTs, including Telangana and Ladakh;
source and licence in docs/sources.md). The file is used exactly as downloaded; names are matched through
the hand-checked `geo_name` column of data/mappings/state_map.csv, never by editing the GeoJSON:
  * `geo_name` is the polygon name (the GeoJSON property STNAME_SH) for each spelling of a state,
    e.g. "Jammu and Kashmir" -> "Jammu & Kashmir";
  * the file still draws Dadra and Nagar Haveli and Daman and Diu (one UT since January 2020) as its two
    old polygons, so that UT has two polygon names and both are painted with the merged UT's value.

When the file is loaded (the file itself is unchanged), coordinates are rounded to 3 decimals (about
100 m on the ground, far below one pixel on an all-India map) to keep each map light in the browser, and
each polygon's rings are turned the way Plotly's map renderer expects (see _polygon()).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
GEOJSON_PATH = ROOT / "assets" / "india_states.geojson"
STATE_MAP_PATH = ROOT / "data" / "mappings" / "state_map.csv"
GEO_PROPERTY = "STNAME_SH"                       # the GeoJSON property that names a state polygon
FEATURE_KEY = f"properties.{GEO_PROPERTY}"       # Plotly's featureidkey for that property


def _signed_area(ring) -> float:
    """Shoelace formula: positive when the ring runs counter-clockwise (in lon/lat)."""
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:])) / 2


def _polygon(rings, digits: int = 3) -> list:
    """Round one polygon's rings and orient them the way Plotly's map renderer (d3-geo) reads them.

    d3-geo takes a CLOCKWISE outer ring as "this shape"; a counter-clockwise outer ring means "the whole
    globe except this shape" and paints the entire map. So the outer ring is made clockwise and the
    holes counter-clockwise (the opposite of the GeoJSON standard's right-hand rule, which the file follows).
    A ring that rounding shrinks to zero area (an islet smaller than about 100 m) is dropped; returns None
    when that happens to the outer ring.
    """
    out = []
    for i, ring in enumerate(rings):
        ring = [[round(x, digits), round(y, digits)] for x, y in ring]
        area = _signed_area(ring)
        if area == 0:
            if i == 0:
                return None
            continue
        if (area < 0) != (i == 0):
            ring = ring[::-1]
        out.append(ring)
    return out


def _geometry(geom: dict) -> dict:
    if geom["type"] == "Polygon":
        return {"type": "Polygon", "coordinates": _polygon(geom["coordinates"])}
    parts = [_polygon(p) for p in geom["coordinates"]]
    return {"type": "MultiPolygon", "coordinates": [p for p in parts if p]}


@lru_cache(maxsize=1)
def india_geojson() -> dict:
    """The India states GeoJSON, ready for Plotly: coordinates rounded to 3 decimals, rings oriented for
    d3-geo, attributes trimmed to the polygon name. The file on disk is not changed."""
    raw = json.loads(GEOJSON_PATH.read_text(encoding="utf-8"))
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {GEO_PROPERTY: f["properties"][GEO_PROPERTY]},
         "geometry": _geometry(f["geometry"])} for f in raw["features"]]}


def polygon_names() -> list[str]:
    """Every polygon name in the GeoJSON, in file order."""
    return [f["properties"][GEO_PROPERTY] for f in india_geojson()["features"]]


def _ring_centroid(ring) -> tuple[float, float, float]:
    """(lon, lat, area) of one ring: the area-weighted centre of its polygon (shoelace formula)."""
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if a == 0:
        return ring[0][0], ring[0][1], 0.0
    return cx / (3 * a), cy / (3 * a), abs(a) / 2


@lru_cache(maxsize=1)
def polygon_centroids() -> dict[str, tuple[float, float, float]]:
    """Polygon name -> (lon, lat, area) of its largest part: where a number printed on that state goes.

    The largest outer ring decides (an island chain's label sits on its biggest island); area is in
    square degrees, used only to tell big states from the small places whose label needs a callout.
    """
    out = {}
    for f in india_geojson()["features"]:
        g = f["geometry"]
        polygons = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        out[f["properties"][GEO_PROPERTY]] = max((_ring_centroid(p[0]) for p in polygons), key=lambda c: c[2])
    return out


def state_centroids() -> dict[str, tuple[float, float, float]]:
    """Official state/UT name -> (lon, lat, area) of its largest polygon (the merged UT: its bigger part)."""
    cents = polygon_centroids()
    return {state: max((cents[p] for p in polys), key=lambda c: c[2]) for state, polys in state_polygons().items()}


@lru_cache(maxsize=1)
def state_polygons() -> dict[str, tuple[str, ...]]:
    """Official state/UT name -> the polygon name(s) that draw it, from the geo_name column of state_map.csv."""
    smap = pd.read_csv(STATE_MAP_PATH, keep_default_na=False)
    out: dict[str, list[str]] = {}
    for std, geo in zip(smap["state_std"], smap["geo_name"]):
        for name in geo.split(";"):
            if name.strip() and name.strip() not in out.setdefault(std, []):
                out[std].append(name.strip())
    return {k: tuple(v) for k, v in out.items()}


def polygon_frame(values: pd.DataFrame, state_col: str = "state") -> pd.DataFrame:
    """Repeat each state's row once per polygon that draws it, with the polygon name in column `polygon`.

    States without a polygon raise a ValueError (tests/test_geo.py checks every state in the data has one).
    """
    polys = state_polygons()
    missing = sorted(set(values[state_col]) - set(polys))
    if missing:
        raise ValueError(f"No map polygon for {missing}: add a geo_name to data/mappings/state_map.csv.")
    out = values.assign(polygon=values[state_col].map(polys)).explode("polygon")
    return out.reset_index(drop=True)
