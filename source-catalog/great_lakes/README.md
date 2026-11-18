# NOAA Great Lakes bathymetry (`great_lakes`)

Low-water-datum GeoTIFF archives for Superior, Michigan, Huron, Erie, and Ontario, from the NCEI Great Lakes bathymetry pages. `domain` is `both` because the coastline mask treats these lakes as land. Grid spacing is on the order of 3 arc-seconds and is not the same in every lake. National land DEMs are often finer, so where both exist the finer grid is kept.

Run from `pipelines/` with `just ../source-catalog/great_lakes/`.
