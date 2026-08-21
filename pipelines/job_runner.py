# Durable SQLite job runner for source download + prep.
#
# Examples (from pipelines/):
#   uv run python job_runner.py autodownload -y
#   uv run python job_runner.py enqueue autodownload -y
#   uv run python job_runner.py serve --download-workers 16 --prep-workers 4
#   uv run python job_runner.py status
#   uv run python job_runner.py retry
#   uv run python job_runner.py reclaim
import argparse
import json
import os
import signal
import sys
import threading
import time
import traceback
from multiprocessing import Process

import utils
import source_marker
from source_download import catalog_urls
from jobs import db as jobdb
from jobs import handlers

PIPELINES_DIR = os.path.dirname(os.path.abspath(__file__))
_SPIN = '⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'


def confirm(prompt, assume_yes):
    if assume_yes:
        return True
    answer = input('{} [y/N] '.format(prompt)).strip().lower()
    return answer in ('y', 'yes')


def catalog_sources():
    from glob import glob
    return sorted([
        path.rstrip('/').split('/')[-2]
        for path in glob(utils.catalog_path('*', 'metadata.json'))
    ])


def source_metadata(source):
    path = utils.catalog_path(source, 'metadata.json')
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        return json.load(f)


def resolve_sources(names, ocean_only=False, land_only=False):
    if not names and (ocean_only or land_only):
        names = catalog_sources()
    resolved = []
    for name in names:
        meta = source_metadata(name)
        domain = (meta or {}).get('domain', 'land')
        if ocean_only and domain not in ('ocean', 'both'):
            continue
        if land_only and domain not in ('land', 'both'):
            continue
        if domain == 'mask':
            continue
        resolved.append(name)
    return resolved


def autodownload_catalog_sources(include_debug=False):
    names = []
    for name in catalog_sources():
        if name.startswith('debug-') and not include_debug:
            continue
        meta = source_metadata(name) or {}
        if meta.get('domain') == 'mask':
            continue
        names.append(name)
    return names


def plan_autodownload(args):
    explicit = list(args.sources or [])
    if explicit or args.ocean or args.land:
        sources = resolve_sources(
            args.sources,
            ocean_only=args.ocean,
            land_only=args.land,
        )
        if not getattr(args, 'include_debug', False):
            sources = [s for s in sources if (not s.startswith('debug-') or s in explicit)]
    else:
        sources = autodownload_catalog_sources(
            include_debug=getattr(args, 'include_debug', False))

    if not sources and not args.sources and not args.ocean and not args.land:
        return None, 'no catalog sources found'

    named_only = bool(explicit)
    do_shoreline = (not args.skip_shoreline) and (not named_only or 's2coast' in explicit)

    skip_ready = []
    skip_nourl = []
    to_run = []
    for source in sources:
        if source == 's2coast':
            continue
        if source_metadata(source) is None:
            print('skip unknown catalog source: {}'.format(source))
            continue
        if args.force:
            urls = catalog_urls(source)
            if not urls and source not in explicit:
                skip_nourl.append(source)
            else:
                to_run.append(source)
            continue
        if source_marker.is_source_ready(source):
            skip_ready.append(source)
            continue
        urls = catalog_urls(source)
        if not urls:
            folder = source_marker.source_folder(source)
            if source in explicit and os.path.isdir(folder):
                to_run.append(source)
            else:
                skip_nourl.append(source)
            continue
        to_run.append(source)

    if do_shoreline:
        if not args.force and handlers.shoreline_is_ready():
            do_shoreline = False

    return {
        'to_run': to_run,
        'skip_ready': skip_ready,
        'skip_nourl': skip_nourl,
        'do_shoreline': do_shoreline,
        'force': bool(args.force),
    }, None


