# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "numpy>=1.24.4",
#   "rasterio>=1.3.11",
# ]
#
# [tool.pixi.workspace]
# channels = ["conda-forge"]
#
# [tool.pixi.dependencies]
# gdal = "==3.13.3"
# ///

# Apply shoreline land/ocean mask to reprojected source groups.
import json
import os
import subprocess
import tempfile

import numpy as np
import rasterio

NODATA = -9999
LAND_3857_GPKG = 'mask-store/shoreline/land_3857.gpkg'
_SOURCE_METADATA_CACHE = {}


def run_command(command):
    p = subprocess.Popen(
        command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    stdout, stderr = p.communicate()
    return stdout.decode(), stderr.decode()


def _load_source_metadata(source):
    if source in _SOURCE_METADATA_CACHE:
        return _SOURCE_METADATA_CACHE[source]
    metadata_path = '../source-catalog/{}/metadata.json'.format(source)
    metadata = {}
    if os.path.isfile(metadata_path):
        with open(metadata_path) as f:
            metadata = json.load(f)
    domain = metadata.get('domain', 'land')
    if domain not in ('land', 'ocean', 'both', 'mask'):
        raise ValueError('invalid domain {!r} for source {}'.format(domain, source))
    priority = int(metadata.get('priority', 0))
    parsed = {'domain': domain, 'priority': priority}
    _SOURCE_METADATA_CACHE[source] = parsed
    return parsed


def get_source_domain(source):
    return _load_source_metadata(source)['domain']


def get_source_priority(source):
    # Higher priority wins when maxzoom ties (after maxzoom, before source name).
    return _load_source_metadata(source)['priority']


def get_grouped_source_items(filepath):
    lines = []
    with open(filepath) as f:
        lines = f.readlines()
    lines = lines[1:]  # skip header
    line_tuples = []
    for line in lines:
        source, filename, maxzoom = line.strip().split(',')
        maxzoom = int(maxzoom)
        # Sort key: higher maxzoom, then higher priority, then source name.
        line_tuples.append((-maxzoom, -get_source_priority(source), source, filename))
    line_tuples = sorted(line_tuples)
    grouped_source_items = []

    first_line_tuple = line_tuples[0]
    last_group_signature = (first_line_tuple[0], first_line_tuple[2])
    current_group = [{
        'maxzoom': -first_line_tuple[0],
        'source': first_line_tuple[2],
        'filename': first_line_tuple[3],
        'domain': get_source_domain(first_line_tuple[2]),
    }]
    for line_tuple in line_tuples[1:]:
        current_group_signature = (line_tuple[0], line_tuple[2])
        if current_group_signature != last_group_signature:
            grouped_source_items.append(current_group)
            current_group = []
            last_group_signature = current_group_signature
        current_group.append({
            'maxzoom': -line_tuple[0],
            'source': line_tuple[2],
            'filename': line_tuple[3],
            'domain': get_source_domain(line_tuple[2]),
        })
    grouped_source_items.append(current_group)
    return grouped_source_items


def load_shoreline_window(reference_src):
    # Rasterize land polygons into the exact grid of the reprojected source tile.
    if not os.path.isfile(LAND_3857_GPKG):
        raise FileNotFoundError(
            'Shoreline vectors missing at {}. Run source_prepare_shoreline.py first.'.format(LAND_3857_GPKG)
        )

    left, bottom, right, top = reference_src.bounds
    width = reference_src.width
    height = reference_src.height

    tmp_fd, tmp_path = tempfile.mkstemp(suffix='-shoreline.tif')
    os.close(tmp_fd)
    try:
        cmd = (
            'gdal_rasterize -q -burn 1 -init 0 -ot Byte '
            '-te {left} {bottom} {right} {top} '
            '-ts {width} {height} '
            '-of GTiff "{src}" "{dst}"'
        ).format(
            left=left, bottom=bottom, right=right, top=top,
            width=width, height=height,
            src=LAND_3857_GPKG, dst=tmp_path
        )
        out, err = run_command(cmd)
        if not os.path.isfile(tmp_path) or os.path.getsize(tmp_path) == 0:
            raise RuntimeError('gdal_rasterize failed for shoreline mask:\n{}\n{}'.format(out, err))
        with rasterio.open(tmp_path) as shore_src:
            mask = shore_src.read(1)
        if mask.shape != (height, width):
            raise RuntimeError('shoreline mask shape {} != expected {}'.format(mask.shape, (height, width)))
        return mask.astype(np.uint8)
    finally:
        if os.path.isfile(tmp_path):
            os.remove(tmp_path)


def apply_domain_mask(elevation, land_mask, domain):
    # land_mask: 1 = land, 0 = ocean
    out = elevation.copy()
    if domain == 'both':
        return out
    if domain == 'ocean':
        out[land_mask == 1] = NODATA
        # Cap at 0 MSL so coarse coastal ramps / drying heights cannot ridge above sea level.
        valid = out != NODATA
        out[valid] = np.minimum(out[valid], 0)
        return out
    # land (default): drop ocean pixels that are sea-level fill ( >= 0 )
    ocean = land_mask == 0
    out[ocean & (out >= 0)] = NODATA
    return out


def mask_reprojected_groups(filepath, tmp_folder):
    # Kept for manual/debug use; aggregation_reproject applies masks inline.
    done_filepath = '{}/mask-done'.format(tmp_folder)
    if os.path.isfile(done_filepath):
        print('mask already done...')
        return

    grouped_source_items = get_grouped_source_items(filepath)
    land_mask = None
    for i, source_items in enumerate(grouped_source_items):
        tiff_path = '{}/{}-3857.tiff'.format(tmp_folder, i)
        if not os.path.isfile(tiff_path):
            continue
        domain = get_source_domain(source_items[0]['source'])
        with rasterio.open(tiff_path) as src:
            if land_mask is None:
                land_mask = load_shoreline_window(src)
            data = np.nan_to_num(src.read(1), nan=NODATA)
            profile = src.profile.copy()
        masked = apply_domain_mask(data, land_mask, domain)
        profile.update(nodata=NODATA)
        with rasterio.open(tiff_path, 'w', **profile) as dst:
            dst.write(masked, 1)

    with open(done_filepath, 'w') as f:
        f.write('ok\n')


if __name__ == '__main__':
    pass
