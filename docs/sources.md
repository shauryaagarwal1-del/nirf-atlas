# Data sources and licences

Every file in NIRF Atlas that we did not create ourselves, where it came from, and the terms under which we use it.

## NIRF rankings 2017–2025

- **Source:** National Institutional Ranking Framework, Ministry of Education, Government of India,
  https://www.nirfindia.org (every chart carries the note "Source: NIRF, Ministry of Education, Govt. of India").
- **What we use:** the published ranking tables, downloaded by `scraper/` into `data/raw/` and cleaned by
  `pipeline/` into `data/processed/nirf_master.parquet`. Details: `docs/source_map.md` and `docs/cleaning_report.md`.

## Map of India: state boundaries

| | |
|---|---|
| File in this repository | `assets/india_states.geojson` (2.2 MB, 37 polygons, EPSG:4326 longitude/latitude) |
| Source repository | [datta07/INDIAN-SHAPEFILES](https://github.com/datta07/INDIAN-SHAPEFILES) |
| Source file URL | https://raw.githubusercontent.com/datta07/INDIAN-SHAPEFILES/master/INDIA/INDIA_STATES.geojson |
| Source commit of the file | `7b003e3e8c35491fadf71ced7f168f18a7423bf3` (21 February 2022) |
| Licence | **MIT License**, Copyright (c) 2022 (the repository's `LICENSE` file) |
| Downloaded | 4 November 2026 |
| SHA-256 of our copy | `c5956ba39e399eeb0897873331cfd1faf998c7958159c10aa549db02d5e70446` |

- **Coverage:** the current states and union territories, including **Telangana** (separate from Andhra Pradesh since
  2014) and **Ladakh** (separate from Jammu and Kashmir since 2019). The polygon name is the property `STNAME_SH`
  (e.g. "Jammu & Kashmir", "Andaman & Nicobar").
- **One known difference:** Dadra and Nagar Haveli and Daman and Diu, merged into one UT in January 2020, are still
  two polygons in the file. We keep the file as it is and paint both polygons with the merged UT's value.
- **How our state names are matched:** never by editing the GeoJSON. The `geo_name` column of
  `data/mappings/state_map.csv` gives the polygon name for each state spelling; `tests/test_geo.py` checks that every
  state in our data, and every official state/UT in the mapping, has a polygon, and that every polygon is used.
- **Changes made when loading (in memory only, `core/geo.py`):** coordinates rounded to 3 decimals (about 100 m,
  below one pixel on an all-India map), polygon rings turned clockwise as Plotly's map renderer expects, and slivers
  that rounding shrinks to zero area dropped. The file on disk is the original download.
- **Note on boundaries:** the map is a visual aid for comparing states; boundaries are as drawn in the open-source
  file above and are not an official map of India.

### Licence text (MIT)

```
MIT License

Copyright (c) 2022

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
