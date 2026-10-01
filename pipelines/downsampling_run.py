# Execute dirty downsampling jobs (build parent Terrarium tiles from children).
# Requires downloader.py staging pmtiles into tmp-store/.
from glob import glob
import io
import os
import shutil
import time
from multiprocessing import Pool

import imagecodecs
import mercantile
import numpy as np
from PIL import Image
from pmtiles.reader import MmapSource, Reader

import progress_util
import utils


def create_tile(parent_x, parent_y, parent_z, tmp_folder, pmtiles_filenames):
    tile_to_pmtiles_filename = get_tile_to_pmtiles_filename(pmtiles_filenames)
    full_data = np.zeros((1024, 1024), dtype=np.float32)
    for row_offset in range(2):
        for col_offset in range(2):
            child_x = 2 * parent_x + col_offset
            child_y = 2 * parent_y + row_offset
            child_z = parent_z + 1
            child = mercantile.Tile(x=child_x, y=child_y, z=child_z)
            if child not in tile_to_pmtiles_filename:
                continue
            filename = tile_to_pmtiles_filename[child]
            file_z, file_x, file_y, _ = [
                int(a) for a in filename.replace('.pmtiles', '').split('-')
            ]
            pmtiles_folder = utils.get_pmtiles_folder(file_x, file_y, file_z)
            filepath = 'tmp-store/{}/{}'.format(
                pmtiles_folder.replace('-store', ''), filename
            )
            with open(filepath, 'r+b') as f:
                reader = Reader(MmapSource(f))
                child_bytes = reader.get(child_z, child_x, child_y)
            child_rgb = np.array(Image.open(io.BytesIO(child_bytes)), dtype=np.float32)
            row_start = 512 * row_offset
            row_end = 512 * (row_offset + 1)
            col_start = 512 * col_offset
            col_end = 512 * (col_offset + 1)
            full_data[row_start:row_end, col_start:col_end] = (
                child_rgb[:, :, 0] * 256.0
                + child_rgb[:, :, 1]
                + child_rgb[:, :, 2] / 256.0
                - 32768.0
            )

    parent_data = full_data.reshape((512, 2, 512, 2)).mean(axis=(1, 3))
    parent_data = utils.get_rounded_elevation_data(parent_data, parent_z)
    parent_data += 32768.0
    parent_rgb = np.zeros((512, 512, 3), dtype=np.uint8)
    parent_rgb[:, :, 0] = parent_data // 256
    parent_rgb[:, :, 1] = np.floor(parent_data % 256)
    parent_rgb[:, :, 2] = np.floor((parent_data - np.floor(parent_data)) * 256)

    parent_bytes = imagecodecs.webp_encode(parent_rgb, lossless=True)
    parent_filepath = '{}/{}-{}-{}.webp'.format(tmp_folder, parent_z, parent_x, parent_y)
    with open(parent_filepath, 'wb') as f:
        f.write(parent_bytes)


def get_tile_to_pmtiles_filename(pmtiles_filenames):
    tile_to_pmtiles_filename = {}
    for pmtiles_filename in pmtiles_filenames:
        pmtiles_z, pmtiles_x, pmtiles_y, child_zoom = [
            int(a) for a in pmtiles_filename.replace('.pmtiles', '').split('-')
        ]
        if pmtiles_z == child_zoom:
            children = [mercantile.Tile(x=pmtiles_x, y=pmtiles_y, z=pmtiles_z)]
        else:
            children = list(
                mercantile.children(
                    mercantile.Tile(x=pmtiles_x, y=pmtiles_y, z=pmtiles_z),
                    zoom=child_zoom,
                )
            )
        for child in children:
            tile_to_pmtiles_filename[child] = pmtiles_filename
    return tile_to_pmtiles_filename


