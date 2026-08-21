# Mapterhorn (bathymetry)

Public terrain **and** bathymetry tiles for interactive web map visualizations. This workspace extends [Mapterhorn](https://github.com/mapterhorn/mapterhorn) so the same Terrarium PMTiles surface can show seafloor depths as well as land elevations.

## What changed vs upstream

- **Shoreline masking** — S2Coast-2023 + GSHHG Antarctica decide land vs ocean so land DEMs (often ocean=`0`) do not block bathymetry.
- **Source `domain`** — `land` (default), `ocean`, `both`, or `mask` in `source-catalog/*/metadata.json`.
- **Bathymetry catalog** — GEBCO 2026, BathDNN25, EMODnet, NOAA BlueTopo, GMRT, plus helpers for NONNA / AusSeabed / LINZ.
- **Unattended ops** — `mapterhorn status`, heartbeats in `meta-store/run-status.json`, `.failed` items with `mapterhorn retry-failed`, and `mapterhorn preflight`.

## Repository layout

| Path | Role |
|------|------|
| [source-catalog/](source-catalog/) | Per-source download lists, metadata, prep recipes |
| [pipelines/](pipelines/) | Download → aggregate → downsample → bundle (`uv run mapterhorn`) |
| [website/](website/) | Static site (viewer, coverage, attribution) |

## Run the pipeline

From `pipelines/` (`uv run mapterhorn` prints the cheat sheet):

```bash
cd pipelines
uv sync
cp env.example .env                 # required; gitignored
# edit .env → MAPTERHORN_DATA_ROOT=/path/outside/git
uv run mapterhorn storage              # confirm data disks
uv run mapterhorn jobs autodownload -y # download + prep (SQLite jobs; resumable)
uv run mapterhorn covering             # plan tiles
# two terminals:
uv run mapterhorn downloader           # copy rasters into tmp as aggregate needs them
uv run mapterhorn aggregate
uv run mapterhorn downsample
uv run mapterhorn bundle --version 1
```

`uv run mapterhorn all --version 1` is covering through bundle. It does **not** download sources.

See [pipelines/README.md](pipelines/README.md) for what each command does, hardware notes, and bathymetry behavior. See [source-catalog/README.md](source-catalog/README.md) for how to add sources. Architecture overview: [ARCHITECTURE.md](ARCHITECTURE.md).

## Requirements

- GDAL (`gdalwarp`, `gdal_translate`, `gdal_rasterize`, `ogr2ogr`, …)
- [uv](https://github.com/astral-sh/uv), wget
- **SSD** for `source-store/`, `aggregation-store/`, `tmp-store/` (~2 GiB RAM per worker thread)
- **HDD** for `pmtiles-store/`, `bundle-store/`, `tar-store/` (large sequential output)

Set `MAPTERHORN_DATA_ROOT` in [`pipelines/.env`](pipelines/env.example) (copy from `env.example`; `.env` is gitignored). The pipeline **refuses to run** if data would land inside the git checkout. Check with `uv run mapterhorn storage`. Wipe stores with `uv run mapterhorn clear-storage -y`. Details in [pipelines/README.md](pipelines/README.md) → Hardware.

## License notes

Catalog policy is unchanged: commercial-OK, no share-alike. OSM coastlines (ODbL) are not used; S2Coast (CC BY 4.0) is the primary shoreline. Always verify per-product attribution in each source's `LICENSE.pdf` / `metadata.json`.
