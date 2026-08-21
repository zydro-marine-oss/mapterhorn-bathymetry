# SQLite job queue for durable source download/prep work.
#
# DB path: $MAPTERHORN_DATA_ROOT/meta-store/jobs.sqlite
import json
import os
import sqlite3
import time

import utils

KIND_SOURCE_DOWNLOAD = 'source_download'
KIND_SOURCE_PREP = 'source_prep'

STATUS_PENDING = 'pending'
STATUS_RUNNING = 'running'
STATUS_SUCCEEDED = 'succeeded'
STATUS_FAILED = 'failed'
STATUS_CANCELLED = 'cancelled'

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_STALE_SECONDS = 600


def db_path():
    return utils.store_dir('meta-store') + '/jobs.sqlite'


def _now():
    return time.time()


def connect(path=None):
    path = path or db_path()
    utils.create_folder(os.path.dirname(path))
    conn = sqlite3.connect(path, timeout=60.0)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=60000')
    conn.execute('PRAGMA foreign_keys=ON')
    migrate(conn)
    return conn


def migrate(conn):
    conn.executescript(
        '''
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at REAL NOT NULL,
            label TEXT NOT NULL,
            config_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL REFERENCES runs(id),
            kind TEXT NOT NULL,
            source TEXT NOT NULL,
            status TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 100,
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            worker_id TEXT,
            error TEXT,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL,
            started_at REAL,
            finished_at REAL,
            heartbeat_at REAL,
            updated_at REAL NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_jobs_claim
            ON jobs(status, kind, priority, id);
        CREATE INDEX IF NOT EXISTS idx_jobs_run
            ON jobs(run_id, status);
        CREATE INDEX IF NOT EXISTS idx_jobs_source
            ON jobs(source, kind, status);

        CREATE TABLE IF NOT EXISTS job_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL REFERENCES jobs(id),
            created_at REAL NOT NULL,
            message TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_job_events_job
            ON job_events(job_id, id);
        '''
    )
    conn.commit()


def create_run(conn, label, config=None):
    now = _now()
    cur = conn.execute(
        'INSERT INTO runs (created_at, label, config_json) VALUES (?, ?, ?)',
        (now, label, json.dumps(config or {})),
    )
    conn.commit()
    return cur.lastrowid


def enqueue(
    conn,
    run_id,
    kind,
    source,
    priority=100,
    max_attempts=DEFAULT_MAX_ATTEMPTS,
    payload=None,
    force=False,
):
    # Skip if pending/running/succeeded already exists unless force.
    existing = conn.execute(
        '''
        SELECT id, status FROM jobs
        WHERE kind = ? AND source = ?
          AND status IN (?, ?, ?)
        ORDER BY id DESC LIMIT 1
        ''',
        (kind, source, STATUS_PENDING, STATUS_RUNNING, STATUS_SUCCEEDED),
    ).fetchone()
    if existing is not None and not force:
        return existing['id']

    if force:
        conn.execute(
            '''
            UPDATE jobs SET status = ?, updated_at = ?, error = ?
            WHERE kind = ? AND source = ? AND status IN (?, ?)
            ''',
            (
                STATUS_CANCELLED, _now(), 'replaced by force enqueue',
                kind, source, STATUS_PENDING, STATUS_RUNNING,
            ),
        )

    now = _now()
    cur = conn.execute(
        '''
        INSERT INTO jobs (
            run_id, kind, source, status, priority, attempts, max_attempts,
            payload_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
        ''',
        (
            run_id, kind, source, STATUS_PENDING, priority,
            max_attempts, json.dumps(payload or {}), now, now,
        ),
    )
    conn.commit()
    return cur.lastrowid


