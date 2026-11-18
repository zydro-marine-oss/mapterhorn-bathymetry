# Global Lake Database v2 (`gldb`)

30 arc-second global lake-depth grid (`GlobalLakeDepth.dat` in `gldbv2.tar.gz`). The archive's own text file describes the layout: little-endian int16, decimetres, 43200 by 21600, north row first, 0 where there is no lake. Preparation stores elevation in metres (depth negated) and writes 0 as nodata. Much of the grid is a mean depth or a default, not a surveyed bed; the archive's lake list says which lakes have bathymetry. The grid is coarser than GEBCO, and the current merge keeps the finer source, so these cells will not replace GEBCO where both have a value. `domain` is `both`. CC-BY.

Run from `pipelines/` with `just ../source-catalog/gldb/`.
