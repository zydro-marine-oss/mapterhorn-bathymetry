# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "numpy>=1.24.4",
#   "rasterio>=1.3.11",
# ]
#
# [tool.pixi.workspace]
# channels = ["conda-forge"]
# ///

# Read an ARC/INFO interchange (.e00) grid and write a GeoTIFF.
# The GRD section is the public interchange layout: a fixed-width header
# followed by row-major values, five numbers per line.
import gzip
import os
import sys
from glob import glob

import numpy as np
import rasterio
from rasterio.transform import from_origin


def open_text(path):
    if path.endswith('.gz'):
        return gzip.open(path, 'rt')
    return open(path, 'rt')


def parse_grd(path):
    with open_text(path) as handle:
        first = handle.readline()
        if not first.startswith('EXP'):
            raise ValueError('{} is not an ARC/INFO interchange file'.format(path))
        if handle.readline().split()[0] != 'GRD':
            raise ValueError('{} has no GRD grid'.format(path))
        header = handle.readline()
        ncols = int(header[0:10])
        nrows = int(header[10:20])
        nodata = float(header[22:])
        cell_x, cell_y = (float(value) for value in handle.readline().split())
        min_x, _min_y = (float(value) for value in handle.readline().split())
        _max_x, max_y = (float(value) for value in handle.readline().split())
        tokens = []
        for line in handle:
            if line.startswith('EOG'):
                break
            text = line.rstrip('\n')
            tokens.extend(text[index:index + 14] for index in range(0, len(text), 14))
    stride = ((ncols + 4) // 5) * 5
    values = np.array(tokens, dtype='float32').reshape(nrows, stride)
    grid = np.ascontiguousarray(values[:, :ncols])
    transform = from_origin(min_x, max_y, cell_x, cell_y)
    return grid, transform, nodata


def convert(path, crs):
    grid, transform, nodata = parse_grd(path)
    out = os.path.splitext(path)[0]
    if out.endswith('.e00'):
        out = out[:-4]
    out = out + '.tif'
    kwargs = dict(
        driver='GTiff', height=grid.shape[0], width=grid.shape[1], count=1,
        dtype='float32', nodata=nodata, transform=transform, tiled=True,
        blockxsize=512, blockysize=512, compress='deflate',
    )
    if crs:
        kwargs['crs'] = crs
    with rasterio.open(out, 'w', **kwargs) as dst:
        dst.write(grid, 1)
    os.remove(path)
    print('wrote {} ({} x {})'.format(os.path.basename(out), grid.shape[1], grid.shape[0]))


def main(source, crs):
    folder = 'source-store/{}'.format(source)
    paths = sorted(glob(folder + '/*.e00') + glob(folder + '/*.e00.gz'))
    if not paths:
        print('no .e00 grids for {}'.format(source))
        return
    for path in paths:
        convert(path, crs)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('usage: source_e00_to_tif.py SOURCE [EPSG:CODE]')
        raise SystemExit(1)
    crs = sys.argv[2] if len(sys.argv) > 2 else None
    main(sys.argv[1], crs)
