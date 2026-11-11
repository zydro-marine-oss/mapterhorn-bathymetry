# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "numpy>=1.24.4",
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
# S-102 fill is typically 1e6; map it to pipeline nodata -9999 and drop any bleed.
from glob import glob
import os
import sys
from multiprocessing import Pool

import numpy as np
from osgeo import gdal

gdal.UseExceptions()

NODATA = -9999.0
# S-102 DCF-2 fill; also treat absurd magnitudes as invalid after warp.
S102_FILL_DEFAULT = 1.0e6
ABSURD_ABS = 1.0e5

COG_OPTIONS = [
    'BLOCKSIZE=512',
    'OVERVIEWS=NONE',
    'SPARSE_OK=YES',
    'BIGTIFF=YES',
    'COMPRESS=LERC',
    'MAX_Z_ERROR=0.001',
]


def s102_to_cog(filepath):
    filepath_out = filepath[:-3] + '.tif' if filepath.endswith('.h5') else filepath + '.tif'
    if os.path.isfile(filepath_out):
        print('skip existing {}'.format(filepath_out))
        if os.path.isfile(filepath):
            os.remove(filepath)
        return

    tmp_path = filepath_out + '.tmp.tif'
    if os.path.isfile(tmp_path):
        os.remove(tmp_path)

    src_nodata = S102_FILL_DEFAULT
    src = gdal.OpenEx(filepath, open_options=['DEPTH_OR_ELEVATION=ELEVATION'])
    if src is None:
        raise RuntimeError('failed to open S-102 dataset {}'.format(filepath))
    try:
        band = src.GetRasterBand(1)
        reported = band.GetNoDataValue()
        if reported is not None:
            src_nodata = float(reported)

        # Warp with explicit nodata so bilinear does not smear the 1e6 fill into valid cells.
        gdal.Warp(
            tmp_path,
            src,
            format='GTiff',
            dstSRS='EPSG:4326',
            srcNodata=src_nodata,
            dstNodata=NODATA,
            resampleAlg=gdal.GRA_Bilinear,
            srcBands=[1],
            warpOptions=['UNIFIED_SRC_NODATA=YES'],
            creationOptions=['TILED=YES', 'COMPRESS=DEFLATE', 'BIGTIFF=IF_NEEDED'],
        )
    finally:
        src = None

    ds = gdal.Open(tmp_path, gdal.GA_Update)
    if ds is None:
        raise RuntimeError('failed to open warped temp {}'.format(tmp_path))
    try:
        band = ds.GetRasterBand(1)
        data = band.ReadAsArray()
        invalid = (
            ~np.isfinite(data)
            | (data == src_nodata)
            | (data == NODATA)
            | (np.abs(data) >= ABSURD_ABS)
        )
        data = data.astype(np.float32, copy=False)
        data[invalid] = NODATA
        band.WriteArray(data)
        band.SetNoDataValue(NODATA)
        band.FlushCache()
    finally:
        ds = None

    gdal.Translate(
        filepath_out,
        tmp_path,
        format='COG',
        noData=NODATA,
        creationOptions=COG_OPTIONS,
    )
    os.remove(tmp_path)
    os.remove(filepath)
    print('converted {} (src_nodata={})'.format(filepath_out, src_nodata))


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
