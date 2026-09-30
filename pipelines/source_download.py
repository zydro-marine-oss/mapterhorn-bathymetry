import os
import sys

import utils


def download_from_internet(source):
    urls = []
    with open('../source-catalog/{}/file_list.txt'.format(source)) as f:
        urls = [l.strip() for l in f.readlines() if l.strip()]
    total = len(urls)
    for j, url in enumerate(urls, start=1):
        print('[{}/{}] downloading {}...'.format(j, total, url))
        command = (
            'cd source-store/{} && wget --continue --progress=bar:force "{}"'
        ).format(source, url)
        out, err = utils.run_command(command, silent=False, stream=True)
        if err:
            raise RuntimeError('wget failed for {}: {}'.format(url, err))


def main():
    source = None
    if len(sys.argv) > 1:
        source = sys.argv[1]
        print('downloading {}...'.format(source))
    else:
        print('source argument missing...')
        exit()

    utils.create_folder('source-store/{}/'.format(source))
    download_from_internet(source)


if __name__ == '__main__':
    main()
