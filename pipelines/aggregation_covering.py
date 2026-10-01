# Plan aggregation work from source-store/*/bounds.csv.
# Writes aggregation-store/{aggregation_id}/*-aggregation.csv (+ .todo markers).
from glob import glob

import mercantile
from ulid import ULID

import progress_util
import utils


def get_mercator_resolutions(minzoom, maxzoom):
    resolutions = []
    for z in range(minzoom, maxzoom + 1):
        tile = mercantile.Tile(x=0, y=0, z=z)
        bounds = mercantile.xy_bounds(tile)
        resolutions.append((bounds.right - bounds.left) / 512)
    return resolutions


def bounds_intersect_no_anitmeridian_crossing(a, b):
    left_a, bottom_a, right_a, top_a = a
    left_b, bottom_b, right_b, top_b = b
    dont_intersect = False
    dont_intersect |= right_a <= left_b
    dont_intersect |= right_b <= left_a
    dont_intersect |= top_a <= bottom_b
    dont_intersect |= top_b <= bottom_a
    return not dont_intersect


def split_at_antimeridian(bbox):
    left, bottom, right, top = bbox
    if left < right:
        return [bbox]
    bbox_1 = (left, bottom, utils.X_MAX_3857, top)
    bbox_2 = (utils.X_MIN_3857, bottom, right, top)
    return [bbox_1, bbox_2]


def bounds_intersect(a, b):
    for aa in split_at_antimeridian(a):
        for bb in split_at_antimeridian(b):
            if bounds_intersect_no_anitmeridian_crossing(aa, bb):
                return True
    return False


def get_intersecting_tiles_dfs(bounds, tile, zoom):
    tile_bounds = mercantile.xy_bounds(tile)
    if not bounds_intersect(bounds, tile_bounds):
        return []
    if tile.z == zoom:
        return [tile]
    result = []
    for child in mercantile.children(tile, zoom=tile.z + 1):
        result += get_intersecting_tiles_dfs(bounds, child, zoom)
    return result


def count_bounds_rows(filepath):
    with open(filepath) as f:
        f.readline()
        return sum(1 for line in f if line.strip())


def get_macrotile_map(progress, overall_task):
    macrotile_map = {}
    filepaths = sorted(glob('source-store/*/bounds.csv'))
    mercator_resolutions = get_mercator_resolutions(0, 32)
    num_sources = len(filepaths)
    if num_sources == 0:
        progress.console.log('no source-store/*/bounds.csv files found')
        return macrotile_map

    row_totals = [count_bounds_rows(path) for path in filepaths]
    total_rows = sum(row_totals)
    progress.console.log(
        'macrotile map: {} source(s), {} bounds row(s)'.format(num_sources, total_rows)
    )
    step = progress.add_task('macrotile map', total=max(total_rows, 1))

    for source_i, filepath in enumerate(filepaths):
        source = filepath.split('/')[1]
        progress.update(
            step,
            description='macrotile map · {} ({}/{})'.format(source, source_i + 1, num_sources),
        )
        with open(filepath) as f:
            f.readline()
            for line in f:
                line = line.strip()
                if line == '':
                    continue
                filename, left, bottom, right, top, width, height = line.split(',')
                width, height = [int(a) for a in [width, height]]
                left, bottom, right, top = [float(a) for a in [left, bottom, right, top]]

                buffer = 2 * utils.macrotile_buffer_3857
                buffered_bounds = (
                    left - buffer,
                    bottom - buffer,
                    right + buffer,
                    top + buffer,
                )
                tiles = get_intersecting_tiles_dfs(
                    buffered_bounds,
                    mercantile.Tile(x=0, y=0, z=0),
                    utils.macrotile_z,
                )
                maxzoom = get_smallest_overzoom(
                    left, bottom, right, top, width, height, mercator_resolutions
                )
                maxzoom = max(maxzoom, utils.macrotile_z)

                for tile in tiles:
                    if (tile.x, tile.y) not in macrotile_map:
                        macrotile_map[(tile.x, tile.y)] = {'sources': {}}
                    if source not in macrotile_map[(tile.x, tile.y)]['sources']:
                        macrotile_map[(tile.x, tile.y)]['sources'][source] = []
                    macrotile_map[(tile.x, tile.y)]['sources'][source].append({
                        'filename': filename,
                        'maxzoom': maxzoom,
                    })
                progress.advance(step)

    progress.remove_task(step)
    progress.console.log(
        'macrotile map done: {} unique macrotiles'.format(len(macrotile_map))
    )
    progress.advance(overall_task)
    return macrotile_map


def get_smallest_overzoom(left, bottom, right, top, width, height, mercator_resolutions):
    horizontal_resolution = (right - left) / width if left < right else (left - right) / width
    vertical_resolution = (top - bottom) / height
    for z in range(len(mercator_resolutions)):
        if mercator_resolutions[z] < horizontal_resolution and mercator_resolutions[z] < vertical_resolution:
            return z
    raise ValueError(
        'No overzoom found. (left, bottom, right, top, width, height) = {}'
        .format((left, bottom, right, top, width, height))
    )


def add_group_ids(macrotile_map, progress, overall_task):
    total = len(macrotile_map)
    step = progress.add_task('group ids', total=max(total, 1))
    for tile_tuple in macrotile_map:
        group_id_parts = set({})
        for source in macrotile_map[tile_tuple]['sources']:
            for source_item in macrotile_map[tile_tuple]['sources'][source]:
                group_id_parts.add((source, source_item['maxzoom']))
        macrotile_map[tile_tuple]['group_id'] = tuple(sorted(list(group_id_parts)))
        progress.advance(step)
    progress.remove_task(step)
    progress.advance(overall_task)