def downsample_single(filepath):
    _, __, filename = filepath.split('/')
    if os.path.isfile('{}.done'.format(filepath)):
        return 'skip'

    queue_folder = 'tmp-store/queue'
    os.makedirs(queue_folder, exist_ok=True)
    shutil.copy(filepath, '{}/{}.tmp'.format(queue_folder, filename))
    os.rename(
        '{}/{}.tmp'.format(queue_folder, filename),
        '{}/{}'.format(queue_folder, filename),
    )
    ready_folder = 'tmp-store/ready'
    os.makedirs(ready_folder, exist_ok=True)
    while not os.path.isfile('{}/{}'.format(ready_folder, filename)):
        time.sleep(1)

    parts = filename.split('-')
    extent_z, extent_x, extent_y, parent_zoom = [int(a) for a in parts[:4]]

    out_folder = utils.get_pmtiles_folder(extent_x, extent_y, extent_z)
    utils.create_folder(out_folder)
    out_filepath = '{}/{}-{}-{}-{}.pmtiles'.format(
        out_folder, extent_z, extent_x, extent_y, parent_zoom
    )

    extent = mercantile.Tile(x=extent_x, y=extent_y, z=extent_z)
    tmp_folder = 'tmp-store/{}'.format(filename.replace('-downsampling.csv', ''))
    os.makedirs(tmp_folder, exist_ok=True)

    with open(filepath) as f:
        pmtiles_filenames = [a.strip() for a in f.readlines()[1:]]

    if extent_z == parent_zoom:
        parents = [extent]
    else:
        parents = list(mercantile.children(extent, zoom=parent_zoom))

    for parent in parents:
        create_tile(parent.x, parent.y, parent.z, tmp_folder, pmtiles_filenames)

    utils.create_archive(tmp_folder, out_filepath)
    shutil.rmtree(tmp_folder)
    with open('{}.done'.format(filepath), 'w') as f:
        f.write('')
    if os.path.isfile('{}.todo'.format(filepath)):
        os.remove('{}.todo'.format(filepath))
    ready_path = '{}/{}'.format(ready_folder, filename)
    if os.path.isfile(ready_path):
        os.remove(ready_path)
    return 'ok'


def get_child_zoom_to_filepaths():
    child_zoom_to_filepaths = {}
    aggregation_ids = utils.get_aggregation_ids()
    aggregation_id = aggregation_ids[-1]
    for todo_filepath in sorted(
        glob('aggregation-store/{}/*-downsampling.csv.todo'.format(aggregation_id))
    ):
        filename = todo_filepath.split('/')[-1]
        _, __, ___, child_zoom = [
            int(a) for a in filename.replace('-downsampling.csv.todo', '').split('-')
        ]
        if child_zoom not in child_zoom_to_filepaths:
            child_zoom_to_filepaths[child_zoom] = []
        child_zoom_to_filepaths[child_zoom].append(todo_filepath.replace('.todo', ''))
    return child_zoom_to_filepaths


def main():
    child_zoom_to_filepaths = get_child_zoom_to_filepaths()
    child_zooms = list(reversed(sorted(list(child_zoom_to_filepaths.keys()))))
    if len(child_zooms) == 0:
        print('nothing to do.')
        return

    total_jobs = sum(len(child_zoom_to_filepaths[z]) for z in child_zooms)
    with progress_util.make_progress() as progress:
        overall = progress.add_task('downsampling run', total=total_jobs)
        progress.console.log(
            '{} job(s) across {} child zoom(s); ensure downloader.py is running'
            .format(total_jobs, len(child_zooms))
        )
        for child_zoom in child_zooms:
            filepaths = sorted(child_zoom_to_filepaths[child_zoom])
            progress.update(
                overall,
                description='downsampling run · child z{} ({} jobs)'.format(
                    child_zoom, len(filepaths)
                ),
            )
            with Pool() as pool:
                for result in pool.imap_unordered(
                    downsample_single, filepaths, chunksize=1
                ):
                    if result == 'skip':
                        progress.console.log('skipped already-done item')
                    progress.advance(overall)
        progress.update(overall, description='downsampling run done')


if __name__ == '__main__':
    main()