def enqueue_plan(conn, plan, label='autodownload'):
    config = {
        'to_run': plan['to_run'],
        'do_shoreline': plan['do_shoreline'],
        'force': plan['force'],
    }
    run_id = jobdb.create_run(conn, label, config)
    force = plan['force']
    payload = {'force': force}

    already_dl = []
    need_dl = []
    for source in plan['to_run']:
        if source_marker.is_download_complete(source) and not force:
            already_dl.append(source)
        else:
            need_dl.append(source)
    need_dl.sort(key=lambda name: (len(catalog_urls(name)), name))

    # Smaller downloads first (lower priority number = sooner)
    for i, source in enumerate(need_dl):
        priority = 100 + i
        jobdb.enqueue(
            conn, run_id, jobdb.KIND_SOURCE_DOWNLOAD, source,
            priority=priority, payload=payload, force=force,
        )

    for i, source in enumerate(already_dl):
        jobdb.enqueue(
            conn, run_id, jobdb.KIND_SOURCE_PREP, source,
            priority=50 + i, payload=payload, force=force,
        )

    if plan['do_shoreline']:
        jobdb.enqueue(
            conn, run_id, jobdb.KIND_SOURCE_PREP, 'shoreline',
            priority=40, payload=payload, force=force,
        )

    return run_id, len(need_dl), len(already_dl), (1 if plan['do_shoreline'] else 0)


def cmd_enqueue(args):
    plan, err = plan_autodownload(args)
    if err:
        print(err)
        return 1
    print('autodownload enqueue: {} to fetch/prepare, {} already READY, {} manual/no URLs'.format(
        len(plan['to_run']), len(plan['skip_ready']), len(plan['skip_nourl'])))
    if plan['do_shoreline']:
        print('  shoreline: will prepare')
    elif not args.skip_shoreline and not (args.sources or []):
        print('  shoreline: already ready')
    if plan['skip_nourl']:
        print('  skip (no file_list URLs): {}'.format(', '.join(plan['skip_nourl'])))
    if getattr(args, 'verbose', False) and plan['to_run']:
        print('  fetch: {}'.format(', '.join(plan['to_run'])))

    if not plan['to_run'] and not plan['do_shoreline']:
        print('nothing to enqueue')
        return 0

    if args.dry_run:
        print('dry-run: not writing jobs')
        return 0

    if not confirm('Enqueue jobs into SQLite and continue?', args.yes):
        print('aborted')
        return 1

    conn = jobdb.connect()
    run_id, n_dl, n_prep, n_shore = enqueue_plan(conn, plan)
    print('run {} enqueued: {} download, {} prep-only, {} shoreline'.format(
        run_id, n_dl, n_prep, n_shore))
    print('DB: {}'.format(jobdb.db_path()))
    conn.close()
    return 0


def _worker_loop(kinds, worker_id, stop_event, verbose):
    os.environ.setdefault('MAPTERHORN_PREP_POOL_SIZE', '1')
    os.environ.setdefault('OMP_NUM_THREADS', '1')
    os.environ.setdefault('GDAL_NUM_THREADS', '1')
    if len(kinds) == 1 and kinds[0] == jobdb.KIND_SOURCE_DOWNLOAD:
        os.environ.setdefault('MAPTERHORN_WGET_QUIET', '1')

    conn = jobdb.connect()
    idle_sleep = 0.5
    while not stop_event.is_set():
        jobdb.requeue_stale(conn)
        job = jobdb.claim(conn, kinds, worker_id)
        if job is None:
            time.sleep(idle_sleep)
            continue

        job_id = job['id']
        kind = job['kind']
        source = job['source']
        force = handlers.payload_force(job)
        stop_hb = threading.Event()

        def heartbeat_loop():
            hb_conn = jobdb.connect()
            while not stop_hb.wait(15.0):
                try:
                    jobdb.heartbeat(hb_conn, job_id)
                except Exception:
                    pass
            hb_conn.close()

        hb_thread = threading.Thread(target=heartbeat_loop, daemon=True)
        hb_thread.start()

        def on_line(text):
            text = (text or '').rstrip()
            if text == '':
                return
            try:
                jobdb.add_event(conn, job_id, text)
            except Exception:
                pass
            if verbose:
                print('[{} {}] {}'.format(kind, source, text), flush=True)

        try:
            on_line('claimed by {}'.format(worker_id))
            if kind == jobdb.KIND_SOURCE_DOWNLOAD:
                handlers.run_source_download(source, force=force, on_line=on_line)
                jobdb.succeed(conn, job_id)
                # Chain prep
                jobdb.enqueue_prep_after_download(
                    conn, job['run_id'], source, priority=50, force=force)
            elif kind == jobdb.KIND_SOURCE_PREP:
                handlers.run_source_prep(source, force=force, on_line=on_line)
                jobdb.succeed(conn, job_id)
            else:
                raise RuntimeError('unknown job kind {}'.format(kind))
        except Exception as e:
            err = '{}'.format(e)
            if verbose:
                traceback.print_exc()
            jobdb.fail(conn, job_id, err, requeue=True)
        finally:
            stop_hb.set()
            hb_thread.join(timeout=2.0)

    conn.close()