def get_aggregation_tiles_dfs(candidate, macrotile_map):
    if candidate.z == utils.macrotile_z:
        return [candidate]
    macrotiles = list(mercantile.children(candidate, zoom=utils.macrotile_z))
    group_ids = set({})
    for macrotile in macrotiles:
        tile_tuple = (macrotile.x, macrotile.y)
        if tile_tuple in macrotile_map:
            group_ids.add(macrotile_map[tile_tuple]['group_id'])
    if len(group_ids) == 0:
        return []
    if len(group_ids) == 1:
        group_id = list(group_ids)[0]
        maxzoom = 0
        for part in group_id:
            maxzoom = max(maxzoom, part[1])
        if candidate.z >= maxzoom - utils.num_overviews:
            return [candidate]
    result = []
    for child in mercantile.children(candidate, zoom=candidate.z + 1):
        result += get_aggregation_tiles_dfs(child, macrotile_map)
    return result


def get_aggregation_tiles(macrotile_map, progress, overall_task):
    candidates = set({})
    for tile_tuple in macrotile_map.keys():
        candidates.add(
            mercantile.parent(
                mercantile.Tile(x=tile_tuple[0], y=tile_tuple[1], z=utils.macrotile_z),
                zoom=utils.macrotile_z - utils.num_overviews,
            )
        )
    candidates = sorted(candidates, key=lambda t: (t.z, t.x, t.y))
    step = progress.add_task('aggregation tiles', total=max(len(candidates), 1))
    aggregation_tiles = []
    for candidate in candidates:
        aggregation_tiles += get_aggregation_tiles_dfs(candidate, macrotile_map)
        progress.advance(step)
    progress.remove_task(step)
    progress.console.log(
        'aggregation tiles: {} from {} candidates'.format(len(aggregation_tiles), len(candidates))
    )
    progress.advance(overall_task)
    return aggregation_tiles


def write_aggregation_items(macrotile_map, aggregation_tiles, aggregation_id, progress, overall_task):
    folder = 'aggregation-store/{}'.format(aggregation_id)
    utils.create_folder(folder)
    total = len(aggregation_tiles)
    step = progress.add_task('write aggregation csv', total=max(total, 1))
    written = 0
    skipped = 0
    for aggregation_tile in aggregation_tiles:
        macrotiles = list(mercantile.children(aggregation_tile, zoom=utils.macrotile_z))
        lines = ['source,filename,maxzoom\n']
        line_tuples = set({})
        child_z = 0
        for macrotile in macrotiles:
            tile_tuple = (macrotile.x, macrotile.y)
            if tile_tuple not in macrotile_map:
                continue
            for source in macrotile_map[tile_tuple]['sources']:
                for source_item in macrotile_map[tile_tuple]['sources'][source]:
                    line_tuples.add((
                        source,
                        source_item['filename'],
                        str(source_item['maxzoom']),
                    ))
                    child_z = max(child_z, source_item['maxzoom'])
        if len(line_tuples) == 0:
            skipped += 1
            progress.advance(step)
            continue
        line_tuples = sorted(list(line_tuples))
        for line_tuple in line_tuples:
            lines.append('{}\n'.format(','.join(line_tuple)))
        out_path = '{}/{}-{}-{}-{}-aggregation.csv'.format(
            folder,
            aggregation_tile.z,
            aggregation_tile.x,
            aggregation_tile.y,
            child_z,
        )
        with open(out_path, 'w') as f:
            f.writelines(lines)
        written += 1
        progress.advance(step)
    progress.remove_task(step)
    progress.console.log(
        'wrote {} aggregation csv(s) ({} skipped empty)'.format(written, skipped)
    )
    progress.advance(overall_task)


def write_aggregation_todos(progress, overall_task):
    aggregation_ids = utils.get_aggregation_ids()
    aggregation_id = aggregation_ids[-1]
    if len(aggregation_ids) < 2:
        dirty_filepaths = sorted(
            glob('aggregation-store/{}/*-aggregation.csv'.format(aggregation_id))
        )
        progress.console.log(
            'first aggregation {}; marking all {} dirty'.format(
                aggregation_id, len(dirty_filepaths)
            )
        )
    else:
        dirty_filenames = utils.get_dirty_aggregation_filenames(
            aggregation_id, aggregation_ids[-2]
        )
        dirty_filepaths = [
            'aggregation-store/{}/{}'.format(aggregation_id, filename)
            for filename in dirty_filenames
        ]
        progress.console.log('{} dirty aggregation item(s)'.format(len(dirty_filepaths)))

    step = progress.add_task('write .todo markers', total=max(len(dirty_filepaths), 1))
    for dirty_filepath in dirty_filepaths:
        with open('{}.todo'.format(dirty_filepath), 'w') as f:
            f.write('')
        progress.advance(step)
    progress.remove_task(step)
    progress.advance(overall_task)


def main():
    with progress_util.make_progress() as progress:
        overall = progress.add_task('aggregation covering', total=5)
        progress.update(overall, description='1/5 macrotile map')
        macrotile_map = get_macrotile_map(progress, overall)

        progress.update(overall, description='2/5 group ids')
        add_group_ids(macrotile_map, progress, overall)

        progress.update(overall, description='3/5 aggregation tiles')
        aggregation_tiles = get_aggregation_tiles(macrotile_map, progress, overall)

        aggregation_id = str(ULID())
        utils.create_folder('aggregation-store/{}'.format(aggregation_id))
        progress.update(overall, description='4/5 write csv ({})'.format(aggregation_id))
        write_aggregation_items(
            macrotile_map, aggregation_tiles, aggregation_id, progress, overall
        )

        progress.update(overall, description='5/5 write todos')
        write_aggregation_todos(progress, overall)
        progress.update(overall, description='aggregation covering done')


if __name__ == '__main__':
    main()
