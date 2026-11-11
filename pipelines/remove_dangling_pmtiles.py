# /// script
# requires-python = ">=3.13"
# dependencies = [
# ]
#
# [tool.pixi.workspace]
# channels = ["conda-forge"]
# ///

from glob import glob
import os


def list_pmtiles_filepaths():
    # One extra directory level is real (z7 folders). Skip a nested
    # pmtiles-store self-link created by ln following an existing symlink.
    paths = list(glob('pmtiles-store/*.pmtiles'))
    for folder in glob('pmtiles-store/*/'):
        name = os.path.basename(folder.rstrip('/'))
        if name == 'pmtiles-store':
            continue
        paths.extend(glob(os.path.join(folder, '*.pmtiles')))
    seen = set()
    unique = []
    for path in paths:
        if not os.path.isfile(path):
            continue
        real = os.path.realpath(path)
        if real in seen:
            continue
        seen.add(real)
        unique.append(path)
    return unique


def main():
    aggregation_id = [folder.split('/')[-1] for folder in sorted(glob('aggregation-store/*'))][-1]

    filepaths = glob(f'aggregation-store/{aggregation_id}/*-aggregation.csv')
    filepaths += glob(f'aggregation-store/{aggregation_id}/*-downsampling.csv')

    expected_pmtiles_filenames = set([])
    for filepath in filepaths:
        filename = filepath.split('/')[-1]
        expected_pmtiles_filenames.add(filename.replace('-aggregation.csv', '.pmtiles').replace('-downsampling.csv', '.pmtiles'))

    pmtiles_filepaths = list_pmtiles_filepaths()

    print(f'num expected files: {len(expected_pmtiles_filenames)}')
    print(f'num present files:  {len(pmtiles_filepaths)}')
    for pmtiles_filepath in pmtiles_filepaths:
        pmtiles_filename = pmtiles_filepath.split('/')[-1]
        if pmtiles_filename not in expected_pmtiles_filenames:
            print(f'Removing {pmtiles_filepath}...')
            try:
                os.remove(pmtiles_filepath)
            except FileNotFoundError:
                print(f'already gone: {pmtiles_filepath}')
    print('done')

if __name__ == '__main__':
    main()