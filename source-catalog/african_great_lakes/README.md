# African Great Lakes bathymetry (`african_great_lakes`)

Bathymetric raster archive (`Bathymetric_Rasters.7z`) from Harvard Dataverse doi:10.7910/DVN/ITCOGT, CC0. The archive is the gridded product; the same dataset also holds sounding tables, which are not fetched. `domain` is `both` because these lakes are inland of the coastline mask. Resolution is on the order of 50–100 m depending on the lake. Whether the rasters store depth or elevation is the sign in the files themselves; check a tile before treating the values as elevation.

Run from `pipelines/` with `just ../source-catalog/african_great_lakes/`.
