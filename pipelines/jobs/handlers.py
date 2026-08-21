# Source download / prep handlers used by the job runner.
#
# Markers DOWNLOAD_COMPLETE / READY stay the filesystem contract for covering.
import json
import os
import subprocess
import sys

import log
import source_marker
import utils
from source_download import catalog_urls

PIPELINES_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG_ROOT = utils.catalog_root()
DOWNLOAD_RECIPE_NEEDLES = (
    'source_download.py',
    'source_gmrt_download.py',
    'create_file_list.py',
)


def py_cmd(*args):
    return [sys.executable] + list(args)


def justfile_recipe_lines(source):
    just_path = '{}/{}/Justfile'.format(CATALOG_ROOT, source)
    if not os.path.isfile(just_path):
        raise FileNotFoundError('missing Justfile for source {}'.format(source))
    lines = []
    with open(just_path) as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith('#') or line.startswith('['):
                continue
            if line.endswith(':') and ' ' not in line:
                continue
            if ' #' in line:
                line = line.split(' #', 1)[0].rstrip()
            lines.append(line)
    return lines


def is_download_recipe_line(line):
    return any(needle in line for needle in DOWNLOAD_RECIPE_NEEDLES)


def recipe_line_to_cmd(line):
    store = utils.store_dir('source-store').rstrip('/') + '/'
    line = line.replace('source-store/', store)
    parts = line.split()
    if len(parts) >= 4 and parts[:3] == ['uv', 'run', 'python']:
        return py_cmd(*parts[3:])
    if len(parts) >= 2 and parts[0] == 'python':
        return py_cmd(*parts[1:])
    return ['bash', '-lc', line]


def source_download_cmd(source):
    just_path = '{}/{}/Justfile'.format(CATALOG_ROOT, source)
    text = ''
    if os.path.isfile(just_path):
        with open(just_path) as f:
            text = f.read()
    if 'source_gmrt_download.py' in text:
        return py_cmd('source_gmrt_download.py', source)
    if 'source_download.py' in text or catalog_urls(source):
        return py_cmd('source_download.py', source)
    return None


def run_command(cmd, on_line=None):
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    env['UV_NO_SYNC'] = '1'
    # Cap nested GDAL / OpenMP threads under job workers
    env.setdefault('OMP_NUM_THREADS', '1')
    env.setdefault('GDAL_NUM_THREADS', '1')
    env.setdefault('MAPTERHORN_PREP_POOL_SIZE', os.environ.get('MAPTERHORN_PREP_POOL_SIZE', '1'))
    if on_line:
        on_line('running: {}'.format(' '.join(cmd)))
    p = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=PIPELINES_DIR,
        env=env,
        bufsize=0,
    )
    buf = b''
    while True:
        chunk = p.stdout.read(4096)
        if not chunk:
            break
        buf += chunk
        text = buf.decode('utf-8', errors='replace').replace('\r', '\n')
        lines = text.split('\n')
        buf = lines[-1].encode('utf-8')
        for line in lines[:-1]:
            if on_line:
                on_line(line)
    if buf and on_line:
        on_line(buf.decode('utf-8', errors='replace'))
    code = p.wait()
    if code != 0:
        raise subprocess.CalledProcessError(code, cmd)


def run_source_download(source, force=False, on_line=None):
    if force:
        source_marker.clear_download_marker(source)
        source_marker.clear_ready_marker(source)
    if source_marker.is_download_complete(source) and not force:
        if on_line:
            on_line('already fetched, skip wget')
        return
    cmd = source_download_cmd(source)
    if cmd is None:
        if on_line:
            on_line('no download step')
        if not source_marker.is_download_complete(source):
            source_marker.mark_download_complete(source)
        return
    run_command(cmd, on_line=on_line)
    if not source_marker.is_download_complete(source):
        if catalog_urls(source):
            raise RuntimeError(
                '{} finished without {}'.format(source, source_marker.DOWNLOAD_MARKER))
        source_marker.mark_download_complete(source)
    if on_line:
        on_line('download complete')


def run_source_prep(source, force=False, on_line=None):
    if source == 'shoreline':
        return run_shoreline_prep(force=force, on_line=on_line)
    cmds = [
        recipe_line_to_cmd(line)
        for line in justfile_recipe_lines(source)
        if not is_download_recipe_line(line)
    ]
    if not cmds:
        if on_line:
            on_line('no unzip/bounds steps in Justfile')
    for cmd in cmds:
        run_command(cmd, on_line=on_line)
    if not source_marker.is_download_complete(source):
        if catalog_urls(source):
            raise RuntimeError(
                '{} finished without {}'.format(source, source_marker.DOWNLOAD_MARKER))
        source_marker.mark_download_complete(source)
    source_marker.mark_ready(source)
    if on_line:
        on_line('READY')
    log.info('autodownload source', source=source)


def shoreline_is_ready():
    shoreline = utils.store_dir('mask-store') + '/shoreline'
    return (
        os.path.isfile('{}/READY'.format(shoreline))
        and os.path.isfile('{}/land_3857.gpkg'.format(shoreline))
    )


def run_shoreline_prep(force=False, on_line=None):
    if force:
        ready = utils.store_dir('mask-store') + '/shoreline/READY'
        if os.path.isfile(ready):
            os.remove(ready)
    if shoreline_is_ready() and not force:
        if on_line:
            on_line('shoreline already ready')
        return
    cmd = [sys.executable, 'source_prepare_shoreline.py']
    run_command(cmd, on_line=on_line)
    log.info('loaded shoreline')


def payload_force(job_row):
    try:
        payload = json.loads(job_row['payload_json'] or '{}')
    except (TypeError, ValueError):
        payload = {}
    return bool(payload.get('force'))
