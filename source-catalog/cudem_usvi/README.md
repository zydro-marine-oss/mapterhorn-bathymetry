# NOAA NCEI CUDEM topobathy (US Virgin Islands) (`cudem_usvi`)

NOAA NCEI coastal topobathy DEMs (CUDEM). Each dataset is the set of GeoTIFF URLs in that dataset's urllist on the NOAA coastal lidar bucket. NCEI publishes a roughly 1/9 arc-second grid nearshore and a 1/3 arc-second grid outside it. Elevations are as published (commonly NAVD88, or the local vertical datum named in the dataset metadata). This catalog does not shift them onto a chart datum.

Tiles are reprojected to EPSG:4326 before aggregation so one source can hold every tile.

Run from `pipelines/` with `just ../source-catalog/cudem_usvi/`.
