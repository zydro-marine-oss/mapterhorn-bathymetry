# New Zealand coastal 1 m DEM (`nz_coastal`)

1 m bare-earth DEMs from the public `nz-coastal` bucket operated for LINZ. The bucket also holds coarser grids and surface models; this list keeps paths containing `dem_1m`. Neighbouring surveys sometimes repeat a sheet id, so the local filename includes the survey name. Elevations are NZVD2016. CC-BY 4.0. `domain` is ocean, so the coastline mask keeps the seabed and leaves land to the existing `nz` source.

Refresh the list with `create_file_list.py`.

Run from `pipelines/` with `just ../source-catalog/nz_coastal/`.
