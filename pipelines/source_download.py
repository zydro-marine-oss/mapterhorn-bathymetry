# Download source files listed in source-catalog/{source}/file_list.txt.
# Defaults to up to 8 parallel workers with Rich progress.
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from urllib.parse import unquote, urlparse
import atexit
import os
import signal
import sys
import threading

import requests
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

import utils

DEFAULT_WORKERS = 8
CHUNK_SIZE = 1024 * 256
# (connect, read) — read timeout applies between chunks while streaming
HTTP_TIMEOUT = (15, 120)

_stop = threading.Event()
_active_responses = set()
_active_lock = threading.Lock()
_executor = None
_interrupt_count = 0


def request_stop():
    _stop.set()
    with _active_lock:
        responses = list(_active_responses)
        _active_responses.clear()
    for response in responses:
        try:
            response.close()
        except Exception:
            pass


def _shutdown_executor(wait=False):
    global _executor
    request_stop()
    executor = _executor
    _executor = None
    if executor is None:
        return
    try:
        executor.shutdown(wait=wait, cancel_futures=True)
    except TypeError:
        executor.shutdown(wait=wait)


def _handle_signal(signum, frame):
    global _interrupt_count
    _interrupt_count += 1
    request_stop()
    if _interrupt_count == 1:
        print('\ninterrupt: stopping downloads (Ctrl+C again to force quit)...', flush=True)
        return
    print('\nforce quit', flush=True)
    os._exit(130)


def install_signal_handlers():
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    atexit.register(_shutdown_executor)


def parse_workers(argv):
    env = os.environ.get('MAPTERHORN_DOWNLOAD_WORKERS')
    if env is not None and env.strip() != '':
        return max(1, int(env))
    if len(argv) > 2:
        return max(1, int(argv[2]))
    return DEFAULT_WORKERS


def filename_from_url(url):
    path = unquote(urlparse(url).path)
    name = os.path.basename(path.rstrip('/'))
    if name == '':
        raise ValueError('could not derive filename from url: {}'.format(url))
    return name


def short_label(index, total, filename, width=40):
    prefix = '[{}/{}] '.format(index, total)
    remain = max(8, width - len(prefix))
    if len(filename) <= remain:
        name = filename
    else:
        name = '…' + filename[-(remain - 1):]
    return prefix + name


def download_one(source, url, index, total, progress, task_id):
    if _stop.is_set():
        raise InterruptedError('cancelled')

    filename = filename_from_url(url)
    dest = os.path.join('source-store', source, filename)
    existing = os.path.getsize(dest) if os.path.isfile(dest) else 0

    headers = {}
    if existing > 0:
        headers['Range'] = 'bytes={}-'.format(existing)

    response = requests.get(
        url, stream=True, headers=headers, timeout=HTTP_TIMEOUT
    )
    with _active_lock:
        _active_responses.add(response)
    try:
        if _stop.is_set():
            raise InterruptedError('cancelled')

        # Local file already complete (resume Range past EOF)
        if existing > 0 and response.status_code == 416:
            progress.update(
                task_id,
                total=existing,
                completed=existing,
                description=short_label(index, total, filename) + ' cached',
            )
            return 'cached'

        # Server ignored Range and resent the whole file
        if existing > 0 and response.status_code == 200:
            existing = 0
            mode = 'wb'
        elif existing > 0 and response.status_code == 206:
            mode = 'ab'
        elif response.status_code == 200:
            existing = 0
            mode = 'wb'
        else:
            response.raise_for_status()

        total_size = None
        content_length = response.headers.get('Content-Length')
        if content_length is not None:
            remaining = int(content_length)
            if response.status_code == 206:
                total_size = existing + remaining
            else:
                total_size = remaining

        # Nothing left to fetch
        if total_size is not None and existing >= total_size:
            progress.update(
                task_id,
                total=existing,
                completed=existing,
                description=short_label(index, total, filename) + ' cached',
            )
            return 'cached'

        progress.update(
            task_id,
            total=total_size,
            completed=existing,
            description=short_label(index, total, filename),
            visible=True,
        )

        with open(dest, mode) as out:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if _stop.is_set():
                    raise InterruptedError('cancelled')
                if not chunk:
                    continue
                out.write(chunk)
                progress.advance(task_id, len(chunk))

        progress.update(
            task_id,
            description=short_label(index, total, filename) + ' done',
        )
        return 'ok'
    finally:
        with _active_lock:
            _active_responses.discard(response)
        try:
            response.close()
        except Exception:
            pass


