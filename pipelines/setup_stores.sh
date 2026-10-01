#!/usr/bin/env bash
# Run from pipelines/ (or any cwd; script cds to its own directory).
set -euo pipefail

HDD_ROOT="/run/media/zydro/external1/mapterhorn"
SSD_ROOT="/home/zydro/mapterhorn-data"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ ! -d /run/media/zydro/external1 ]]; then
  echo "HDD not mounted: /run/media/zydro/external1" >&2
  exit 1
fi
if [[ ! -d /run/media/zydro/external2 ]]; then
  echo "SSD not mounted: /run/media/zydro/external2" >&2
  exit 1
fi

mkdir -p \
  "$SSD_ROOT/source-store" \
  "$SSD_ROOT/aggregation-store" \
  "$SSD_ROOT/tmp-store" \
  "$SSD_ROOT/mask-store" \
  "$HDD_ROOT/pmtiles-store" \
  "$HDD_ROOT/bundle-store" \
  "$HDD_ROOT/tar-store" \
  "$HDD_ROOT/polygon-store" \
  "$HDD_ROOT/meta-store"

link_store() {
  local name="$1"
  local target="$2"
  if [[ -L "$name" ]]; then
    rm -f "$name"
  elif [[ -e "$name" ]]; then
    echo "refusing to replace non-symlink path: $SCRIPT_DIR/$name" >&2
    exit 1
  fi
  ln -s "$target" "$name"
  echo "$name -> $target"
}

# SSD: random-access working data
link_store source-store "$SSD_ROOT/source-store"
link_store aggregation-store "$SSD_ROOT/aggregation-store"
link_store tmp-store "$SSD_ROOT/tmp-store"
link_store mask-store "$SSD_ROOT/mask-store"

# HDD: sequential / archival
link_store pmtiles-store "$HDD_ROOT/pmtiles-store"
link_store bundle-store "$HDD_ROOT/bundle-store"
link_store tar-store "$HDD_ROOT/tar-store"
link_store polygon-store "$HDD_ROOT/polygon-store"
link_store meta-store "$HDD_ROOT/meta-store"

echo "done."
