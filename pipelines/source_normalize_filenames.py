from glob import glob
import sys
import zipfile
import shutil
import os
from multiprocessing import Pool

import utils

SILENT = False

def main():
    source = None
    if len(sys.argv) > 1:
        source = sys.argv[1]
        print(f'normalizing filenames for {source}...')
    else:
        print('source argument missing...')
        exit()
    
    filepaths = sorted(glob(f'source-store/{source}/*'))

    for filepath in filepaths:
        print(filepath)

if __name__ == '__main__':
    main()
