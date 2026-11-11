# List all NOAA S-102 Edition 3.0.0 HDF5 tiles and write file_list.txt.
# Requires: aws CLI (no credentials; --no-sign-request).
import os
import subprocess
import sys

BUCKET = 'noaa-s102-pds'
PREFIX = 'ed3.0.0/'
HTTP_BASE = 'https://noaa-s102-pds.s3.amazonaws.com'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'file_list.txt')


def main():
    cmd = [
        'aws', 's3', 'ls', '--no-sign-request', '--recursive',
        's3://{}/{}'.format(BUCKET, PREFIX),
    ]
    print('listing s3://{}/{} ...'.format(BUCKET, PREFIX), flush=True)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('aws s3 ls failed with code {}'.format(proc.returncode))

    urls = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        # aws s3 ls --recursive: DATE TIME SIZE KEY
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        key = parts[3]
        if not key.endswith('.h5'):
            continue
        if not key.startswith(PREFIX):
            continue
        urls.append('{}/{}'.format(HTTP_BASE, key))

    urls = sorted(set(urls))
    with open(OUT, 'w') as f:
        for url in urls:
            f.write(url + '\n')
    print('wrote {} urls to {}'.format(len(urls), OUT))


if __name__ == '__main__':
    main()