def claim(conn, kinds, worker_id):
    kinds = list(kinds)
    if not kinds:
        return None
    placeholders = ','.join('?' * len(kinds))
    now = _now()
    # Serialize claims across worker processes
    conn.isolation_level = None
    try:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute(
            '''
            SELECT id FROM jobs
            WHERE status = ? AND kind IN ({})
            ORDER BY priority ASC, id ASC
            LIMIT 1
            '''.format(placeholders),
            [STATUS_PENDING] + kinds,
        ).fetchone()
        if row is None:
            conn.execute('COMMIT')
            return None
        job_id = row['id']
        conn.execute(
            '''
            UPDATE jobs SET
                status = ?,
                worker_id = ?,
                attempts = attempts + 1,
                started_at = COALESCE(started_at, ?),
                heartbeat_at = ?,
                updated_at = ?,
                error = NULL
            WHERE id = ? AND status = ?
            ''',
            (STATUS_RUNNING, worker_id, now, now, now, job_id, STATUS_PENDING),
        )
        conn.execute('COMMIT')
    except Exception:
        try:
            conn.execute('ROLLBACK')
        except Exception:
            pass
        raise
    finally:
        conn.isolation_level = ''  # restore default (deferred transactions)
    return get_job(conn, job_id)


def heartbeat(conn, job_id):
    now = _now()
    conn.execute(
        'UPDATE jobs SET heartbeat_at = ?, updated_at = ? WHERE id = ? AND status = ?',
        (now, now, job_id, STATUS_RUNNING),
    )
    conn.commit()


def add_event(conn, job_id, message):
    message = (message or '').rstrip()
    if message == '':
        return
    if len(message) > 2000:
        message = message[:1999] + '…'
    conn.execute(
        'INSERT INTO job_events (job_id, created_at, message) VALUES (?, ?, ?)',
        (job_id, _now(), message),
    )
    conn.commit()


def succeed(conn, job_id):
    now = _now()
    conn.execute(
        '''
        UPDATE jobs SET
            status = ?, finished_at = ?, heartbeat_at = ?, updated_at = ?,
            worker_id = NULL, error = NULL
        WHERE id = ?
        ''',
        (STATUS_SUCCEEDED, now, now, now, job_id),
    )
    conn.commit()


def fail(conn, job_id, error, requeue=True):
    now = _now()
    row = get_job(conn, job_id)
    if row is None:
        return
    err = str(error)
    if len(err) > 4000:
        err = err[:3999] + '…'
    can_retry = requeue and row['attempts'] < row['max_attempts']
    status = STATUS_PENDING if can_retry else STATUS_FAILED
    conn.execute(
        '''
        UPDATE jobs SET
            status = ?,
            error = ?,
            finished_at = ?,
            heartbeat_at = ?,
            updated_at = ?,
            worker_id = NULL,
            started_at = CASE WHEN ? = ? THEN NULL ELSE started_at END
        WHERE id = ?
        ''',
        (
            status, err, now, now, now,
            status, STATUS_PENDING,
            job_id,
        ),
    )
    conn.commit()
    add_event(conn, job_id, 'fail: {}'.format(err))


def requeue_stale(conn, stale_seconds=DEFAULT_STALE_SECONDS):
    cutoff = _now() - stale_seconds
    cur = conn.execute(
        '''
        UPDATE jobs SET
            status = ?,
            worker_id = NULL,
            started_at = NULL,
            heartbeat_at = NULL,
            updated_at = ?,
            error = 'reclaimed stale running job'
        WHERE status = ? AND (heartbeat_at IS NULL OR heartbeat_at < ?)
        ''',
        (STATUS_PENDING, _now(), STATUS_RUNNING, cutoff),
    )
    conn.commit()
    return cur.rowcount


def retry_failed(conn, source=None):
    if source:
        cur = conn.execute(
            '''
            UPDATE jobs SET
                status = ?, error = NULL, worker_id = NULL,
                started_at = NULL, finished_at = NULL, heartbeat_at = NULL,
                updated_at = ?, attempts = 0
            WHERE status = ? AND source = ?
            ''',
            (STATUS_PENDING, _now(), STATUS_FAILED, source),
        )
    else:
        cur = conn.execute(
            '''
            UPDATE jobs SET
                status = ?, error = NULL, worker_id = NULL,
                started_at = NULL, finished_at = NULL, heartbeat_at = NULL,
                updated_at = ?, attempts = 0
            WHERE status = ?
            ''',
            (STATUS_PENDING, _now(), STATUS_FAILED),
        )
    conn.commit()
    return cur.rowcount


