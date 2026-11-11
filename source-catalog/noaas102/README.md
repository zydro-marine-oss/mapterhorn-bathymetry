# NOAA S-102 (`noaas102`)

High-resolution US coastal and Great Lakes bathymetry from NOAA Office of Coast Survey S-102 Bathymetric Surface products on AWS:

https://noaa-s102-pds.s3.amazonaws.com/README.html

## Prep notes

- Source files are S-102 Edition 3.0.0 HDF5 (`.h5`). `source_s102_to_cog.py` converts band 1 to elevation (positive up), reprojects to EPSG:4326 (tiles ship in mixed UTM zones), and writes LERC GeoTIFFs with nodata `-9999`.
- `"domain": "ocean"` — shoreline-masked to water and capped at 0 MSL during aggregation.
- `"priority": 1` — preferred over GEBCO when maxzoom ties (S-102 also usually wins via higher native resolution / maxzoom).
- Vertical values are relative to chart datums (often MLLW), not MSL — expect a vertical offset vs GEBCO until datum adjustment is added.
- Refresh `file_list.txt` with `python create_file_list.py` when NOAA publishes new tiles.
