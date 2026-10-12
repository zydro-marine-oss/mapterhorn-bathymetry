### About this `mapterhorn-bathymetry` fork

This fork is a (WIP) attempt to build a combined elevation + bathymetry model by adding GEBCO and other bathymetry datasets into the Mapterhorn pipeline. All credit goes to the [mapterhorn](https://github.com/mapterhorn/mapterhorn) team for their work so far! Use at your own risk.

#### About our Modifications

This branch keeps the upstream mapterhorn pipeline (for the most part). We add a new source type `mask` representing shoreline mask geometry. Shoreline geometry is used to mask `land` or `ocean` sources along the shoreline boundary, allowing the different datasets to be combined.

- Optional source `domain` (`land` / `ocean` / `both` / `mask`) in `source-catalog/*/metadata.json`
- Shoreline masking (S2Coast + GSHHG Antarctica) during aggregation
- GEBCO added as an ocean data source

Prepare the shoreline, then GEBCO, from `pipelines/`:

```
just ../source-catalog/s2coast/
just ../source-catalog/gebco/
```

See [source-catalog/README.md](./source-catalog/README.md) for `domain`, and [pipelines/README.md](./pipelines/README.md) for the rest of the pipeline.

#### Problems

There are a number of issues with this approach that prevent the dataset from being "production ready":

- The masking using shoreline geometry is binary, which creates 'ridges' and 'ledges' where low-res bathymetry such as from GEBCO does not exactly align with the edge of higher-res terrain data.
- Some areas of the world (eg French Alps) have mysterious missing tiles.
- The dataset does not currently mask shorelines for large lakes / inland oceans such as the Great Lakes. It's unclear where we make that cutoff. Should we include _all_ lakes? (an impossible task)
- Some water bodies are not at MSL 0. How might this affect the output of the pipeline?
 
---

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="resources/mapterhorn-bathymetry-logo-darkmode.png">
  <source media="(prefers-color-scheme: light)" srcset="resources/mapterhorn-bathymetry-logo.png">
  <img alt="Mapterhorn Bathymetry logo" src="resources/mapterhorn-bathymetry-logo.png">
</picture>

Public terrain tiles for interactive web map visualizations.

## Viewer

[https://mapterhorn.com/viewer](https://mapterhorn.com/viewer)

## Examples

[https://mapterhorn.com/examples](https://mapterhorn.com/examples)

## Migrate from AWS Elevation Tiles (Tilezen Joerd)

```diff
"hillshadeSource": {
    "type": "raster-dem",
-   "tiles": ["https://elevation-tiles-prod.s3.amazonaws.com/terrarium/{z}/{x}/{y}.png"],
+   "tiles": ["https://tiles.mapterhorn.com/{z}/{x}/{y}.webp"],
    "encoding": "terrarium",
-   "tileSize": 256,
+   "tileSize": 512,
}

```

## Contributing

[CONTRIBUTING.md](./CONTRIBUTING.md)

## License

Code: BSD-3, see [LICENSE](https://github.com/mapterhorn/mapterhorn/blob/main/LICENSE).

Terrain data: various open-data sources, for a full list see [https://mapterhorn.com/attribution](https://mapterhorn.com/attribution).
