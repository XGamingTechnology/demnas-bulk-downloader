#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

UPSTREAM="${BHUMI_UPSTREAM_WMS:-https://bhumi.atrbpn.go.id/expapi/bhumigs/umum/wms}"

exec python3 bhumi/proxy_wms.py \
  --host 127.0.0.1 \
  --port 8765 \
  --upstream "$UPSTREAM"
