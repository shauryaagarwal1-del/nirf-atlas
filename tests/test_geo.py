"""Map tests (Phase 11): the India GeoJSON and the link from our state names to its polygons.

Checked:
  * assets/india_states.geojson is a FeatureCollection of current states/UTs (Telangana and Ladakh included);
  * EVERY state in the master table has a matching polygon, through the geo_name column of
    data/mappings/state_map.csv (names are fixed there, never by editing the GeoJSON);
  * every polygon of the file is used by some state, so no part of India stays unpainted by mistake;
  * the loaded boundaries are oriented the way Plotly's map renderer expects (outer rings clockwise),
    otherwise a state would paint the whole globe.

    python -m pytest tests/test_geo.py -v
"""

import json

import pandas as pd
import pytest

from core.data import MASTER_PATH, load_master
from core.geo import (GEO_PROPERTY, GEOJSON_PATH, STATE_MAP_PATH, _signed_area, india_geojson, polygon_frame,
                      polygon_names, state_polygons)


@pytest.fixture(scope="module")
def raw() -> dict:
    return json.loads(GEOJSON_PATH.read_text(encoding="utf-8"))


def test_geojson_has_current_states(raw):
    assert raw["type"] == "FeatureCollection"
    names = {f["properties"][GEO_PROPERTY] for f in raw["features"]}
    assert {"Telangana", "Andhra Pradesh", "Ladakh", "Jammu & Kashmir", "Delhi", "Puducherry"} <= names
    assert all(f["geometry"]["type"] in ("Polygon", "MultiPolygon") for f in raw["features"])


@pytest.mark.skipif(not MASTER_PATH.exists(), reason="run `python -m pipeline.clean` first")
def test_every_state_in_the_data_has_a_polygon():
    polys, names = state_polygons(), set(polygon_names())
    data_states = set(load_master()["state"].dropna())
    missing = sorted(data_states - set(polys))
    assert not missing, f"no geo_name in state_map.csv for {missing}"
    for s in data_states:
        assert polys[s] and set(polys[s]) <= names, (s, polys[s])


def test_every_official_state_maps_to_existing_polygons():
    smap = pd.read_csv(STATE_MAP_PATH, keep_default_na=False)
    assert smap["geo_name"].ne("").all()
    names = set(polygon_names())
    for std, polys in state_polygons().items():
        assert set(polys) <= names, (std, polys)
    assert set(smap["state_std"]) == set(state_polygons())


def test_every_polygon_is_used():
    used = {p for polys in state_polygons().values() for p in polys}
    assert used == set(polygon_names())


def test_merged_ut_is_drawn_by_both_old_polygons():
    polys = state_polygons()["Dadra and Nagar Haveli and Daman and Diu"]
    assert set(polys) == {"Dadra & Nagar Haveli", "Daman & Diu"}
    frame = polygon_frame(pd.DataFrame({"state": ["Dadra and Nagar Haveli and Daman and Diu", "Kerala"], "v": [1, 2]}))
    assert frame["polygon"].tolist() == ["Dadra & Nagar Haveli", "Daman & Diu", "Kerala"]
    assert frame["v"].tolist() == [1, 1, 2]


def test_unknown_state_has_no_polygon():
    with pytest.raises(ValueError, match="state_map.csv"):
        polygon_frame(pd.DataFrame({"state": ["Atlantis"]}))


def test_loaded_rings_are_oriented_for_plotly():
    for f in india_geojson()["features"]:
        g = f["geometry"]
        polygons = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        for rings in polygons:
            assert _signed_area(rings[0]) < 0                     # outer ring clockwise
            assert all(_signed_area(r) > 0 for r in rings[1:])   # holes counter-clockwise
