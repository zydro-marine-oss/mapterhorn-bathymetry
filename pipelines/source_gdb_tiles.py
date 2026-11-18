# /// script
# requires-python = ">=3.13"
# dependencies = [
# ]
#
# [tool.pixi.workspace]
# channels = ["conda-forge"]
#
# [tool.pixi.dependencies]
# gdal = "==3.13.3"
# ///

# Tile a File Geodatabase delivered inside a zip.
# NRCan publishes the west-coast topo-bathy model as one file geodatabase.
# A single raster of that size is awkward for the polygonize step, so this
# cuts it into square windows and drops windows that are entirely nodata.
# Output is EPSG:4326.
import glob
import json
import os
import subprocess
import sys
import zipfile

TILE = 8192


def run_json(command):
    proc = subprocess.run(command, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)
    return json.loads(proc.stdout)


def gdb_inside(zip_path):
    roots = set()
    with zipfile.ZipFile(zip_path) as archive:
        for name in archive.namelist():
            marker = '.gdb/'
            index = name.lower().find(marker)
            if index >= 0:
                roots.add(name[:index + len(marker) - 1])
    if len(roots) != 1:
        raise ValueError('expected one .gdb in {}, found {}'.format(zip_path, sorted(roots)))
    return '/vsizip/{}/{}'.format(os.path.abspath(zip_path), roots.pop())


def raster_source(gdb_path):
    info = run_json(['gdalinfo', '-json', gdb_path])
    subdatasets = info.get('subdatasets') or []
    if subdatasets:
        return subdatasets[0]['name']
    bands = info.get('bands') or []
    if bands:
        return gdb_path
    raise ValueError('no raster in {}'.format(gdb_path))


def tile_source(source):
    folder = 'source-store/{}'.format(source)
    zips = sorted(glob.glob(folder + '/*.zip'))
    if len(zips) != 1:
        raise SystemExit('{}: expected one zip, found {}'.format(source, zips))
    gdb = gdb_inside(zips[0])
    raster = raster_source(gdb)
    info = run_json(['gdalinfo', '-json', raster])
    width = info['size'][0]
    height = info['size'][1]
    written = 0
    for row in range(0, height, TILE):
        for col in range(0, width, TILE):
            win_w = min(TILE, width - col)
            win_h = min(TILE, height - row)
            out = os.path.join(folder, 'tile_{}_{}.tif'.format(row // TILE, col // TILE))
            command = [
                'gdal_translate', '-q', '-srcwin', str(col), str(row), str(win_w), str(win_h),
                '-of', 'GTiff', raster, out,
            ]
            subprocess.run(command, check=True)
            stats = run_json(['gdalinfo', '-json', '-stats', out])
            band = stats['bands'][0]
            minimum = band.get('minimum')
            maximum = band.get('maximum')
            if minimum is None or (minimum == maximum and minimum == band.get('noDataValue')):
                os.remove(out)
                continue
            warped = out + '.4326.tif'
            subprocess.run([
                'gdalwarp', '-q', '-overwrite', '-t_srs', 'EPSG:4326', '-r', 'bilinear',
                '-of', 'COG', '-co', 'COMPRESS=LERC', '-co', 'MAX_Z_ERROR=0.001',
                '-co', 'BLOCKSIZE=512', '-co', 'OVERVIEWS=NONE', '-co', 'SPARSE_OK=YES',
                out, warped,
            ], check=True)
            os.replace(warped, out)
            written += 1
            print('kept {}'.format(os.path.basename(out)))
    os.remove(zips[0])
    print('wrote {} tiles'.format(written))


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('usage: source_gdb_tiles.py SOURCE')
        raise SystemExit(1)
    tile_source(sys.argv[1])
