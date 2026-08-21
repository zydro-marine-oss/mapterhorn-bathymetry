# Mapterhorn architecture

Mapterhorn turns public elevation and bathymetry rasters into a single interactive map surface: **Terrarium-encoded WebP tiles** packed into **PMTiles**. This document explains how that pipeline works end to end, in plain language.

For operator commands, see [pipelines/README.md](pipelines/README.md). For adding sources, see [source-catalog/README.md](source-catalog/README.md).

---

## What Mapterhorn produces

Clients (web maps, apps) need height at every place on Earth, at many zoom levels. Mapterhorn’s answer is not one giant GeoTIFF. It is a **tile pyramid**:

- Each tile is **512×512** pixels.
- Heights are stored as **Terrarium RGB** (Mapbox Terrarium encoding), compressed as **lossless WebP**.
- Tiles live in **PMTiles** archives (one file can hold a whole zoom range).

This fork also merges **ocean depths** into the same surface as land elevations. Land DEMs often fill the sea with `0`, which would block bathymetry if you simply stacked rasters. A **shoreline mask** keeps land and ocean data on the correct side of the coast.

---

## Big picture

Four stages run in order. Each stage reads from named **stores** on disk and writes to the next.

```text
  source-catalog          (URLs, Justfiles, licenses)
         │
         ▼
  Source pipeline         download → normalize → bounds → coverage → tarball
         │
         ▼
  Covering                plan which tiles need work (aggregation + downsampling)
         │
         ▼
  Aggregation             reproject, merge sources, write local-maxzoom PMTiles
         │                  (downloader stages rasters into tmp-store)
         ▼
  Downsampling            build lower zooms from higher ones
         │
         ▼
  Bundle                  pack single-zoom PMTiles into planet + regional files
```

Typical operator path (from `pipelines/`):

1. `uv run mapterhorn jobs autodownload -y` — enqueue download/prep into SQLite, run process workers (+ shoreline)
2. `uv run mapterhorn covering` — plan work
3. `uv run mapterhorn downloader` (one terminal) + `uv run mapterhorn aggregate` (another)
4. `uv run mapterhorn downsample`
5. `uv run mapterhorn bundle --version 1`

`uv run mapterhorn all --version 1` runs covering through bundle. It does **not** download sources.

