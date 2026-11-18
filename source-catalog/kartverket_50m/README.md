# Kartverket 50 m (`kartverket_50m`)

50 m sea and coastal terrain cells from Geonorge's TIFF Atom feed for `SjoTerrengmodellerDTM50`. Cells are delivered in several UTM zones, so preparation reprojects every tile to EPSG:4326. Kartverket describes inshore cells relative to chart datum and offshore cells relative to mean sea level. Attribute Kartverket, CC-BY 4.0.

Run from `pipelines/` with `just ../source-catalog/kartverket_50m/`.
