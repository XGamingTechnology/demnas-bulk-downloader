#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

OUT="/tmp/bhumi_persil_getmap.png"

python3 bhumi/download_wms.py   --version 1.3.0   --layer 'umum:Persil'   --bbox 104.08144856688278,-3.508670771548452,104.43584512679433,-3.3288696787825245   --crs EPSG:4326   --width 1879   --height 955   --raw-image "$OUT"

echo
file "$OUT"
ls -lh "$OUT"
