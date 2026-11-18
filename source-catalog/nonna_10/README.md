# CHS NONNA-10 (`nonna_10`)

10 m non-navigational bathymetry. The file list is one WCS GetCoverage request per polygon in the official NONNA-10 index shapefile (`NONNA10.zip` on the Open Government record). Requests use EPSG:4326 and the cell envelope. The CHS licence restricts redistribution and forbids navigation; read the licence PDF linked from that record before publishing tiles.

Refresh with `create_file_list.py` after downloading a new index.

Run from `pipelines/` with `just ../source-catalog/nonna_10/`.
