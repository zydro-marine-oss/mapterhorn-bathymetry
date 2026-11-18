# Bathymetry sources

Public bathymetry and lake surveys added beside GEBCO and NOAA S-102. Finer native resolution wins. `priority` only breaks a tie, which is how `noaas102` is preferred to `gebco` when the zoom matches. Ocean sources are masked to the coastline and capped at 0. Lake surveys use `domain: both`, because that mask treats lakes as land.

Elevations are stored as published. This catalog does not apply a separation grid or a lake-surface offset. Vertical datums therefore still differ (mean sea level, lowest astronomical tide, chart datum, NAVD88, NAP, Ordnance Datum Newlyn, NHN, LN02). Do not navigate with the tiles.

## Inventory

| Source | Fetched | Licence | What it is |
| --- | --- | --- | --- |
| gebco | yes (already in the catalog) | Public domain / Open Government Licence | Global 2026 grid, mean sea level |
| noaas102 | yes (already in the catalog) | US Government work | US S-102 surfaces, chart datum, priority 1 on a zoom tie |
| emodnet | yes | CC-BY 4.0 | 2024 European DTM, ~115 m, lowest astronomical tide. 58 tiles that exist on the EMODnet download host |
| cudem | yes | US Government work | NCEI 2014 topobathy for CONUS and Alaska, 1/9 and 1/3 arc-second |
| cudem_pr | yes | US Government work | NCEI topobathy, Puerto Rico |
| cudem_usvi | yes | US Government work | NCEI topobathy, US Virgin Islands |
| cudem_hawaii | yes | US Government work | NCEI topobathy, Hawaii |
| cudem_guam | yes | US Government work | NCEI topobathy, Guam |
| cudem_cnmi | yes | US Government work | NCEI topobathy, Northern Mariana Islands |
| cudem_amsam | yes | US Government work | NCEI topobathy, American Samoa |
| noaa_estuarine | yes | US Government work | NCEI 30 m estuarine DEMs (`*_30m.nc` on the regional THREDDS server) |
| great_lakes | yes | US Government work | NCEI low-water-datum grids for the five Great Lakes. `domain: both` |
| infomar_10m | yes | CC-BY 4.0 | Geological Survey Ireland, 10 m inshore, lowest astronomical tide |
| infomar_25m | yes | CC-BY 4.0 | Geological Survey Ireland, 25 m shelf, lowest astronomical tide |
| kartverket_50m | yes | CC-BY 4.0 | Kartverket 50 m cells from the Geonorge TIFF Atom feed |
| vaklodingen | yes | CC0 | Rijkswaterstaat 20 m grid, NAP |
| uk_surfzone | yes | Open Government Licence v3 | Environment Agency 2 m SurfZone DEM 2019 |
| uk_multibeam | yes | Open Government Licence v3 | Environment Agency coastal multibeam tiles |
| nz_coastal | yes | CC-BY 4.0 | LINZ 1 m coastal DEMs from the public `nz-coastal` bucket |
| ausbathytopo | yes | CC-BY 4.0 | AusSeabed 250 m compilation |
| gbr30 | yes | CC-BY 4.0 | AusSeabed / Beaman 30 m Great Barrier Reef grid, 2020 |
| swiobc | yes | CC-BY 3.0 | Southwest Indian Ocean compilation on PANGAEA |
| gsc_atlantic | yes | Open Government Licence – Canada | NRCan 100 m GeoTIFF, Scotian Shelf and Newfoundland-Labrador |
| gsc_pacific | yes | Open Government Licence – Canada | NRCan 10 m west-coast model, file geodatabase, tiled during preparation |
| dgm_w | yes | GeoNutzV | All WSV DGM-W GeoTIFF zips from the INSPIRE elevation table. Heights are NHN |
| nonna_10 | yes | CHS NONNA licence | One WCS request per cell of the official NONNA-10 index |
| nonna_100 | yes | CHS NONNA licence | One WCS request per cell of the official NONNA-100 index |
| african_great_lakes | yes | CC0 | Dataverse raster archive doi:10.7910/DVN/ITCOGT. `domain: both` |
| lac_leman | yes | swisstopo open data | swissBATHY3D, LN02 orthometric bed. `domain: both` |
| lac_neuchatel | yes | swisstopo open data | swissBATHY3D, LN02 orthometric bed. `domain: both` |
| bodensee | yes | CC-BY 3.0 | Lake Constance 3 m model, DHHN92, PANGAEA. `domain: both` |
| lake_tahoe | yes | US Government work | USGS DDS-55 ARC/INFO grid, UTM zone 10. `domain: both` |
| gldb | yes | CC-BY | Global Lake Database v2, 30 arc-second depths. `domain: both` |
| batnas | token required | BIG terms, no resale | Sheet index is public. Each GeoTIFF needs `BATNAS_TOKEN` |
| ddm | not fetched | SDFI terms | No stable file URL on the Dataforsyningen page |
| litto3d_bretagne | not fetched | Licence Ouverte / Etalab | Official page is Shom's diffusion site; no stable file list |
| uk_cco | not fetched | Open Government Licence | Channel Coastal Observatory basket, no stable file URL |
| uk_cco_doris | not fetched | Crown copyright, reuse except navigation | Same basket as the CCO surveys |