def download_from_internet(source, workers=DEFAULT_WORKERS):
    global _executor

    with open('../source-catalog/{}/file_list.txt'.format(source)) as f:
        urls = [l.strip() for l in f.readlines() if l.strip()]
    total = len(urls)
    if total == 0:
        print('no urls in file_list.txt')
        return

    workers = max(1, min(workers, total))
    # Keep only a small window of in-flight futures (not one per URL).
    in_flight_limit = workers * 2
    print('downloading {} files with {} worker(s)...'.format(total, workers))

    progress = Progress(
        SpinnerColumn(),
        TextColumn('{task.description}', justify='left'),
        BarColumn(bar_width=28),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        expand=True,
    )

    errors = []
    cancelled = False
    completed = 0
    executor = ThreadPoolExecutor(max_workers=workers)
    _executor = executor
    pending = {}
    url_iter = enumerate(urls, start=1)
    # Reuse a small pool of live bars instead of 25k Rich tasks.
    free_slots = []

    def take_slot():
        if free_slots:
            return free_slots.pop()
        return progress.add_task('starting…', total=None)

    def submit_one(index, url):
        slot = take_slot()
        future = executor.submit(
            download_one, source, url, index, total, progress, slot
        )
        pending[future] = (url, slot)

    try:
        with progress:
            overall = progress.add_task(
                'files {}/{}'.format(0, total), total=total
            )
            while len(pending) < in_flight_limit:
                try:
                    index, url = next(url_iter)
                except StopIteration:
                    break
                submit_one(index, url)

            while pending:
                if _stop.is_set():
                    cancelled = True
                    break
                done, _ = wait(
                    set(pending), timeout=0.5, return_when=FIRST_COMPLETED
                )
                for future in done:
                    url, slot = pending.pop(future)
                    try:
                        future.result()
                    except InterruptedError:
                        cancelled = True
                    except Exception as exc:
                        if _stop.is_set():
                            cancelled = True
                        else:
                            errors.append((url, exc))
                    completed += 1
                    progress.update(
                        overall,
                        completed=completed,
                        description='files {}/{}'.format(completed, total),
                    )
                    progress.reset(slot, total=None, description='idle')
                    free_slots.append(slot)
                    if cancelled:
                        break
                    try:
                        index, next_url = next(url_iter)
                        submit_one(index, next_url)
                    except StopIteration:
                        pass
                if cancelled:
                    break
    finally:
        request_stop()
        for future in list(pending):
            future.cancel()
        # Never block forever on hung sockets after cancel.
        try:
            executor.shutdown(wait=not cancelled, cancel_futures=True)
        except TypeError:
            executor.shutdown(wait=not cancelled)
        if _executor is executor:
            _executor = None

    if cancelled:
        print('download cancelled; partial files kept for resume')
        raise SystemExit(130)

    if errors:
        for url, exc in errors:
            print('FAILED {}: {}'.format(url, exc))
        raise RuntimeError('{} download(s) failed'.format(len(errors)))

    print('downloaded {} file(s).'.format(total))


def main():
    if len(sys.argv) < 2:
        print('usage: source_download.py <source> [workers]')
        print('  workers default: {} (or MAPTERHORN_DOWNLOAD_WORKERS)'.format(DEFAULT_WORKERS))
        exit()

    install_signal_handlers()
    source = sys.argv[1]
    workers = parse_workers(sys.argv)
    print('downloading {}...'.format(source))
    utils.create_folder('source-store/{}/'.format(source))
    download_from_internet(source, workers=workers)


if __name__ == '__main__':
    main()
