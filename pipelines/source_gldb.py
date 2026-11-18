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

# Global Lake Database v2 ships lake depth as a headerless little-endian
# int16 grid. The layout is stated in GlobalLakeDepth.txt inside the archive:
# 43200 by 21600 cells, 30 arc-seconds, row 0 at 90 N, column 0 at 180 W,
# depths in decimetres, 0 where there is no lake.
# This writes elevation in metres, negative down, with 0 stored as nodata,
# which is the same sign convention as the rest of the catalog.
import os
import sys
import tarfile

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.windows import Window

WIDTH = 43200
HEIGHT = 21600
NODATA = -9999.0
CELL = 1.0 / 120.0


def find_dat(folder):
    direct = os.path.join(folder, 'GlobalLakeDepth.dat')
    if os.path.isfile(direct):
        return direct
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if name.endswith('.tar.gz') or name.endswith('.tgz'):
            with tarfile.open(path, 'r:gz') as archive:
                member = archive.extractfile('GlobalLakeDepth.dat')
                if member is None:
                    raise ValueError('{} has no GlobalLakeDepth.dat'.format(name))
                out = os.path.join(folder, 'GlobalLakeDepth.dat')
                with open(out, 'wb') as handle:
                    while True:
                        chunk = member.read(1 << 20)
                        if not chunk:
                            break
                        handle.write(chunk)
            os.remove(path)
            return out
    raise ValueError('GlobalLakeDepth.dat not found in {}'.format(folder))


def convert(folder):
    dat_path = find_dat(folder)
    out_path = os.path.join(folder, 'gldb_v2.tif')
    transform = from_origin(-180.0, 90.0, CELL, CELL)
    profile = dict(
        driver='GTiff', height=HEIGHT, width=WIDTH, count=1, dtype='float32',
        nodata=NODATA, crs='EPSG:4326', transform=transform, tiled=True,
        blockxsize=512, blockysize=512, compress='deflate', bigtiff='YES',
    )
    with open(dat_path, 'rb') as raw, rasterio.open(out_path, 'w', **profile) as dst:
        for row in range(HEIGHT):
            raw_row = np.frombuffer(raw.read(WIDTH * 2), dtype='<i2')
            if raw_row.size != WIDTH:
                raise ValueError('short read at row {}'.format(row))
            elevation = np.full(WIDTH, NODATA, dtype='float32')
            wet = raw_row != 0
            elevation[wet] = -raw_row[wet].astype('float32') / 10.0
            dst.write(elevation.reshape(1, WIDTH), 1, window=Window(0, row, WIDTH, 1))
            if row % 2000 == 0:
                print('row {} / {}'.format(row, HEIGHT))
    os.remove(dat_path)
    print('wrote {}'.format(out_path))


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('usage: source_gldb.py SOURCE')
        raise SystemExit(1)
    convert('source-store/{}'.format(sys.argv[1]))