def _spawn_workers(download_workers, prep_workers, stop_event, verbose):
    procs = []
    for i in range(max(0, download_workers)):
        wid = 'download-{}'.format(i)
        p = Process(
            target=_worker_loop,
            args=([jobdb.KIND_SOURCE_DOWNLOAD], wid, stop_event, verbose),
            name=wid,
        )
        p.start()
        procs.append(p)
    for i in range(max(0, prep_workers)):
        wid = 'prep-{}'.format(i)
        p = Process(
            target=_worker_loop,
            args=([jobdb.KIND_SOURCE_PREP], wid, stop_event, verbose),
            name=wid,
        )
        p.start()
        procs.append(p)
    return procs


def _status_line(conn, spin_i, verbose=False):
    c = jobdb.counts(conn)
    done = c['succeeded'] + c['failed']
    total = c['total'] - c['cancelled']
    active = jobdb.active_jobs(conn)
    spin = _SPIN[spin_i % len(_SPIN)]
    left = '{}  {}/{} done  ·  {} succeeded  ·  {} failed  ·  {} downloading  ·  {} preparing  ·  {} queued'.format(
        spin,
        done,
        total,
        c['succeeded'],
        c['failed'],
        c['download_running'],
        c['prep_running'],
        c['pending'],
    )
    if verbose or not active:
        return left
    bits = []
    for row in active[:3]:
        ev = jobdb.latest_events(conn, row['id'], limit=1)
        step = ev[0]['message'] if ev else row['kind']
        if step.startswith('running: '):
            for part in step.split():
                if part.endswith('.py'):
                    step = os.path.basename(part).replace('source_', '').replace('.py', '')
                    break
        if len(step) > 28:
            step = step[:27] + '…'
        bits.append('{} {}'.format(row['source'], step))
    extra = len(active) - len(bits)
    if extra > 0:
        bits.append('+{}'.format(extra))
    if bits:
        return '{}  │  {}'.format(left, ' · '.join(bits))
    return left


