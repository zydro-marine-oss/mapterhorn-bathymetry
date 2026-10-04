from glob import glob
import gzip
import math
import time
import sys
import json
import os
from io import BytesIO

import mercantile
from pmtiles.tile import (
    TileType,
    Compression,
    deserialize_header,
    deserialize_directory,
    Entry,
    serialize_header,
    tileid_to_zxy,
)
from pmtiles.reader import Reader, MmapSource
from pmtiles.writer import Writer, optimize_directories

try:
    from pmtiles.writer import finalize_header
except ImportError:
    def finalize_header(
        header,
        addressed_tiles_count,
        tile_entries,
        tile_contents_count,
        metadata,
        clustered,
        tile_data_length,
    ):
        # PyPI pmtiles < git master: Writer.finalize exists, this helper does not.
        header['addressed_tiles_count'] = addressed_tiles_count
        header['tile_entries_count'] = len(tile_entries)
        header['tile_contents_count'] = tile_contents_count
        tile_entries = sorted(tile_entries, key=lambda e: e.tile_id)
        header['min_zoom'] = tileid_to_zxy(tile_entries[0].tile_id)[0]
        header['max_zoom'] = tileid_to_zxy(tile_entries[-1].tile_id)[0]
        root_bytes, leaves_bytes, num_leaves = optimize_directories(
            tile_entries, 16384 - 127
        )
        compressed_metadata = gzip.compress(json.dumps(metadata).encode(), mtime=0)
        header['clustered'] = clustered
        header['internal_compression'] = Compression.GZIP
        header['root_offset'] = 127
        header['root_length'] = len(root_bytes)
        header['metadata_offset'] = header['root_offset'] + header['root_length']
        header['metadata_length'] = len(compressed_metadata)
        header['leaf_directory_offset'] = (
            header['metadata_offset'] + header['metadata_length']
        )
        header['leaf_directory_length'] = len(leaves_bytes)
        header['tile_data_offset'] = (
            header['leaf_directory_offset'] + header['leaf_directory_length']
        )
        header['tile_data_length'] = tile_data_length
        header_bytes = serialize_header(header)
        return header_bytes, root_bytes, compressed_metadata, leaves_bytes

import progress_util
import utils


def get_parent_to_filepaths(num_aggregations, progress=None):
    filepaths = sorted(utils.list_pmtiles_filepaths())

    parent_to_filepath = {}
    dirty_parents = get_dirty_parents(num_aggregations) if num_aggregations > 0 else None
    scan = None
    if progress is not None:
        scan = progress.add_task(
            'index pmtiles', total=max(len(filepaths), 1)
        )

    for filepath in filepaths:
        filename = filepath.split('/')[-1]
        z, x, y, child_z = [int(a) for a in filename.replace('.pmtiles', '').split('-')]
        
        parent = None
        if child_z <= 12:
            parent = mercantile.Tile(x=0, y=0, z=0)
        else:
            assert z >= 6
            if z == 6:
                parent = mercantile.Tile(x=x, y=y, z=z)
            else:
                parent = mercantile.parent(mercantile.Tile(x=x, y=y, z=z), zoom=6)
        
        if not (num_aggregations > 0 and parent not in dirty_parents):
            if parent not in parent_to_filepath:
                parent_to_filepath[parent] = []
            parent_to_filepath[parent].append(filepath)

        if scan is not None:
            progress.advance(scan)

    if scan is not None:
        progress.remove_task(scan)

    return parent_to_filepath

def get_dirty_parents(num_aggregations):
    dirty_parents = set([mercantile.Tile(x=0, y=0, z=0)])

    aggregation_ids = utils.get_aggregation_ids()
    assert len(aggregation_ids) >= num_aggregations

    for offset in range(num_aggregations):
        current_aggregation_id = aggregation_ids[-1 - offset]
        last_aggregation_id = None if len(aggregation_ids) == 1 else aggregation_ids[-2 - offset]
        aggregation_filenames = utils.get_dirty_aggregation_filenames(current_aggregation_id, last_aggregation_id)
        
        for filename in aggregation_filenames:
            z, x, y, child_z = [int(a) for a in filename.replace('-aggregation.csv', '').split('-')]
            if child_z >= 13:
                dirty_parents.add(mercantile.parent(mercantile.Tile(x=x, y=y, z=z), zoom=6))

    return list(dirty_parents)

