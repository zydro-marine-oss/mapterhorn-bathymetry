# Execute dirty aggregation jobs (reproject → merge → tile).
# Requires downloader.py staging files into tmp-store/.
from glob import glob
import os
import shutil
import time
from multiprocessing import Pool

import aggregation_merge
import aggregation_reproject
import aggregation_tile
import progress_util
import utils


def run(filepath):
    filename = filepath.split('/')[-1]
    item = filename.replace('-aggregation.csv', '')
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

    tmp_folder = 'tmp-store/{}'.format(item)
    os.makedirs(tmp_folder, exist_ok=True)
    aggregation_reproject.reproject(filepath, tmp_folder)
    aggregation_merge.merge(filepath, tmp_folder)
    aggregation_tile.main(filepath, tmp_folder)
    shutil.rmtree(tmp_folder)

    with open('{}.done'.format(filepath), 'w') as f:
        f.write('')
    if os.path.isfile('{}.todo'.format(filepath)):
        os.remove('{}.todo'.format(filepath))
    ready_path = '{}/{}'.format(ready_folder, filename)
    if os.path.isfile(ready_path):
        os.remove(ready_path)
    return 'ok'


def main():
    aggregation_ids = utils.get_aggregation_ids()
    aggregation_id = aggregation_ids[-1]
    dirty_filepaths = [
        filepath.replace('.todo', '')
        for filepath in glob(
            'aggregation-store/{}/*-aggregation.csv.todo'.format(aggregation_id)
        )
    ]
    dirty_filepaths = sorted(dirty_filepaths)

    if len(dirty_filepaths) == 0:
        print('nothing to do.')
        return

    with progress_util.make_progress() as progress:
        overall = progress.add_task(
            'aggregation run ({})'.format(aggregation_id),
            total=len(dirty_filepaths),
        )
        progress.console.log(
            'aggregating {} dirty item(s); ensure downloader.py is running'
            .format(len(dirty_filepaths))
        )
        with Pool() as pool:
            for result in pool.imap_unordered(run, dirty_filepaths, chunksize=1):
                if result == 'skip':
                    progress.console.log('skipped already-done item')
                progress.advance(overall)
        progress.update(overall, description='aggregation run done')


if __name__ == '__main__':
    main()
