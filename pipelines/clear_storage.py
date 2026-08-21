# Delete all (or selected) pipeline store directories under MAPTERHORN_DATA_ROOT.
#
#   uv run mapterhorn clear-storage -y
#   uv run python clear_storage.py --yes
#   uv run python clear_storage.py --stores source-store tmp-store -y
import argparse
import os
import shutil
import sys

import utils


def dir_size_bytes(path):
    total = 0
    if not os.path.isdir(path):
        return 0
    for root, _, files in os.walk(path):
        for name in files:
            fp = os.path.join(root, name)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total


def format_bytes(n):
    units = ['B', 'KiB', 'MiB', 'GiB', 'TiB']
    size = float(n)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            if unit == 'B':
                return '{} {}'.format(int(size), unit)
            return '{:.1f} {}'.format(size, unit)
        size /= 1024.0


def confirm(prompt, assume_yes):
    if assume_yes:
        return True
    answer = input('{} [y/N] '.format(prompt)).strip().lower()
    return answer in ('y', 'yes')


def main():
    parser = argparse.ArgumentParser(
        description='Clear Mapterhorn store directories (outside the git repo)',
    )
    parser.add_argument(
        '--stores',
        nargs='*',
        default=None,
        help='store names to clear (default: all). Choices: {}'.format(
            ', '.join(utils.STORE_NAMES)),
    )
    parser.add_argument('--yes', '-y', action='store_true', help='do not prompt')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    try:
        root = utils.require_data_config()
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 1

    names = list(args.stores) if args.stores else list(utils.STORE_NAMES)
    unknown = [n for n in names if n not in utils.STORE_NAMES]
    if unknown:
        print('unknown store(s): {}'.format(', '.join(unknown)), file=sys.stderr)
        return 1

    targets = []
    total = 0
    for name in names:
        path = utils.store_dir(name, create=False)
        exists = os.path.isdir(path) or os.path.isfile(path)
        size = dir_size_bytes(path) if os.path.isdir(path) else (
            os.path.getsize(path) if os.path.isfile(path) else 0)
        targets.append((name, path, exists, size))
        total += size

    print('MAPTERHORN_DATA_ROOT = {}'.format(root))
    print('Will clear {} store(s) (~{}):'.format(len(targets), format_bytes(total)))
    for name, path, exists, size in targets:
        mark = format_bytes(size) if exists else '(missing)'
        print('  {:<20} {}  {}'.format(name, mark, path))

    if args.dry_run:
        print('dry-run: not deleting')
        return 0

    if not confirm(
        'Delete these directories permanently? This cannot be undone.',
        args.yes,
    ):
        print('aborted')
        return 1

    for name, path, exists, _size in targets:
        if not exists:
            print('  skip {} (not present)'.format(name))
            continue
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        print('  removed {}'.format(path))

    print('done')
    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
