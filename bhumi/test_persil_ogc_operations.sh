#!/usr/bin/env bash
set -euo pipefail

BASE="https://bhumi.atrbpn.go.id/mprx/service"
OUT="${1:-output/persil_ogc_operation_probe}"
mkdir -p "$OUT"

curl_common=(
  -sS
  --connect-timeout 10
  --max-time 30
  --user-agent "Mozilla/5.0 (compatible; demnas-bulk-downloader/1.0)"
  --referer "https://bhumi.atrbpn.go.id/peta"
)

sanitize_headers() {
  sed -E \
    -e 's/^(Set-Cookie:).*/\1 [REDACTED]/I' \
    -e 's/^(Cookie:).*/\1 [REDACTED]/I' \
    -e 's/^(Authorization:).*/\1 [REDACTED]/I' \
    -e 's/^(Proxy-Authorization:).*/\1 [REDACTED]/I'
}

probe() {
  local name="$1"
  shift

  local raw_headers="$OUT/$name.raw.headers"
  local safe_headers="$OUT/$name.headers"
  local body="$OUT/$name.body"

  local code
  code=$(curl "${curl_common[@]}" \
    -G "$BASE" \
    "$@" \
    -D "$raw_headers" \
    -o "$body" \
    -w '%{http_code}' || true)

  if [[ -f "$raw_headers" ]]; then
    sanitize_headers < "$raw_headers" > "$safe_headers"
    rm -f "$raw_headers"
  fi

  local ctype="" bytes=0
  [[ -f "$safe_headers" ]] && ctype=$(grep -i '^content-type:' "$safe_headers" | tail -1 | tr -d '\r' || true)
  [[ -f "$body" ]] && bytes=$(wc -c < "$body")

  echo "$name => HTTP ${code:-REQUEST_ERROR} | $ctype | bytes=$bytes"
  if [[ "$code" == "200" && -f "$body" ]]; then
    file "$body" || true
    head -c 300 "$body" 2>/dev/null | tr '\n' ' ' | sed 's/[[:cntrl:]]/ /g' || true
    echo
  fi
}

echo "=== BHUMI Persil OGC operation probe ==="
echo "service: $BASE"
echo

probe "wms_130_getlegendgraphic" \
  --data-urlencode "SERVICE=WMS" \
  --data-urlencode "VERSION=1.3.0" \
  --data-urlencode "REQUEST=GetLegendGraphic" \
  --data-urlencode "LAYER=bhumi_persil" \
  --data-urlencode "STYLE=default" \
  --data-urlencode "FORMAT=image/png"

probe "wms_111_getlegendgraphic" \
  --data-urlencode "SERVICE=WMS" \
  --data-urlencode "VERSION=1.1.1" \
  --data-urlencode "REQUEST=GetLegendGraphic" \
  --data-urlencode "LAYER=bhumi_persil" \
  --data-urlencode "FORMAT=image/png"

probe "wms_130_describelayer" \
  --data-urlencode "SERVICE=WMS" \
  --data-urlencode "VERSION=1.3.0" \
  --data-urlencode "REQUEST=DescribeLayer" \
  --data-urlencode "LAYERS=bhumi_persil" \
  --data-urlencode "OUTPUT_FORMAT=application/json"

probe "wms_111_describelayer" \
  --data-urlencode "SERVICE=WMS" \
  --data-urlencode "VERSION=1.1.1" \
  --data-urlencode "REQUEST=DescribeLayer" \
  --data-urlencode "LAYERS=bhumi_persil"

probe "wms_getstyles" \
  --data-urlencode "SERVICE=WMS" \
  --data-urlencode "VERSION=1.1.1" \
  --data-urlencode "REQUEST=GetStyles" \
  --data-urlencode "LAYERS=bhumi_persil"

probe "wfs_200_getcapabilities" \
  --data-urlencode "SERVICE=WFS" \
  --data-urlencode "VERSION=2.0.0" \
  --data-urlencode "REQUEST=GetCapabilities"

probe "wfs_110_getcapabilities" \
  --data-urlencode "SERVICE=WFS" \
  --data-urlencode "VERSION=1.1.0" \
  --data-urlencode "REQUEST=GetCapabilities"

probe "wfs_200_describefeaturetype" \
  --data-urlencode "SERVICE=WFS" \
  --data-urlencode "VERSION=2.0.0" \
  --data-urlencode "REQUEST=DescribeFeatureType" \
  --data-urlencode "TYPENAMES=bhumi_persil"

echo
echo "Bodies and SANITIZED headers saved under: $OUT"
echo "This probe uses only standard OGC operations and does not attempt access-control bypass."
