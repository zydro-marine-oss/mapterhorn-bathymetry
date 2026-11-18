# INFOMAR 10 m (`infomar_10m`)

Merged inshore bathymetry for Irish waters, 10 m, WGS 84, lowest astronomical tide, from Geological Survey Ireland's marine download service. The GeoTIFF is inside one zip. The file name says WGS84; `source_to_4326.py` assigns that CRS if the file does not already carry it only when the raster is already geographic. If the zip has no CRS tag, set it with `source_set_crs.py infomar_10m EPSG:4326` before the warp.

Run from `pipelines/` with `just ../source-catalog/infomar_10m/`.
