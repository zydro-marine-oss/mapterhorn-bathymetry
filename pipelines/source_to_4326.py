# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "rasterio>=1.3.11",
# ]
#
# [tool.pixi.workspace]
# channels = ["conda-forge"]
#
# [tool.pixi.dependencies]
# gdal = "==3.13.3"
# ///

# Reproject a source's GeoTIFFs to EPSG:4326 so aggregation can build one VRT.
# Files that are already EPSG:4326 are left unchanged.
from glob import glob
import os
import subprocess
import sys

import rasterio


def run_command(command):
    proc = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(stderr.decode())
    return stdout.decode()


def warp_one(path):
    with rasterio.open(path) as src:
        if src.crs is not None and src.crs.to_epsg() == 4326:
            return
        nodata = src.nodata
    tmp = path + '.4326.tif'
    nodata_args = ''
    if nodata is not None:
        nodata_args = '-srcnodata {0} -dstnodata {0}'.format(nodata)
    command = (
        'gdalwarp -q -overwrite -t_srs EPSG:4326 -r bilinear {nodata} '
        '-of COG -co BLOCKSIZE=512 -co OVERVIEWS=NONE -co SPARSE_OK=YES '
        '-co BIGTIFF=YES -co COMPRESS=LERC -co MAX_Z_ERROR=0.001 '
        '"{src}" "{dst}"'
    ).format(nodata=nodata_args, src=path, dst=tmp)
    run_command(command)
    os.replace(tmp, path)
    print('reprojected {}'.format(os.path.basename(path)))


def main(source):
    paths = sorted(glob('source-store/{}/*.tif'.format(source)))
    paths += sorted(glob('source-store/{}/*.tiff'.format(source)))
    if not paths:
        print('no rasters in source-store/{}'.format(source))
        return
    for path in paths:
        warp_one(path)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('usage: source_to_4326.py SOURCE')
        raise SystemExit(1)
    main(sys.argv[1])
