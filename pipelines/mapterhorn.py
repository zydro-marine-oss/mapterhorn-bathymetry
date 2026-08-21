# Mapterhorn operator CLI — one entry point for the whole pipeline.
#
# From pipelines/:
#   uv run mapterhorn --help
#   uv run mapterhorn jobs autodownload -y
#   uv run mapterhorn covering
import argparse
import os
import subprocess
import sys
from pathlib import Path

PIPELINES_DIR = Path(__file__).resolve().parent


def load_dotenv():
    env_path = PIPELINES_DIR / '.env'
    if not env_path.is_file():
        return
    with open(env_path) as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            if line.startswith('export '):
                line = line[len('export '):].strip()
            key, _, val = line.partition('=')
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


def run_script(script, argv=None, env=None):
    cmd = [sys.executable, script] + list(argv or [])
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.call(cmd, cwd=str(PIPELINES_DIR), env=full_env)


def cmd_help(_args):
    print('''Mapterhorn pipeline CLI (run from pipelines/, or: uv run mapterhorn …)

Two phases: get data, then build tiles.

1) Get data (resumable SQLite jobs):
     mapterhorn storage
     mapterhorn jobs autodownload -y
     mapterhorn jobs status --watch
     mapterhorn manage list

2) Build tiles:
     mapterhorn covering
     mapterhorn downloader          # terminal A
     mapterhorn aggregate           # terminal B
     mapterhorn downsample
     mapterhorn bundle --version 1

Or after sources are READY:
     mapterhorn all --version 1     # covering through bundle (no download)

Watch / recover:
     mapterhorn status
     mapterhorn retry-failed
     mapterhorn preflight
     mapterhorn jobs retry
     mapterhorn jobs reclaim

Also:
     mapterhorn shoreline
     mapterhorn manage load NAME -y
     mapterhorn manage clear NAME -y
     mapterhorn upload
''')
    return 0


def cmd_storage(_args):
    return run_script('storage_layout.py')


def cmd_preflight(_args):
    return run_script('preflight.py')


def cmd_status(_args):
    return run_script('status.py')


def cmd_shoreline(_args):
    return run_script('source_prepare_shoreline.py')


def cmd_covering(_args):
    rc = run_script('aggregation_covering.py')
    if rc != 0:
        return rc
    return run_script('downsampling_covering.py')


def cmd_downloader(_args):
    return run_script('downloader.py')


def cmd_aggregate(_args):
    return run_script('aggregation_run.py')


def cmd_downsample(_args):
    return run_script('downsampling_run.py')


def cmd_retry_failed(_args):
    return run_script('retry_failed.py')


def cmd_upload(_args):
    return run_script('upload.py')


def cmd_bundle(args):
    version = str(args.version)
    rc = run_script('remove_dangling_pmtiles.py')
    if rc != 0:
        return rc
    rc = run_script('bundle.py', [version], env={'TMPDIR': '/tmp'})
    if rc != 0:
        return rc
    rc = run_script('download_urls.py', [version])
    if rc != 0:
        return rc
    return run_script('attribution.py')


def cmd_all(args):
    version = str(args.version)
    steps = [
        ('preflight', ['preflight.py'], None),
        ('aggregation covering', ['aggregation_covering.py'], None),
        ('downsampling covering', ['downsampling_covering.py'], None),
    ]
    for label, argv, env in steps:
        print('=== {} ==='.format(label))
        rc = run_script(argv[0], argv[1:], env=env)
        if rc != 0:
            return rc

    print('=== downloader (background) ===')
    dl = subprocess.Popen(
        [sys.executable, 'downloader.py'],
        cwd=str(PIPELINES_DIR),
        env=os.environ.copy(),
    )
    try:
        for label, argv, env in [
            ('aggregate', ['aggregation_run.py'], None),
            ('downsample', ['downsampling_run.py'], None),
            ('remove dangling pmtiles', ['remove_dangling_pmtiles.py'], None),
            ('bundle', ['bundle.py', version], {'TMPDIR': '/tmp'}),
            ('download urls', ['download_urls.py', version], None),
            ('attribution', ['attribution.py'], None),
            ('status', ['status.py'], None),
        ]:
            print('=== {} ==='.format(label))
            rc = run_script(argv[0], argv[1:], env=env)
            if rc != 0:
                return rc
    finally:
        dl.terminate()
        try:
            dl.wait(timeout=30)
        except subprocess.TimeoutExpired:
            dl.kill()
    return 0


