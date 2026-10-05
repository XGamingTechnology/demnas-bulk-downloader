#!/usr/bin/env bash
set -euo pipefail

BASE="https://bhumi.atrbpn.go.id/mprx/service"
OUT="${1:-output/persil_getfeatureinfo_probe}"
mkdir -p "$OUT"

read -r CX CY XMIN YMIN XMAX YMAX <<EOF
$(python3 - <<'PY'
import math
minlon=104.08144856688278
minlat=-3.508670771548452
maxlon=104.43584512679433
maxlat=-3.3288696787825245
lon=(minlon+maxlon)/2
lat=(minlat+maxlat)/2
r=6378137.0
x=math.radians(lon)*r
y=r*math.log(math.tan(math.pi/4+math.radians(lat)/2))
half=50.0
print(x, y, x-half, y-half, x+half, y+half)
PY
)
EOF

sanitize_headers() {
  sed -E \
    -e 's/^(Set-Cookie:).*/\1 [REDACTED]/I' \
    -e 's/^(Cookie:).*/\1 [REDACTED]/I' \
    -e 's/^(Authorization:).*/\1 [REDACTED]/I' \
    -e 's/^(Proxy-Authorization:).*/\1 [REDACTED]/I'
}

curl_common=(
  -sS
  --connect-timeout 10
  --max-time 30
)

save_headers_safely() {
  local raw="$1"
  local safe="$2"
  sanitize_headers < "$raw" > "$safe"
  rm -f "$raw"
}

echo "=== BHUMI Persil safe HTTP/WMS diagnostic ==="
echo "service: $BASE"
echo "center EPSG:3857: $CX,$CY"
echo "output: $OUT"
echo

echo "=== HTTP policy ==="
for method in HEAD OPTIONS; do
  echo "-- $method"
  tmp="$OUT/policy_${method,,}.raw.headers"
  safe="$OUT/policy_${method,,}.headers"

  curl "${curl_common[@]}" \
    -X "$method" \
    -D "$tmp" \
    -o /dev/null \
    "$BASE" || true

  if [[ -f "$tmp" ]]; then
    save_headers_safely "$tmp" "$safe"
    sed -n '1,20p' "$safe"
  else
    echo "No response headers captured."
  fi
  echo
done

request_getmap() {
  local version="$1"
  local crskey="$2"
  local crs="$3"
  local name="getmap_${version//./_}"
  local raw_headers="$OUT/$name.raw.headers"
  local safe_headers="$OUT/$name.headers"

  local code
  code=$(curl "${curl_common[@]}" \
    -G "$BASE" \
    --data-urlencode "SERVICE=WMS" \
    --data-urlencode "VERSION=$version" \
    --data-urlencode "REQUEST=GetMap" \
    --data-urlencode "LAYERS=bhumi_persil" \
    --data-urlencode "STYLES=" \
    --data-urlencode "$crskey=$crs" \
    --data-urlencode "BBOX=$XMIN,$YMIN,$XMAX,$YMAX" \
    --data-urlencode "WIDTH=256" \
    --data-urlencode "HEIGHT=256" \
    --data-urlencode "FORMAT=image/png" \
    --data-urlencode "TRANSPARENT=true" \
    -D "$raw_headers" \
    -o "$OUT/$name.bin" \
    -w '%{http_code}' || true)

  if [[ -f "$raw_headers" ]]; then
    save_headers_safely "$raw_headers" "$safe_headers"
  fi

  local ctype="" bytes=0
  if [[ -f "$safe_headers" ]]; then
    ctype=$(grep -i '^content-type:' "$safe_headers" | tail -1 | tr -d '\r' || true)
  fi
  if [[ -f "$OUT/$name.bin" ]]; then
    bytes=$(wc -c < "$OUT/$name.bin")
  fi

  echo "GetMap $version => HTTP ${code:-REQUEST_ERROR} | $ctype | bytes=$bytes"
}

request_gfi() {
  local version="$1"
  local crskey="$2"
  local crs="$3"
  local xy1="$4"
  local xy2="$5"
  local fmt="$6"
  local slug
  slug=$(printf '%s' "$fmt" | tr '/+.' '____')
  local name="gfi_${version//./_}_$slug"
  local raw_headers="$OUT/$name.raw.headers"
  local safe_headers="$OUT/$name.headers"

  local code
  code=$(curl "${curl_common[@]}" \
    -G "$BASE" \
    --data-urlencode "SERVICE=WMS" \
    --data-urlencode "VERSION=$version" \
    --data-urlencode "REQUEST=GetFeatureInfo" \
    --data-urlencode "LAYERS=bhumi_persil" \
    --data-urlencode "QUERY_LAYERS=bhumi_persil" \
    --data-urlencode "STYLES=" \
    --data-urlencode "$crskey=$crs" \
    --data-urlencode "BBOX=$XMIN,$YMIN,$XMAX,$YMAX" \
    --data-urlencode "WIDTH=256" \
    --data-urlencode "HEIGHT=256" \
    --data-urlencode "$xy1=128" \
    --data-urlencode "$xy2=128" \
    --data-urlencode "INFO_FORMAT=$fmt" \
    --data-urlencode "FEATURE_COUNT=10" \
    -D "$raw_headers" \
    -o "$OUT/$name.body" \
    -w '%{http_code}' || true)

  if [[ -f "$raw_headers" ]]; then
    save_headers_safely "$raw_headers" "$safe_headers"
  fi

  local ctype="" bytes=0
  if [[ -f "$safe_headers" ]]; then
    ctype=$(grep -i '^content-type:' "$safe_headers" | tail -1 | tr -d '\r' || true)
  fi
  if [[ -f "$OUT/$name.body" ]]; then
    bytes=$(wc -c < "$OUT/$name.body")
  fi

  echo "GetFeatureInfo $version $fmt => HTTP ${code:-REQUEST_ERROR} | $ctype | bytes=$bytes"

  if [[ "$code" == "200" && -f "$OUT/$name.body" ]]; then
    file "$OUT/$name.body" || true
    if command -v jq >/dev/null 2>&1; then
      jq -r '
        if type=="object" then
          "JSON keys: " + (keys|join(",")) +
          (if (.features|type)=="array" then
             "\nfeatures=" + ((.features|length)|tostring)
           else "" end)
        else empty end
      ' "$OUT/$name.body" 2>/dev/null || true
    fi
  fi
}

echo
echo "=== Baseline GetMap ==="
request_getmap "1.3.0" "CRS" "EPSG:3857"
request_getmap "1.1.1" "SRS" "EPSG:3857"

echo
echo "=== Standard GetFeatureInfo variants ==="
for fmt in \
  "application/json" \
  "application/geo+json" \
  "text/plain" \
  "text/html" \
  "application/vnd.ogc.gml"
do
  request_gfi "1.3.0" "CRS" "EPSG:3857" "I" "J" "$fmt"
done

for fmt in \
  "application/json" \
  "text/plain" \
  "text/html"
do
  request_gfi "1.1.1" "SRS" "EPSG:3857" "X" "Y" "$fmt"
done

echo
echo "=== Summary ==="
echo "Bodies and SANITIZED headers saved under: $OUT"
echo "No raw Set-Cookie/Authorization headers are retained."
echo "This probe intentionally avoids auth bypass, token/cookie reuse,"
echo "origin/path obfuscation, and access-control evasion."