def traverse_dry_run(get_bytes, header, dir_offset, dir_length):
    entries = deserialize_directory(get_bytes(dir_offset, dir_length))
    for entry in entries:
        if entry.run_length > 0:
            for i in range(entry.run_length):
                yield entry.tile_id + i, header['tile_data_offset'] + entry.offset, entry.length
        else:
            for t in traverse_dry_run(
                get_bytes,
                header,
                header['leaf_directory_offset'] + entry.offset,
                entry.length,
            ):
                yield t

def all_tiles_dry_run(get_bytes):
    header = deserialize_header(get_bytes(0, 127))
    return traverse_dry_run(get_bytes, header, header['root_offset'], header['root_length'])
    
def create_archive(filepaths, name, progress):
    progress.console.log('start working on {}...'.format(name))

    utils.create_folder('bundle-store')
    out_filepath = 'bundle-store/{}.pmtiles'.format(name)
    checksum = None

    min_z = math.inf
    max_z = 0
    min_lon = math.inf
    min_lat = math.inf
    max_lon = -math.inf
    max_lat = -math.inf
    tiles_filepaths = []
    tile_data_length = 0
    dry = progress.add_task(
        '{} · dry run'.format(name), total=max(len(filepaths), 1)
    )
    for filepath in filepaths:
        filename = filepath.split('/')[-1]
        z, x, y, child_z = [int(a) for a in filename.replace('.pmtiles', '').split('-')]    
        max_z = max(max_z, child_z)
        min_z = min(min_z, child_z)
        west, south, east, north = mercantile.bounds(x, y, z)
        min_lon = min(min_lon, west)
        min_lat = min(min_lat, south)
        max_lon = max(max_lon, east)
        max_lat = max(max_lat, north)

        with open(filepath , 'r+b') as f:
            reader = Reader(MmapSource(f))
            for tile_id, tile_offset, tile_length in all_tiles_dry_run(reader.get_bytes):
                tiles_filepaths.append((tile_id, tile_offset, tile_length, filepath))
                tile_data_length += tile_length
        progress.advance(dry)
    progress.remove_task(dry)

    progress.console.log(
        'found {:_} tiles ({:.2f} GiB)'.format(
            len(tiles_filepaths), tile_data_length / 1024 ** 3
        )
    )

    tiles_filepaths.sort()

    tile_entries = []
    offset = 0
    for tile_id, _, tile_length, __ in tiles_filepaths:
        tile_entries.append(Entry(tile_id, offset, tile_length, 1))
        offset += tile_length

    min_lon_e7 = int(min_lon * 1e7)
    min_lat_e7 = int(min_lat * 1e7)
    max_lon_e7 = int(max_lon * 1e7)
    max_lat_e7 = int(max_lat * 1e7)

    header = {
        'tile_type': TileType.WEBP,
        'tile_compression': Compression.NONE,
        'min_zoom': min_z,
        'max_zoom': max_z,
        'min_lon_e7': min_lon_e7,
        'min_lat_e7': min_lat_e7,
        'max_lon_e7': max_lon_e7,
        'max_lat_e7': max_lat_e7,
        'center_zoom': int(0.5 * (min_z + max_z)),
        'center_lon_e7': int(0.5 * (min_lon_e7 + max_lon_e7)),
        'center_lat_e7': int(0.5 * (min_lat_e7 + max_lat_e7)),
        'encoding': 'terrarium',
    }
    addressed_tiles_count  = len(tile_entries)
    tile_contents_count = len(tile_entries)
    metadata = {
        'attribution': '<a href="https://mapterhorn.com/attribution">© Mapterhorn</a>',
    }
    clustered = True
    header_bytes, root_bytes, compressed_metadata, leaves_bytes = finalize_header(header, addressed_tiles_count, tile_entries, tile_contents_count, metadata, clustered, tile_data_length)

    with open(out_filepath, 'wb') as f:

        progress.console.log('writing header...')
        hash_writer = utils.HashWriter(f)
        hash_writer.write(header_bytes)
        hash_writer.write(root_bytes)
        hash_writer.write(compressed_metadata)
        hash_writer.write(leaves_bytes)

        last_filepath = None
        in_pmtiles_data = None

        write = progress.add_task(
            '{} · write tiles'.format(name),
            total=max(tile_data_length, 1),
        )
        bytes_written = 0
        last_update = 0.0
        for _, tile_offset, tile_length, filepath in tiles_filepaths:
            if last_filepath != filepath:
                last_filepath = filepath
                with open(filepath, 'rb') as f_in:
                    in_pmtiles_data = f_in.read()
            hash_writer.write(in_pmtiles_data[tile_offset:(tile_offset + tile_length)])
            bytes_written += tile_length
            now = time.monotonic()
            if bytes_written == tile_data_length or now - last_update >= 0.25:
                progress.update(
                    write,
                    completed=bytes_written,
                    description='{} · write tiles ({:.2f}/{:.2f} GiB)'.format(
                        name,
                        bytes_written / 1024 ** 3,
                        tile_data_length / 1024 ** 3,
                    ),
                )
                last_update = now

        checksum = hash_writer.md5.hexdigest()
        progress.remove_task(write)

    progress.console.log('{} md5 {}'.format(name, checksum))
    utils.create_folder('meta-store/bundle')
    filesize = os.path.getsize(out_filepath)
    with open('meta-store/bundle/{}.json'.format(name), 'w') as f:
        json.dump({
            'size': filesize,
            'md5sum': checksum,
            'min_lon': min_lon,
            'min_lat': min_lat,
            'max_lon': max_lon,
            'max_lat': max_lat,
            'min_zoom': min_z,
            'max_zoom': max_z,
        }, f, indent=2)