def get_job(conn, job_id):
    row = conn.execute('SELECT * FROM jobs WHERE id = ?', (job_id,)).fetchone()
    return row


def list_jobs(conn, status=None, kind=None, run_id=None, limit=200):
    clauses = []
    args = []
    if status:
        clauses.append('status = ?')
        args.append(status)
    if kind:
        clauses.append('kind = ?')
        args.append(kind)
    if run_id is not None:
        clauses.append('run_id = ?')
        args.append(run_id)
    where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
    args.append(limit)
    return conn.execute(
        'SELECT * FROM jobs {} ORDER BY id DESC LIMIT ?'.format(where),
        args,
    ).fetchall()


def counts(conn, run_id=None):
    if run_id is None:
        rows = conn.execute(
            'SELECT status, kind, COUNT(*) AS n FROM jobs GROUP BY status, kind'
        ).fetchall()
    else:
        rows = conn.execute(
            '''
            SELECT status, kind, COUNT(*) AS n FROM jobs
            WHERE run_id = ? GROUP BY status, kind
            ''',
            (run_id,),
        ).fetchall()
    out = {
        'pending': 0,
        'running': 0,
        'succeeded': 0,
        'failed': 0,
        'cancelled': 0,
        'download_pending': 0,
        'download_running': 0,
        'prep_pending': 0,
        'prep_running': 0,
        'total': 0,
    }
    for row in rows:
        status = row['status']
        kind = row['kind']
        n = row['n']
        out['total'] += n
        if status in out:
            out[status] += n
        if kind == KIND_SOURCE_DOWNLOAD and status == STATUS_PENDING:
            out['download_pending'] += n
        if kind == KIND_SOURCE_DOWNLOAD and status == STATUS_RUNNING:
            out['download_running'] += n
        if kind == KIND_SOURCE_PREP and status == STATUS_PENDING:
            out['prep_pending'] += n
        if kind == KIND_SOURCE_PREP and status == STATUS_RUNNING:
            out['prep_running'] += n
    return out


def run_is_terminal(conn, run_id):
    row = conn.execute(
        '''
        SELECT COUNT(*) AS n FROM jobs
        WHERE run_id = ? AND status IN (?, ?)
        ''',
        (run_id, STATUS_PENDING, STATUS_RUNNING),
    ).fetchone()
    return row['n'] == 0


def active_jobs(conn, kinds=None):
    if kinds:
        placeholders = ','.join('?' * len(kinds))
        return conn.execute(
            '''
            SELECT * FROM jobs
            WHERE status = ? AND kind IN ({})
            ORDER BY heartbeat_at DESC
            '''.format(placeholders),
            [STATUS_RUNNING] + list(kinds),
        ).fetchall()
    return conn.execute(
        'SELECT * FROM jobs WHERE status = ? ORDER BY heartbeat_at DESC',
        (STATUS_RUNNING,),
    ).fetchall()


def latest_events(conn, job_id, limit=1):
    return conn.execute(
        '''
        SELECT message FROM job_events
        WHERE job_id = ? ORDER BY id DESC LIMIT ?
        ''',
        (job_id, limit),
    ).fetchall()


def has_open_job(conn, kind, source):
    row = conn.execute(
        '''
        SELECT id FROM jobs
        WHERE kind = ? AND source = ? AND status IN (?, ?, ?)
        LIMIT 1
        ''',
        (kind, source, STATUS_PENDING, STATUS_RUNNING, STATUS_SUCCEEDED),
    ).fetchone()
    return row is not None


def enqueue_prep_after_download(conn, run_id, source, priority=50, force=False):
    return enqueue(
        conn,
        run_id,
        KIND_SOURCE_PREP,
        source,
        priority=priority,
        payload={'after': 'download'},
        force=force,
    )