def cmd_serve(args):
    os.environ.setdefault('MAPTERHORN_PREP_POOL_SIZE', '1')
    download_workers = max(0, args.download_workers)
    prep_workers = max(0, args.prep_workers)
    if download_workers + prep_workers < 1:
        print('need at least one worker')
        return 1

    conn = jobdb.connect()
    reclaimed = jobdb.requeue_stale(conn, stale_seconds=args.stale_seconds)
    if reclaimed:
        print('reclaimed {} stale running job(s)'.format(reclaimed))

    c = jobdb.counts(conn)
    print('jobs serve: {} download workers, {} prep workers'.format(
        download_workers, prep_workers))
    print('  pending={} running={} succeeded={} failed={}'.format(
        c['pending'], c['running'], c['succeeded'], c['failed']))
    print('  DB: {}'.format(jobdb.db_path()))

    from multiprocessing import Event
    stop_event = Event()
    procs = _spawn_workers(download_workers, prep_workers, stop_event, args.verbose)

    live = sys.stderr.isatty() and not args.verbose
    spin_i = 0
    exit_code = 0

    def handle_sig(_signum, _frame):
        stop_event.set()

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    try:
        while True:
            if stop_event.is_set():
                print('\nstopping workers (jobs remain in DB for resume)...', flush=True)
                break
            jobdb.requeue_stale(conn, stale_seconds=args.stale_seconds)
            c = jobdb.counts(conn)
            if c['pending'] == 0 and c['running'] == 0:
                if live:
                    sys.stderr.write('\r\033[2K')
                    sys.stderr.flush()
                print('all jobs idle  succeeded={} failed={}'.format(
                    c['succeeded'], c['failed']))
                if c['failed']:
                    exit_code = 1
                break
            spin_i += 1
            line = _status_line(conn, spin_i, verbose=args.verbose)
            if live:
                sys.stderr.write('\r\033[2K' + line)
                sys.stderr.flush()
            elif spin_i % 20 == 0:
                print(line, flush=True)
            time.sleep(0.25 if live else 1.0)
    finally:
        stop_event.set()
        for p in procs:
            p.join(timeout=5.0)
            if p.is_alive():
                p.terminate()
        if live:
            sys.stderr.write('\r\033[2K')
            sys.stderr.flush()
        conn.close()
    return exit_code


def cmd_status(args):
    conn = jobdb.connect()
    jobdb.requeue_stale(conn, stale_seconds=args.stale_seconds)
    c = jobdb.counts(conn)
    print('jobs  pending={}  running={}  succeeded={}  failed={}  cancelled={}'.format(
        c['pending'], c['running'], c['succeeded'], c['failed'], c['cancelled']))
    print('  download: pending={} running={}'.format(
        c['download_pending'], c['download_running']))
    print('  prep:     pending={} running={}'.format(
        c['prep_pending'], c['prep_running']))
    print('  DB: {}'.format(jobdb.db_path()))
    if args.failed:
        rows = jobdb.list_jobs(conn, status=jobdb.STATUS_FAILED, limit=args.limit)
        if not rows:
            print('no failed jobs')
        for row in rows:
            print('  #{} {} {}  attempts={}  {}'.format(
                row['id'], row['kind'], row['source'], row['attempts'],
                (row['error'] or '')[:120],
            ))
    if args.running:
        rows = jobdb.active_jobs(conn)
        for row in rows:
            ev = jobdb.latest_events(conn, row['id'], limit=1)
            step = ev[0]['message'] if ev else ''
            print('  #{} {} {}  worker={}  {}'.format(
                row['id'], row['kind'], row['source'], row['worker_id'], step[:80],
            ))
    if args.watch:
        live = sys.stderr.isatty()
        spin_i = 0
        try:
            while True:
                spin_i += 1
                jobdb.requeue_stale(conn, stale_seconds=args.stale_seconds)
                line = _status_line(conn, spin_i)
                if live:
                    sys.stderr.write('\r\033[2K' + line)
                    sys.stderr.flush()
                else:
                    print(line, flush=True)
                time.sleep(0.25 if live else 2.0)
        except KeyboardInterrupt:
            if live:
                sys.stderr.write('\n')
            return 0
    conn.close()
    return 0


def cmd_retry(args):
    conn = jobdb.connect()
    if args.sources:
        n = 0
        for source in args.sources:
            n += jobdb.retry_failed(conn, source=source)
    else:
        n = jobdb.retry_failed(conn)
    print('requeued {} failed job(s)'.format(n))
    conn.close()
    return 0


def cmd_reclaim(args):
    conn = jobdb.connect()
    n = jobdb.requeue_stale(conn, stale_seconds=args.stale_seconds)
    print('reclaimed {} stale running job(s)'.format(n))
    conn.close()
    return 0