def cmd_manage(args):
    # Forward remaining argv after 'manage'
    return run_script('source_manage.py', args.manage_argv)


def cmd_jobs(args):
    return run_script('job_runner.py', args.jobs_argv)


def cmd_sources(args):
    # mapterhorn sources gebco emodnet -y
    argv = ['load'] + list(args.sources)
    if args.yes:
        argv.append('-y')
    if args.force:
        argv.append('--force')
    if args.dry_run:
        argv.append('--dry-run')
    return run_script('source_manage.py', argv)


def build_parser():
    parser = argparse.ArgumentParser(
        prog='mapterhorn',
        description='Mapterhorn terrain + bathymetry pipeline',
    )
    sub = parser.add_subparsers(dest='command')

    p = sub.add_parser('help', help='show operator cheat sheet')
    p.set_defaults(func=cmd_help)

    p = sub.add_parser('storage', help='show which disk each store is on')
    p.set_defaults(func=cmd_storage)

    p = sub.add_parser('preflight', help='dependency / data readiness checks')
    p.set_defaults(func=cmd_preflight)

    p = sub.add_parser('status', help='aggregation run status')
    p.set_defaults(func=cmd_status)

    p = sub.add_parser('shoreline', help='build shoreline land/ocean mask')
    p.set_defaults(func=cmd_shoreline)

    p = sub.add_parser('covering', help='plan aggregation + downsampling work')
    p.set_defaults(func=cmd_covering)

    p = sub.add_parser('downloader', help='stage rasters into tmp-store')
    p.set_defaults(func=cmd_downloader)

    p = sub.add_parser('aggregate', help='build local-maxzoom tiles')
    p.set_defaults(func=cmd_aggregate)

    p = sub.add_parser('downsample', help='build overview zoom levels')
    p.set_defaults(func=cmd_downsample)

    p = sub.add_parser('bundle', help='pack PMTiles for distribution')
    p.add_argument('--version', default='1', help='bundle version tag (default 1)')
    p.set_defaults(func=cmd_bundle)

    p = sub.add_parser('all', help='covering through bundle (does not download)')
    p.add_argument('--version', default='1', help='bundle version tag (default 1)')
    p.set_defaults(func=cmd_all)

    p = sub.add_parser('retry-failed', help='requeue failed aggregation items')
    p.set_defaults(func=cmd_retry_failed)

    p = sub.add_parser('upload', help='upload finished PMTiles')
    p.set_defaults(func=cmd_upload)

    p = sub.add_parser('manage', help='list/clear/load/reload sources')
    p.add_argument('manage_argv', nargs=argparse.REMAINDER,
                   help='args passed to source_manage.py')
    p.set_defaults(func=cmd_manage)

    p = sub.add_parser('jobs', help='SQLite source download/prep jobs')
    p.add_argument('jobs_argv', nargs=argparse.REMAINDER,
                   help='args passed to job_runner.py')
    p.set_defaults(func=cmd_jobs)

    p = sub.add_parser('sources', help='load named sources (download + prep)')
    p.add_argument('sources', nargs='*', help='source ids')
    p.add_argument('--yes', '-y', action='store_true')
    p.add_argument('--force', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    p.set_defaults(func=cmd_sources)

    return parser


def main(argv=None):
    load_dotenv()
    os.chdir(PIPELINES_DIR)
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if not argv:
        return cmd_help(None)

    args = parser.parse_args(argv)
    if not getattr(args, 'command', None):
        return cmd_help(None)
    if args.command == 'manage':
        argv_rest = list(args.manage_argv or [])
        if argv_rest and argv_rest[0] == '--':
            argv_rest = argv_rest[1:]
        args.manage_argv = argv_rest
        if not args.manage_argv:
            return run_script('source_manage.py', ['--help'])
    if args.command == 'jobs':
        argv_rest = list(args.jobs_argv or [])
        if argv_rest and argv_rest[0] == '--':
            argv_rest = argv_rest[1:]
        args.jobs_argv = argv_rest
        if not args.jobs_argv:
            return run_script('job_runner.py', ['--help'])
    return args.func(args) or 0


if __name__ == '__main__':
    sys.exit(main())
