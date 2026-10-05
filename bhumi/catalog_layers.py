#!/usr/bin/env python3
"""
Discover public BHUMI layer catalog entries.

Prints metadata exposed by the public BHUMI layer catalog, including:
- map_service_url
- map_service_vendor
- map_service_layer_name
- bounds
- layer type

This script only reads published catalog metadata.
"""

from __future__ import annotations

import argparse
import json
import sys

import requests


URL = "https://bhumi.atrbpn.go.id/panel/items/layers"


def main() -> int:
    ap = argparse.ArgumentParser(description="Search public BHUMI layer catalog")
    ap.add_argument("search", nargs="?", default="")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--pages", type=int, default=10)
    ap.add_argument("--timeout", type=int, default=30)
    args = ap.parse_args()

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; demnas-bulk-downloader/1.0)",
        "Referer": "https://bhumi.atrbpn.go.id/peta",
        "Accept": "application/json",
    })

    needle = args.search.lower().strip()
    found = []

    for page in range(1, args.pages + 1):
        params = {
            "filter[status][_eq]": "published",
            "limit": args.limit,
            "page": page,
        }

        try:
            r = session.get(URL, params=params, timeout=args.timeout)
            r.raise_for_status()
            payload = r.json()
        except (requests.RequestException, ValueError) as exc:
            print(f"Catalog request gagal page={page}: {exc}", file=sys.stderr)
            return 2

        rows = payload.get("data", []) if isinstance(payload, dict) else []
        if not rows:
            break

        for row in rows:
            hay = json.dumps(row, ensure_ascii=False).lower()
            if not needle or needle in hay:
                found.append(row)

        if len(rows) < args.limit:
            break

    print(f"Matches: {len(found)}")
    for row in found:
        print("\n---")
        print(f"id: {row.get('id')}")
        print(f"name: {row.get('name')}")
        print(f"vendor: {row.get('map_service_vendor')}")
        print(f"service_url: {row.get('map_service_url')}")
        print(f"service_layer: {row.get('map_service_layer_name')}")
        print(f"type: {row.get('type')}")
        print(f"sw_bound: {row.get('sw_bound')}")
        print(f"ne_bound: {row.get('ne_bound')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
