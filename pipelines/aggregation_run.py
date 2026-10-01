# Execute dirty aggregation jobs (reproject → merge → tile).
# Requires downloader.py staging files into tmp-store/.
from glob import glob
import os
import shutil
import threading
import time
from multiprocessing import Pool, Queue
from queue import Empty

import aggregation_merge
import aggregation_reproject
import aggregation_tile
import progress_util
import utils

# Set in worker processes via Pool initializer
_STATUS_QUEUE = None


def _init_worker(status_queue):
    global _STATUS_QUEUE
    _STATUS_QUEUE = status_queue


def _status(item, phase):
    if _STATUS_QUEUE is not None:
        _STATUS_QUEUE.put((item, phase))


def run(filepath):
    filename = filepath.split('/')[-1]
    item = filename.replace('-aggregation.csv', '')
    if os.path.isfile('{}.done'.format(filepath)):
        _status(item, 'skip')
        return 'skip'

    _status(item, 'queue')
    queue_folder = 'tmp-store/queue'
    os.makedirs(queue_folder, exist_ok=True)
    shutil.copy(filepath, '{}/{}.tmp'.format(queue_folder, filename))
    os.rename(
        '{}/{}.tmp'.format(queue_folder, filename),
        '{}/{}'.format(queue_folder, filename),
    )

    ready_folder = 'tmp-store/ready'
    os.makedirs(ready_folder, exist_ok=True)
    _status(item, 'waiting for downloader')
    while not os.path.isfile('{}/{}'.format(ready_folder, filename)):
        time.sleep(1)

    tmp_folder = 'tmp-store/{}'.format(item)
    os.makedirs(tmp_folder, exist_ok=True)

    _status(item, 'reproject')
    aggregation_reproject.reproject(filepath, tmp_folder)
    _status(item, 'merge')
    aggregation_merge.merge(filepath, tmp_folder)
    _status(item, 'tile')
    aggregation_tile.main(filepath, tmp_folder)
    shutil.rmtree(tmp_folder)

    with open('{}.done'.format(filepath), 'w') as f:
        f.write('')
    if os.path.isfile('{}.todo'.format(filepath)):
        os.remove('{}.todo'.format(filepath))
    ready_path = '{}/{}'.format(ready_folder, filename)
    if os.path.isfile(ready_path):
        os.remove(ready_path)

    _status(item, 'done')
    return 'ok'


def _drain_status(status_queue, progress, active_tasks, max_active=8):
    # Keep up to max_active live rows for in-flight jobs; overall bar is separate.
    while True:
        try:
            item, phase = status_queue.get_nowait()
        except Empty:
            break

        if phase in ('done', 'skip'):
            task_id = active_tasks.pop(item, None)
            if task_id is not None:
                progress.remove_task(task_id)
            continue

        if item not in active_tasks:
            if len(active_tasks) >= max_active:
                # Drop oldest tracked row to make room
                old_item = next(iter(active_tasks))
                progress.remove_task(active_tasks.pop(old_item))
            active_tasks[item] = progress.add_task(
                '{} · {}'.format(item, phase),
                total=None,
            )
        else:
            progress.update(
                active_tasks[item],
                description='{} · {}'.format(item, phase),
            )


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

    status_queue = Queue()
    active_tasks = {}
    workers = os.cpu_count() or 4

    with progress_util.make_progress() as progress:
        overall = progress.add_task(
            'aggregation run ({})'.format(aggregation_id),
            total=len(dirty_filepaths),
        )
        progress.console.log(
            '{} dirty item(s), {} worker(s). Overall % advances when a full job finishes '
            '(reproject+merge+tile). Live rows show in-flight phase. Ensure downloader.py is running.'
            .format(len(dirty_filepaths), workers)
        )

        stop_listener = threading.Event()

        def listen():
            while not stop_listener.is_set():
                _drain_status(status_queue, progress, active_tasks, max_active=workers)
                time.sleep(0.2)
            _drain_status(status_queue, progress, active_tasks, max_active=workers)

        listener = threading.Thread(target=listen, daemon=True)
        listener.start()

        try:
            with Pool(processes=workers, initializer=_init_worker, initargs=(status_queue,)) as pool:
                for result in pool.imap_unordered(run, dirty_filepaths, chunksize=1):
                    progress.advance(overall)
        finally:
            stop_listener.set()
            listener.join(timeout=2.0)

        progress.update(overall, description='aggregation run done')


if __name__ == '__main__':
    main()
