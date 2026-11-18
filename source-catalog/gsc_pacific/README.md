# Canada west coast DEM (`gsc_pacific`)

10 m topo-bathymetric model of the British Columbia coast, published by NRCan as one file geodatabase. Preparation tiles that geodatabase into 8192-pixel windows, drops empty windows, and reprojects the rest to EPSG:4326. The raster is large; expect a long download and a long tile step. Open Government Licence – Canada. The record describes the vertical datum as chart datum (lower low water, large tide) for the bathymetry.

Run from `pipelines/` with `just ../source-catalog/gsc_pacific/`.
