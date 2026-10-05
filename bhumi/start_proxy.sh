#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

UPSTREAM="${BHUMI_UPSTREAM_WMS:-}"

if [[ -z "$UPSTREAM" ]]; then
  echo "BHUMI_UPSTREAM_WMS belum di-set."
  echo
  echo "Audit kandidat dulu:"
  echo "  python3 bhumi/proxy_wms.py --probe"
  echo
  echo "Setelah ada endpoint valid:"
  echo "  export BHUMI_UPSTREAM_WMS='https://.../geoserver/.../wms'"
  echo "  bash bhumi/start_proxy.sh"
  exit 1
fi

exec python3 bhumi/proxy_wms.py   --host 127.0.0.1   --port 8765   --upstream "$UPSTREAM"
