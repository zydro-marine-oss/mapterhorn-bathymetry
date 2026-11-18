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

# Turn NetCDF rasters in a source into EPSG:4326 LERC GeoTIFFs.
# NOAA's estuarine DEMs are distributed as NetCDF rather than GeoTIFF.
from glob import glob
import os
import subprocess
import sys


def run_command(command):
    proc = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(stderr.decode())
    return stdout.decode()


def convert_one(path):
    out = os.path.splitext(path)[0] + '.tif'
    command = (
        'gdalwarp -q -overwrite -t_srs EPSG:4326 -r bilinear '
        '-of COG -co BLOCKSIZE=512 -co OVERVIEWS=NONE -co SPARSE_OK=YES '
        '-co BIGTIFF=YES -co COMPRESS=LERC -co MAX_Z_ERROR=0.001 '
        '"{src}" "{dst}"'
    ).format(src=path, dst=out)
    run_command(command)
    os.remove(path)
    print('wrote {}'.format(os.path.basename(out)))


def main(source):
    paths = sorted(glob('source-store/{}/*.nc'.format(source)))
    if not paths:
        print('no netcdf files for {}'.format(source))
        return
    for path in paths:
        convert_one(path)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('usage: source_netcdf_to_cog.py SOURCE')
        raise SystemExit(1)
    main(sys.argv[1])