def cmd_autodownload(args):
    # Enqueue then serve until idle
    rc = cmd_enqueue(args)
    if rc != 0:
        return rc
    # After dry-run / nothing, skip serve
    if args.dry_run:
        return 0
    conn = jobdb.connect()
    c = jobdb.counts(conn)
    conn.close()
    if c['pending'] == 0 and c['running'] == 0:
        return 0
    # Reuse serve defaults from args
    return cmd_serve(args)


def build_parser():
    parser = argparse.ArgumentParser(description='Mapterhorn SQLite job runner')
    sub = parser.add_subparsers(dest='command', required=True)

    def add_plan_args(p, with_verbose=True):
        p.add_argument('sources', nargs='*', help='source ids (default: all catalog)')
        p.add_argument('--ocean', action='store_true')
        p.add_argument('--land', action='store_true')
        p.add_argument('--skip-shoreline', action='store_true')
        p.add_argument('--include-debug', action='store_true')
        p.add_argument('--force', action='store_true')
        p.add_argument('--yes', '-y', action='store_true')
        p.add_argument('--dry-run', action='store_true')
        if with_verbose:
            p.add_argument('--verbose', '-v', action='store_true')

    def add_serve_args(p, with_verbose=True):
        p.add_argument('--download-workers', type=int, default=16,
                       help='download worker processes (default 16)')
        p.add_argument('--prep-workers', type=int, default=4,
                       help='prep worker processes (default 4)')
        p.add_argument('--jobs', '-j', type=int, default=None,
                       help='alias for --download-workers')
        p.add_argument('--prep-jobs', type=int, default=None,
                       help='alias for --prep-workers')
        p.add_argument('--stale-seconds', type=int, default=jobdb.DEFAULT_STALE_SECONDS)
        if with_verbose:
            p.add_argument('--verbose', '-v', action='store_true')

    p_enq = sub.add_parser('enqueue', help='plan and write jobs to SQLite')
    p_enq_auto = p_enq.add_subparsers(dest='enqueue_what', required=True)
    p_enq_ad = p_enq_auto.add_parser('autodownload', help='enqueue source download/prep')
    add_plan_args(p_enq_ad)
    p_enq_ad.set_defaults(func=cmd_enqueue)

    p_serve = sub.add_parser('serve', help='run worker processes until queue idle')
    add_serve_args(p_serve)
    p_serve.set_defaults(func=cmd_serve)

    p_status = sub.add_parser('status', help='show job counts')
    p_status.add_argument('--failed', action='store_true')
    p_status.add_argument('--running', action='store_true')
    p_status.add_argument('--watch', action='store_true')
    p_status.add_argument('--limit', type=int, default=50)
    p_status.add_argument('--stale-seconds', type=int, default=jobdb.DEFAULT_STALE_SECONDS)
    p_status.set_defaults(func=cmd_status)

    p_retry = sub.add_parser('retry', help='requeue failed jobs')
    p_retry.add_argument('sources', nargs='*', help='limit to these sources')
    p_retry.set_defaults(func=cmd_retry)

    p_reclaim = sub.add_parser('reclaim', help='requeue stale running jobs')
    p_reclaim.add_argument('--stale-seconds', type=int, default=jobdb.DEFAULT_STALE_SECONDS)
    p_reclaim.set_defaults(func=cmd_reclaim)

    p_auto = sub.add_parser('autodownload', help='enqueue then serve until done')
    add_plan_args(p_auto, with_verbose=True)
    add_serve_args(p_auto, with_verbose=False)
    p_auto.set_defaults(func=cmd_autodownload)

    return parser


def _normalize_serve_aliases(args):
    if getattr(args, 'jobs', None) is not None:
        args.download_workers = args.jobs
    if getattr(args, 'prep_jobs', None) is not None:
        args.prep_workers = args.prep_jobs


def main():
    parser = build_parser()
    args = parser.parse_args()
    _normalize_serve_aliases(args)
    # multiprocessing needs fork context friendly cwd
    os.chdir(PIPELINES_DIR)
    return args.func(args) or 0


if __name__ == '__main__':
    sys.exit(main())
