# Download source files listed in source-catalog/{source}/file_list.txt.
# Defaults to up to 8 parallel wget workers (override with argv or env).
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import sys
import threading

import utils

DEFAULT_WORKERS = 8
_PRINT_LOCK = threading.Lock()


def _log(message):
    with _PRINT_LOCK:
        print(message, flush=True)


def download_one(source, url, index, total, workers):
    # Parallel bars interleave badly; keep a live bar only for a single worker.
    if workers == 1:
        progress = '--progress=bar:force'
        stream = True
    else:
        progress = '--no-verbose'
        stream = False

    _log('[{}/{}] downloading {}...'.format(index, total, url))
    command = (
        'cd source-store/{} && wget --continue {} "{}"'
    ).format(source, progress, url)
    out, err = utils.run_command(command, silent=True, stream=stream)
    if err:
        raise RuntimeError('wget failed for {}: {}'.format(url, err))
    _log('[{}/{}] done {}'.format(index, total, url))


def download_from_internet(source, workers=DEFAULT_WORKERS):
    with open('../source-catalog/{}/file_list.txt'.format(source)) as f:
        urls = [l.strip() for l in f.readlines() if l.strip()]
    total = len(urls)
    if total == 0:
        print('no urls in file_list.txt')
        return

    workers = max(1, min(workers, total))
    print('downloading {} files with {} worker(s)...'.format(total, workers))

    if workers == 1:
        for j, url in enumerate(urls, start=1):
            download_one(source, url, j, total, workers)
        return

    errors = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(download_one, source, url, j, total, workers): url
            for j, url in enumerate(urls, start=1)
        }
        for future in as_completed(futures):
            url = futures[future]
            try:
                future.result()
            except Exception as exc:
                errors.append((url, exc))

    if errors:
        for url, exc in errors:
            print('FAILED {}: {}'.format(url, exc))
        raise RuntimeError('{} download(s) failed'.format(len(errors)))


def parse_workers(argv):
    env = os.environ.get('MAPTERHORN_DOWNLOAD_WORKERS')
    if env is not None and env.strip() != '':
        return max(1, int(env))
    if len(argv) > 2:
        return max(1, int(argv[2]))
    return DEFAULT_WORKERS


def main():
    if len(sys.argv) < 2:
        print('usage: source_download.py <source> [workers]')
        print('  workers default: {} (or MAPTERHORN_DOWNLOAD_WORKERS)'.format(DEFAULT_WORKERS))
        exit()

    source = sys.argv[1]
    workers = parse_workers(sys.argv)
    print('downloading {}...'.format(source))
    utils.create_folder('source-store/{}/'.format(source))
    download_from_internet(source, workers=workers)


if __name__ == '__main__':
    main()