See [Source jobs (SQLite)](#source-jobs-sqlite) for resume/retry details. `mapterhorn manage autodownload` is an alias that delegates to the same runner.

---

## Repository layout

| Path | Role |
|------|------|
| `source-catalog/` | One folder per elevation/bathymetry product: download list, prep recipe, metadata, license |
| `pipelines/` | All processing code; run via `uv run mapterhorn` |
| `website/` | Static site (viewer, coverage, attribution) when present |
| Data stores | Live **outside** the git tree under `MAPTERHORN_DATA_ROOT` (see [Hardware and stores](#hardware-and-stores)) |

---

## Data stores

Everything heavy lives in store directories. Paths resolve from `MAPTERHORN_DATA_ROOT`, with optional per-store overrides (e.g. put PMTiles on HDD while sources stay on SSD).

| Store | What it holds |
|-------|----------------|
| **source-store** | Downloaded and normalized GeoTIFFs, per-source `bounds.csv`, readiness markers |
| **mask-store** | Shoreline land polygons (`shoreline/land_3857.gpkg`) used during aggregation |
| **aggregation-store** | Work queues: CSV job files and `.todo` / `.done` / `.failed` markers for each covering run |
| **tmp-store** | Hot scratch: download queue, staged rasters, per-tile GDAL warps |
| **pmtiles-store** | Intermediate single-zoom PMTiles from aggregation and downsampling |
| **bundle-store** | Final distribution files (`planet.pmtiles`, `6-{x}-{y}.pmtiles`) |
| **tar-store** | Per-source tarballs (rasters + metadata) for archive/upload |
| **polygon-store** | Coverage footprints (`{source}.gpkg`) |
| **meta-store** | Checksums, attribution, download URLs, run status / logs, **`jobs.sqlite`** (source job queue) |
| **task-store** | Optional distributed worker request/response files |

**SSD** for random access: `source-store`, `aggregation-store`, `tmp-store`, preferably `mask-store`.  
**HDD** for large sequential data: `pmtiles-store`, `bundle-store`, `tar-store`.

---

## Source catalog

Each product under `source-catalog/{name}/` has:

| File | Purpose |
|------|---------|
| `file_list.txt` | One download URL per line |
| `Justfile` | Ordered prep recipe (parsed by Python; the `just` tool is not required) |
| `metadata.json` | Name, license, producer, resolution, optional **`domain`** |
| `LICENSE.pdf` | License snapshot shipped with the source tarball |

### Domain (land vs ocean)

`metadata.json` may set `"domain"`:

| Domain | Meaning |
|--------|---------|
| `land` | Terrain DEM (default if omitted) |
| `ocean` | Bathymetry — masked to water during aggregation |
| `both` | True topobathy — no shoreline masking |
| `mask` | Shoreline data only (`s2coast`), not elevation |

Aggregation uses this so land and ocean sources paint different pixels along the coast.

---

## Stage 1 — Source pipeline

Goal: turn messy public downloads into **normalized GeoTIFFs** plus indexes the rest of the pipeline can trust.

### Typical prep chain

A catalog Justfile usually does some of:

1. **Download** — `wget` every URL into `source-store/{source}/` (`source_download.py`). Interrupted runs resume with `wget --continue`; the complete marker is written only when every URL succeeds.
2. **Unpack / convert** — unzip/7z, COG-style LERC tiling, CRS/nodata/orientation fixes, or bathymetry-specific helpers (BlueTopo band extract, BathDNN NetCDF → GeoTIFF, GMRT download).
3. **Bounds** — `source_bounds.py` writes `bounds.csv`: each raster’s filename, Web Mercator extent, width, height. Polar extents are clamped to Web Mercator’s valid latitude range.
4. **Polygonize** — union of valid pixels → `polygon-store/{source}.gpkg` (coverage map / tarball).
5. **Tarball** — package LICENSE, metadata, bounds, coverage, and TIFFs into `tar-store/{source}.tar`.

### Two readiness markers

In `source-store/{source}/`:

| Marker | Means |
|--------|--------|
| `DOWNLOAD_COMPLETE` | All catalog URLs are on disk. Unzip may still be running. |
| `READY` | Prep finished (unzip, convert, bounds, polygonize, tarball as required). |

**Covering and the downloader require `READY`.** A half-downloaded or still-extracting source never enters tile planning.

### Source jobs (SQLite)

Source work is tracked in **`meta-store/jobs.sqlite`**, not only in memory. `uv run mapterhorn jobs autodownload -y` (or `manage autodownload -y`) does two things:

1. **Enqueue** — plan download/prep jobs (skip sources already `READY`; prep-only if `DOWNLOAD_COMPLETE` already exists; optional shoreline job).
2. **Serve** — spawn separate **download** and **prep** OS processes that claim jobs from the DB, heartbeat while running, and write markers when done.

| Command | Role |
|---------|------|
| `mapterhorn jobs autodownload -y` | Enqueue + serve until the queue is idle |
| `mapterhorn jobs enqueue autodownload -y` | Plan only |
| `mapterhorn jobs serve` | Resume workers on whatever is still pending |
| `mapterhorn jobs status [--watch]` | Durable counts: pending / running / succeeded / failed |
| `mapterhorn jobs retry` | Requeue failed jobs |
| `mapterhorn jobs reclaim` | Turn stale `running` rows (dead workers) back into `pending` |

Download success still writes `DOWNLOAD_COMPLETE` and enqueues a `source_prep` job. Prep success writes `READY`. Kill the runner mid-flight and run `mapterhorn jobs serve` again — finished sources are not redone.

Defaults: 16 download workers, 4 prep workers. Prep workers set `MAPTERHORN_PREP_POOL_SIZE=1` so unzip/polygonize do not each fork a huge nested process pool. Aggregation covering still uses file-based `.todo` / `.done` / `.failed` (not SQLite yet).

---

## Shoreline mask

Before aggregation can mix land and ocean, land polygons must exist under `mask-store/shoreline/`.

`source_prepare_shoreline.py` (also triggered by autodownload):

1. Downloads **S2Coast-2023** (primary worldwide coastline) and **GSHHG** (Antarctica south of −60°).
2. Builds land polygons and reprojects them to Web Mercator: `land_3857.gpkg`.
3. Writes a coarse overview for tooling; **per-tile masking rasterizes the GPKG**, not a global 30 m raster (that would be enormous).

OSM coastlines are intentionally avoided (share-alike). S2Coast is CC BY 4.0.

---

## Stage 2 — Covering (planning)

Covering answers: *which pieces of Earth need tiles, from which source files, at what resolution?* It writes job CSVs; it does not warp imagery yet.

`uv run mapterhorn covering` runs:

1. **Aggregation covering** (`aggregation_covering.py`)
2. **Downsampling covering** (`downsampling_covering.py`)

### Macrotiles (zoom 12)

Planning uses **zoom-12 Web Mercator tiles** as the unit of geography (“macrotiles”). For every row in every ready source’s `bounds.csv`:

1. Buffer the item’s bbox slightly (edge overlap for blending).
2. Find which z12 tiles it intersects.
3. Compute a **local maxzoom**: the coarsest zoom that still oversamples the source’s native resolution (assuming 512 px tiles). Maxzoom is at least 12.

Macrotiles that share the same set of `(source, maxzoom)` pairs are **grouped**, then **simplified** into larger “aggregation tiles” when parents still share that group — but never larger than a **6-zoom span** (~32768 px wide). That caps memory (~4 GiB of float32 elevation for one job).

Output looks like:

```text
aggregation-store/{run-id}/{z}-{x}-{y}-{child_z}-aggregation.csv
```

Example contents:

```text
source,filename,maxzoom
glo30,Copernicus_DSM_COG_10_N47_00_E009_00_DEM.tif,12
swissalti3d,swissalti3d_2019_2755-1227_0.5_2056_5728.tif,17
```

Here `z/x/y` is the aggregation tile extent; `child_z` is the zoom at which sources are sampled. Dirty jobs vs the previous covering get a `.todo` suffix so only changed regions rebuild.

Downsampling covering walks from high zoom toward zero and writes similar CSVs listing **child PMTiles** that feed each parent overview tile.

---

## Stage 3 — Aggregation (building local-maxzoom tiles)

Aggregation turns planned CSVs into **single-zoom PMTiles** at each region’s local maxzoom.

### Downloader (staging)

Aggregation workers need fast random access to many GeoTIFFs. The **downloader** (`mapterhorn downloader`) runs as a long-lived process:

1. Aggregation drops a CSV into `tmp-store/queue/`.
2. The downloader copies (or optionally symlinks) listed files from `source-store` into `tmp-store/source/`.
3. When staging is done, the CSV moves to `tmp-store/ready/`.
4. Old staged files are pruned when `tmp-store/source` grows past a size cap (default 100 GiB).

Workers wait until their job appears under `ready/`. Sources that are not `READY` are refused.

### Reproject, mask, merge, tile

For each `.todo` aggregation job (`aggregation_run.py`):

1. **Group sources** by priority: **higher maxzoom wins**, then lexicographic source name. Finer data outranks coarser data where both cover the same area.
2. **Reproject** each group with GDAL (`gdalbuildvrt` → `gdalwarp` to EPSG:3857, cubicspline, nodata −9999) into a working GeoTIFF.
3. **Apply domain mask** (`aggregation_mask.py`) *after* warp and *before* deciding “this tile is full”:
   - **ocean** sources: land pixels → nodata  
   - **land** sources: ocean pixels with elevation ≥ 0 → nodata (keeps negative coastal topobathy)  
   - **both**: no shoreline mask  
   This is why land DEMs that paint the sea as zero do not block bathymetry.
4. If the best group still has holes, **merge** lower-priority groups into those nodata pixels. Soften seams with a short gaussian blur along boundaries.
5. **Cut tiles**: 512×512 windows → Terrarium RGB → lossless WebP → one PMTiles archive per aggregation item.

Incremental runs skip jobs unchanged since the previous aggregation id.

### Terrarium and vertical rounding

Terrarium packs elevation into RGB with millimeter-scale precision at high zoom. To keep tiles small and slopes sensible, vertical values are **rounded more coarsely at lower zooms** (powers of two of 1/256 m). At z19 resolution is ~3.9 mm; at z0 it is 2048 m. Across zooms, the design keeps a similar minimum slope angle (~1.5°) between neighboring pixels.

### Where PMTiles land

Filenames mirror the CSV names without `-aggregation`. Zoom &lt; 7 files sit at the root of `pmtiles-store/`; higher zooms live under a zoom-7 parent folder, e.g. `pmtiles-store/7-67-44/12-2144-1434-17.pmtiles`.

---

## Stage 4 — Downsampling (overviews)

Aggregation only writes tiles at each region’s **local maxzoom**. Viewers still need coarser zooms for the whole planet.

Downsampling:

1. Loads four child tiles from existing PMTiles.
2. Decodes Terrarium → averages 2×2 into one 512×512 parent.
3. Re-encodes Terrarium WebP and packs another single-zoom PMTiles file.

Jobs run from high child zoom toward lower parents so each level can feed the next. Unchanged parents (relative to the previous aggregation) are skipped.

---

## Stage 5 — Bundle (distribution)

After aggregation and downsampling, `pmtiles-store` holds thousands of single-zoom archives (each at most ~64 tiles wide / ~1 GiB). **Bundle** merges them into multi-zoom products:

| Output | Contents |
|--------|----------|
| `bundle-store/planet.pmtiles` | Zooms **0–12** worldwide |
| `bundle-store/6-{x}-{y}.pmtiles` | Zooms **13+** under that z6 parent |

Bundle also refreshes metadata used by the public site: download URLs, attribution (from catalog metadata + tarball checksums), and removes dangling intermediate PMTiles before packing.

---

## How bathymetry and land interact

Priority is **resolution-first**, not “ocean always on top”:

1. Domain masking assigns land DEM pixels to land and bathymetry pixels to ocean.
2. Among sources that remain for a pixel, the group with the **higher maxzoom** wins; ties break by source name.

So a fine coastal bathymetry product can beat GEBCO in the ocean, and a national DEM can beat Copernicus GLO-30 on land, without either wiping out the other side of the shoreline.

Caveat: vertical datums are not homogenized. Nearshore seams between land and ocean products can still show small height jumps.

---

## Tile conventions (quick reference)

| Detail | Value |
|--------|--------|
| Tile size | 512×512 pixels |
| CRS | Web Mercator (EPSG:3857) |
| Encoding | Terrarium RGB → lossless WebP |
| Planning unit | Zoom **12** macrotiles |
| Max job extent | 6 zoom levels → ≤ 32768 px wide |
| Useful vertical table | Through zoom **19** (~3.9 mm) |
| Processing nodata | −9999 (missing elev written as 0 in Terrarium output) |

---

## Hardware and stores

Rule of thumb: **~2 GiB RAM per worker thread**. Throughput on a large box is on the order of ~100 GiB of normalized input per hour.

Set stores outside git:

```bash
# pipelines/.env  (gitignored; copy from env.example)
MAPTERHORN_DATA_ROOT=/mnt/ssd/mapterhorn
```

`MAPTERHORN_DATA_ROOT` is **required**. If it is missing or points inside the git repo, every store access raises and the CLI exits. Optional per-store overrides (`MAPTERHORN_PMTILES_STORE`, …) are also rejected if they resolve inside the repo.

Wipe all stores under the data root:

```bash
uv run mapterhorn clear-storage -y
uv run mapterhorn clear-storage --stores tmp-store aggregation-store -y
```

---

## Failure, status, and incremental rebuilds

- Progress and heartbeats: `meta-store/run-status.json` and logs (`mapterhorn status`).
- Failed jobs become `*.csv.failed` without stopping the whole pool; `mapterhorn retry-failed` turns them back into `.todo`.
- Re-running covering with updated sources marks only **dirty** aggregation/downsampling items, so adding or updating a DEM does not force a full-planet rebuild.

---

## Mental model

Think of Mapterhorn as a **compiler** for elevation:

1. **Sources** are libraries (normalized GeoTIFFs + bounds).
2. **Covering** is the planner (which regions, which files, which zoom).
3. **Aggregation** is codegen for the finest local tiles (with land/ocean awareness).
4. **Downsampling** builds the overview pyramid.
5. **Bundle** is the linker that ships a few big PMTiles files to users.

The same Terrarium surface can then show mountains and seafloor in one map layer.
