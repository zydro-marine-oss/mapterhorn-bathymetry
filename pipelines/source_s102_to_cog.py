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
# libgdal-hdf5 = "*"
# ///

# Convert NOAA S-102 HDF5 tiles to elevation GeoTIFFs in EPSG:4326.
from glob import glob
import os
import sys
from multiprocessing import Pool
import subprocess


def run_command(command):
    p = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    return p.returncode, stdout.decode(), stderr.decode()


def s102_to_cog(filepath):
    filepath_out = filepath[:-3] + '.tif' if filepath.endswith('.h5') else filepath + '.tif'
    if os.path.isfile(filepath_out):
        print('skip existing {}'.format(filepath_out))
        if os.path.isfile(filepath):
            os.remove(filepath)
        return

    # DEPTH_OR_ELEVATION=ELEVATION: positive up. Mixed UTM -> EPSG:4326 for one CRS per source.
    cmd = (
        'GDAL_CACHEMAX=512 gdalwarp -oo DEPTH_OR_ELEVATION=ELEVATION '
        '-t_srs EPSG:4326 -dstnodata -9999 -r bilinear -b 1 '
        '-of COG -co BLOCKSIZE=512 -co OVERVIEWS=NONE -co SPARSE_OK=YES '
        '-co BIGTIFF=YES -co COMPRESS=LERC -co MAX_Z_ERROR=0.001 '
        '"{}" "{}"'
    ).format(filepath, filepath_out)
    code, out, err = run_command(cmd)
    if code != 0 or not os.path.isfile(filepath_out):
        raise RuntimeError('gdalwarp failed for {}:\n{}\n{}'.format(filepath, out, err))
    os.remove(filepath)
    print('converted {}'.format(filepath_out))


def main(source):
    filepaths = sorted(glob('source-store/{}/{}'.format(source, '*.h5')))
    print('num h5 files: {}'.format(len(filepaths)))
    if not filepaths:
        print('nothing to convert')
        return
    with Pool() as pool:
        pool.map(s102_to_cog, filepaths, chunksize=1)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        source = sys.argv[1]
        print('converting S-102 to cog for source={}...'.format(source))
        main(source)
    else:
        print('source argument missing')
        raise SystemExit(1)