def get_name_from_parent(parent):
    name = None
    if parent == mercantile.Tile(x=0, y=0, z=0):
        name = 'planet'
    else:
        name = f'{parent.z}-{parent.x}-{parent.y}'
    return name

def main():
    num_aggregations = None
    if len(sys.argv) == 2:
        num_aggregations = int(sys.argv[1])
    else:
        print('Not enough arguments. Usage: bundle.py {{num_aggregations}}')
        exit()

    created = []
    with progress_util.make_progress() as progress:
        overall = progress.add_task(
            'bundle last {} aggregation(s)'.format(num_aggregations),
            total=None,
        )
        parent_to_filepaths = get_parent_to_filepaths(num_aggregations, progress)
        if len(parent_to_filepaths) == 0:
            progress.update(overall, description='bundle: nothing to do')
            print('nothing to do.')
            return

        progress.update(
            overall,
            total=len(parent_to_filepaths),
            description='bundle last {} aggregation(s)'.format(num_aggregations),
        )
        progress.console.log(
            'bundling the last {} aggregation(s); {} archive(s) to write'
            .format(num_aggregations, len(parent_to_filepaths))
        )
        for i, parent in enumerate(parent_to_filepaths, start=1):
            name = get_name_from_parent(parent)
            created.append(name)
            progress.update(
                overall,
                description='bundle · {} ({}/{})'.format(
                    name, i, len(parent_to_filepaths)
                ),
            )
            create_archive(parent_to_filepaths[parent], name, progress)
            progress.advance(overall)
        progress.update(overall, description='bundle done')

    print('The following {} file(s) were created:'.format(len(created)))
    for name in created:
        print('{}.pmtiles'.format(name))

if __name__ == '__main__':
    main()
