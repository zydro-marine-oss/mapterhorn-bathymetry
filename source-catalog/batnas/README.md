# BATNAS (`batnas`)

Indonesia's national bathymetry grid, about 6 arc-seconds (~180 m), mean sea level. The sheet index is public (`portal-web/batnas.json`). Downloading a sheet needs a short-lived token from a logged-in session on tanahair.indonesia.go.id.

From `pipelines/`:

    BATNAS_TOKEN='…' python3 ../source-catalog/batnas/download.py

The script writes GeoTIFFs into `source-store/batnas/`. Then run the rest of the Justfile steps (`source_to_4326.py` onward), or run `just` after the token step if you add the download yourself. No token is stored in the repo. BIG's terms say the data may not be resold; confirm redistribution of derived tiles before publishing.

Run from `pipelines/` with `just ../source-catalog/batnas/`.
