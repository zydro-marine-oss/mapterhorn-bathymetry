# Plan downsampling work from aggregation coverings.
from glob import glob

import mercantile

import progress_util
import utils


def get_extents_from_coverings(aggregation_id, zoom):
    extents = []
    filepaths = glob('aggregation-store/{}/*-*-*-{}-*.csv'.format(aggregation_id, zoom))
    for filepath in filepaths:
        filename = filepath.split('/')[-1]
        parts = filename.replace('.csv', '').split('-')
        extent_z, extent_x, extent_y = [int(a) for a in parts[:3]]
        extents.append(mercantile.Tile(x=extent_x, y=extent_y, z=extent_z))
    return extents


def get_tile_to_extent_map(extents, zoom):
    tile_to_extent_map = {}
    for extent in extents:
        for child in mercantile.children(extent, zoom=zoom):
            tile_to_extent_map[child] = extent
    return tile_to_extent_map


def get_simplified_extents(extents, zoom):
    simplified_extents_unlimited = list(mercantile.simplify(extents))
    simplified_extents = []
    for unlimited in simplified_extents_unlimited:
        if unlimited.z == zoom:
            simplified_extents.append(mercantile.parent(unlimited, zoom=zoom - 1))
        elif unlimited.z >= zoom - utils.num_overviews:
            simplified_extents.append(unlimited)
        else:
            simplified_extents += list(
                mercantile.children(unlimited, zoom=zoom - utils.num_overviews)
            )
    return simplified_extents


def tiles_intersect(a, b):
    if a == b:
        return True
    if a.z < b.z and mercantile.parent(b, zoom=a.z) == a:
        return True
    if b.z < a.z and mercantile.parent(a, zoom=b.z) == b:
        return True
    return False


def is_parent_of_dirty_aggregation_tile(tile, dirty_aggregation_tiles):
    for dirty_aggregation_tile in dirty_aggregation_tiles:
        if tiles_intersect(dirty_aggregation_tile, tile):
            return True
    return False


def not_in_previous_aggregation(filename, aggregation_ids):
    return len(glob('aggregation-store/{}/{}'.format(aggregation_ids[-2], filename))) == 0


def write_downsampling_todos(progress, overall_task):
    aggregation_ids = utils.get_aggregation_ids()
    aggregation_id = aggregation_ids[-1]

    dirty_aggregation_tiles = []
    if len(aggregation_ids) >= 2:
        dirty_aggregation_filenames = utils.get_dirty_aggregation_filenames(
            aggregation_id, aggregation_ids[-2]
        )
        for filename in dirty_aggregation_filenames:
            z, x, y, _ = [
                int(a) for a in filename.replace('-aggregation.csv', '').split('-')
            ]
            dirty_aggregation_tiles.append(mercantile.Tile(x=x, y=y, z=z))

    filepaths = sorted(
        glob('aggregation-store/{}/*-downsampling.csv'.format(aggregation_id))
    )
    step = progress.add_task('downsampling todos', total=max(len(filepaths), 1))
    dirty_count = 0
    for filepath in filepaths:
        filename = filepath.split('/')[-1]
        z, x, y, _ = [
            int(a) for a in filename.replace('-downsampling.csv', '').split('-')
        ]
        if (
            len(aggregation_ids) < 2
            or is_parent_of_dirty_aggregation_tile(
                mercantile.Tile(x=x, y=y, z=z), dirty_aggregation_tiles
            )
            or not_in_previous_aggregation(filename, aggregation_ids)
        ):
            with open('{}.todo'.format(filepath), 'w') as f:
                f.write('')
            dirty_count += 1
        progress.advance(step)
    progress.remove_task(step)
    progress.console.log('marked {} downsampling .todo file(s)'.format(dirty_count))
    progress.advance(overall_task)


def write_downsampling_items(progress, overall_task):
    aggregation_ids = utils.get_aggregation_ids()
    aggregation_id = aggregation_ids[-1]

    command = 'rm -f aggregation-store/{}/*-downsampling.csv'.format(aggregation_id)
    utils.run_command(command)

    child_zooms = list(reversed(range(1, 32)))
    step = progress.add_task('downsampling coverings', total=len(child_zooms))
    written = 0

    for child_zoom in child_zooms:
        progress.update(
            step,
            description='downsampling coverings · z{}'.format(child_zoom),
        )
        extents = get_extents_from_coverings(aggregation_id, child_zoom)
        if len(extents) == 0:
            progress.advance(step)
            continue

        tile_to_extent_map = get_tile_to_extent_map(extents, child_zoom)
        simplified_extents = get_simplified_extents(extents, child_zoom)
        inner = progress.add_task(
            'z{} extents'.format(child_zoom),
            total=max(len(simplified_extents), 1),
        )
        for simplified_extent in simplified_extents:
            involved_extents = set({})
            children = list(mercantile.children(simplified_extent, zoom=child_zoom))
            for child in children:
                if child in tile_to_extent_map:
                    involved_extents.add(tile_to_extent_map[child])
            lines = ['filename\n']
            for involved_extent in involved_extents:
                lines.append(
                    '{}-{}-{}-{}.pmtiles\n'.format(
                        involved_extent.z,
                        involved_extent.x,
                        involved_extent.y,
                        child_zoom,
                    )
                )
            out_filepath = 'aggregation-store/{}/{}-{}-{}-{}-downsampling.csv'.format(
                aggregation_id,
                simplified_extent.z,
                simplified_extent.x,
                simplified_extent.y,
                child_zoom - 1,
            )
            with open(out_filepath, 'w') as f:
                f.writelines(lines)
            written += 1
            progress.advance(inner)
        progress.remove_task(inner)
        progress.advance(step)

    progress.remove_task(step)
    progress.console.log('wrote {} downsampling csv file(s)'.format(written))
    progress.advance(overall_task)


def main():
    with progress_util.make_progress() as progress:
        overall = progress.add_task('downsampling covering', total=2)
        progress.update(overall, description='1/2 write downsampling items')
        write_downsampling_items(progress, overall)
        progress.update(overall, description='2/2 write downsampling todos')
        write_downsampling_todos(progress, overall)
        progress.update(overall, description='downsampling covering done')


if __name__ == '__main__':
    main()
