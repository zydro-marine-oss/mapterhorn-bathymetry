import sys
import os
from pathlib import Path

SILENT = False

def main():
    source = None
    if len(sys.argv) > 1:
        source = sys.argv[1]
        print(f'normalizing filenames for {source}...')
    else:
        print('source argument missing...')
        exit()
    
    root_dir = Path(f'source-store/{source}')
    for path in root_dir.iterdir():
        if not path.is_file():
            continue

        name = path.name

        # Remove query parameters from filenames
        if ".tif?download=1" in name:
            name = name.replace("?download=1", "")
        
        # Replace any periods in the filename with underscores
        stem, ext = os.path.splitext(name)
        new_name = stem.replace(".", "_") + ext
        new_path = path.with_name(new_name)

        os.rename(path, new_path)
        print(f"Renamed {name} -> {new_name}")
        
if __name__ == '__main__':
    main()
