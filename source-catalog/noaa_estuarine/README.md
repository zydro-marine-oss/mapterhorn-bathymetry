# NOAA estuarine bathymetric DEMs (`noaa_estuarine`)

30 m estuarine DEMs from NCEI's THREDDS `regional` catalog: every NetCDF whose name ends in `_30m.nc`. Elevations are the values in those files (local tidal datums, often mean lower low water). Other regional DEMs on the same server that are not named `_30m` are not included.

Run from `pipelines/` with `just ../source-catalog/noaa_estuarine/`.
