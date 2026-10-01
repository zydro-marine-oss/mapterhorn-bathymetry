# Download source files listed in source-catalog/{source}/file_list.txt.
# Defaults to up to 8 parallel workers with stacked Rich progress bars.
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

_stop = threading.Event()
_active_responses = set()
_active_lock = threading.Lock()
_executor = None


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


def _shutdown_executor():
    global _executor
    request_stop()
    executor = _executor
    _executor = None
    if executor is None:
        return
    try:
        executor.shutdown(wait=False, cancel_futures=True)
    except TypeError:
        executor.shutdown(wait=False)


def _handle_signal(signum, frame):
    # Cooperative cancel only; main loop exits after workers unwind.
    request_stop()


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


def short_label(index, total, filename, width=36):
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

    response = requests.get(url, stream=True, headers=headers, timeout=120)
    with _active_lock:
        _active_responses.add(response)
    try:
        if _stop.is_set():
            raise InterruptedError('cancelled')

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

        progress.update(
            task_id,
            total=total_size,
            completed=existing,
            description=short_label(index, total, filename),
        )

        with open(dest, mode) as out:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if _stop.is_set():
                    raise InterruptedError('cancelled')
                if not chunk:
                    continue
                out.write(chunk)
                progress.advance(task_id, len(chunk))

        progress.update(task_id, description=short_label(index, total, filename) + ' done')
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
    executor = ThreadPoolExecutor(max_workers=workers)
    _executor = executor
    futures = {}

    try:
        with progress:
            task_ids = [
                progress.add_task(short_label(j, total, filename_from_url(url)), total=None)
                for j, url in enumerate(urls, start=1)
            ]
            futures = {
                executor.submit(
                    download_one, source, url, j, total, progress, task_ids[j - 1]
                ): url
                for j, url in enumerate(urls, start=1)
            }
            pending = set(futures)
            while pending:
                if _stop.is_set():
                    cancelled = True
                    break
                done, pending = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
                for future in done:
                    url = futures[future]
                    try:
                        future.result()
                    except InterruptedError:
                        cancelled = True
                    except Exception as exc:
                        if _stop.is_set():
                            cancelled = True
                        else:
                            errors.append((url, exc))
                if cancelled:
                    break
    finally:
        # Wake/close any still-running workers. Do not use _stop after this to
        # decide success — request_stop() always sets it.
        request_stop()
        for future in futures:
            future.cancel()
        try:
            executor.shutdown(wait=True, cancel_futures=True)
        except TypeError:
            executor.shutdown(wait=True)
        if _executor is executor:
            _executor = None

    if cancelled:
        print('download cancelled; partial files kept for resume')
        raise SystemExit(130)

    if errors:
        for url, exc in errors:
            print('FAILED {}: {}'.format(url, exc))
        raise RuntimeError('{} download(s) failed'.format(len(errors)))


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
