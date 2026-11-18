# WSV DGM-W (`dgm_w`)

Every GeoTIFF zip in the WSV INSPIRE elevation download table for the federal waterway terrain model (DGM-W), contours excluded. The publisher stores orthometric height in NHN, not depth below chart datum, and tiles use more than one projected CRS. Preparation reprojects them to EPSG:4326 and does not apply a chart-datum surface. Attribute Wasserstraßen- und Schifffahrtsverwaltung des Bundes under GeoNutzV. Inland reaches sit well above sea level; `domain` ocean will drop them where the coastline mask says land, and will cap water pixels at 0.

Run from `pipelines/` with `just ../source-catalog/dgm_w/`.