## Attribution

- EMODnet Bathymetry Consortium, CC-BY 4.0.
- NOAA NCEI for CUDEM, the estuarine DEMs, and the Great Lakes grids. NOAA Office of Coast Survey for S-102.
- Geological Survey Ireland and the Marine Institute (INFOMAR), CC-BY 4.0.
- Kartverket, CC-BY 4.0.
- Rijkswaterstaat, CC0, for Vaklodingen.
- Environment Agency, Open Government Licence, for SurfZone and coastal multibeam.
- Toitū Te Whenua Land Information New Zealand, CC-BY 4.0.
- Geoscience Australia / AusSeabed, and R. Beaman for the reef grid, CC-BY 4.0.
- Dorschel et al. / Alfred Wegener Institute, CC-BY 3.0, for the southwest Indian Ocean compilation.
- Geological Survey of Canada / Natural Resources Canada, Open Government Licence – Canada.
- Wasserstraßen- und Schifffahrtsverwaltung des Bundes, GeoNutzV.
- Canadian Hydrographic Service. The NONNA licence limits redistribution and is not for navigation. The licence PDF is linked from the Open Government record.
- Hamilton et al. 2022, CC0, doi:10.7910/DVN/ITCOGT.
- swisstopo for swissBATHY3D.
- IGKB / Wessels et al. via PANGAEA, CC-BY 3.0, for Lake Constance.
- USGS for Lake Tahoe (DDS-55).
- Kourzeneva and Choulga for Global Lake Database v2, CC-BY.
- Badan Informasi Geospasial for BATNAS.
- GEBCO Compilation Group.

## Open questions

- **CHS NONNA.** The licence restricts what can be passed on and forbids navigation. Decide whether derived tiles may be published before building them.
- **BATNAS.** BIG's terms include a no-resale condition. Downloads need `BATNAS_TOKEN` from a logged-in session at tanahair.indonesia.go.id. The token is not stored in the repo.
- **Danmarks Dybdemodel, Litto3D Bretagne, CCO multibeam, and DORIS** are catalogued but not fetched. Their publishers do not offer a stable anonymous file URL that this pipeline can call. Add a file list only from the publisher, not from a third-party copy.
- **Vertical datums are not aligned.** CUDEM stays on the datum in the NCEI files. EMODnet and INFOMAR are lowest astronomical tide. Kartverket mixes chart datum and mean sea level. Lake grids are orthometric bed elevation (or, for GLDB, depth below the lake surface). The ocean-domain cap at 0 still removes drying heights above 0.
- **Coarser surveys lose to finer ones.** GLDB (~930 m) will not replace GEBCO where both have a value. A 2 m lake grid will not replace a 0.5 m land DEM over that lake. Changing that would mean a different merge rule than the one this fork already uses.
- **WSV DGM-W** is NHN elevation for the whole waterway model, including inland reaches that are far above sea level. `domain: ocean` drops land pixels and caps the rest at 0, which is a poor description of an inland river bed.
- **GSC Atlantic** does not publish one vertical datum for the whole compilation.
- **African Great Lakes** rasters should be checked for sign (depth versus elevation) on a sample tile before a production build.
- **GSC Pacific** preparation tiles an official file geodatabase. That step is long and has not been run here.
