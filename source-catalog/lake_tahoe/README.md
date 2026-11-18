# Lake Tahoe bathymetry (`lake_tahoe`)

10 m bathymetric grid from USGS Digital Data Series 55, distributed as an ARC/INFO interchange file (`.e00.gz`). The grid is UTM zone 10, metres above sea level. Preparation parses the GRD section, stamps EPSG:32610, and reprojects to EPSG:4326. Not shifted to the lake surface. `domain` is `both`.

Run from `pipelines/` with `just ../source-catalog/lake_tahoe/`.
