#!/usr/bin/env python3
"""
Query BHUMI Persil through the authenticated /expapi/getPersil endpoint.

Security model:
- Requires an existing authorized token supplied through BHUMI_TOKEN.
- Never stores or prints the token.
- Does not attempt to obtain credentials, bypass authentication, or decrypt
  protected payloads.
- If the server returns an encrypted payload, it is saved as raw JSON and the
  script stops with a clear message.

Example:
  export BHUMI_TOKEN='<JWT_TOKEN_FROM_YOUR_AUTHORIZED_BHUMI_SESSION>'
  python3 bhumi/query_persil.py \
    --bbox 104.08144856688278,-3.508670771548452,104.43584512679433,-3.3288696787825245 \
    --output output/bhumi_persil.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests


BASE = "https://bhumi.atrbpn.go.id"
ENDPOINT = f"{BASE}/expapi/getPersil"
REFERER = f"{BASE}/peta"


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    try:
        vals = [float(v.strip()) for v in value.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "BBOX harus minLon,minLat,maxLon,maxLat"
        ) from exc

    if len(vals) != 4:
        raise argparse.ArgumentTypeError(
            "BBOX harus berisi empat angka"
        )

    minlon, minlat, maxlon, maxlat = vals
    if minlon >= maxlon or minlat >= maxlat:
        raise argparse.ArgumentTypeError("BBOX tidak valid")
    return minlon, minlat, maxlon, maxlat


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Query BHUMI Persil using an existing authorized token."
    )
    ap.add_argument("--bbox", required=True, type=parse_bbox)
    ap.add_argument("--width", type=int, default=800)
    ap.add_argument("--height", type=int, default=600)
    ap.add_argument("--x", type=int)
    ap.add_argument("--y", type=int)
    ap.add_argument("--feature-count", type=int, default=50)
    ap.add_argument("--output", default="output/bhumi_persil_response.json")
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print request metadata/body without sending.",
    )
    args = ap.parse_args()

    token = os.environ.get("BHUMI_TOKEN", "").strip()
    if not token and not args.dry_run:
        print(
            "BHUMI_TOKEN belum tersedia. Gunakan token dari sesi BHUMI yang "
            "memang kamu berhak akses, lalu set hanya di shell lokal:\n"
            "  export BHUMI_TOKEN='<JWT_TOKEN_FROM_YOUR_AUTHORIZED_BHUMI_SESSION>'\n"
            "Token tidak boleh di-commit atau dikirim ke chat.",
            file=sys.stderr,
        )
        return 2

    minlon, minlat, maxlon, maxlat = args.bbox
    x = args.x if args.x is not None else args.width // 2
    y = args.y if args.y is not None else args.height // 2

    body = {
        "service_layer_name": "umum:Persil",
        "width": args.width,
        "height": args.height,
        "bbox": f"{minlon},{minlat},{maxlon},{maxlat}",
        "x": x,
        "y": y,
        "query_layers": "umum:Persil",
        "url": "/expapi/getPersil",
        "service": "/bhumigs/umum",
        "FEATURE_COUNT": str(args.feature_count),
    }

    if args.dry_run:
        print(json.dumps({
            "endpoint": ENDPOINT,
            "method": "POST",
            "body": body,
            "token_required": True,
        }, indent=2))
        return 0

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; demnas-bulk-downloader/1.0)",
        "Referer": REFERER,
        "Origin": BASE,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": token,
    }

    try:
        resp = requests.post(
            ENDPOINT,
            headers=headers,
            json=body,
            timeout=args.timeout,
        )
    except requests.RequestException as exc:
        print(f"Request gagal: {exc}", file=sys.stderr)
        return 3

    print(f"HTTP {resp.status_code}")
    print(f"Content-Type: {resp.headers.get('content-type', '')}")
    print(f"Bytes: {len(resp.content)}")

    try:
        data = resp.json()
    except ValueError:
        print(resp.text[:2000], file=sys.stderr)
        return 4

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Response disimpan: {out}")

    if resp.status_code in (401, 403):
        print(
            "Token tidak diterima atau tidak memiliki izin untuk endpoint ini.",
            file=sys.stderr,
        )
        return 5

    if isinstance(data, dict) and data.get("encrypted"):
        print(
            "Server mengembalikan payload terenkripsi. Script ini sengaja "
            "tidak membypass proteksi tersebut. Gunakan data yang memang "
            "ditampilkan/diizinkan oleh BHUMI atau endpoint resmi yang "
            "menyediakan GeoJSON/fitur terbuka.",
            file=sys.stderr,
        )
        return 6

    features = data.get("features") if isinstance(data, dict) else None
    if isinstance(features, list):
        print(f"Features: {len(features)}")
        return 0

    print("Response JSON diterima, tetapi tidak berisi array 'features'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
