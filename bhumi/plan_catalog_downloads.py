#!/usr/bin/env python3
"""
Classify published BHUMI catalog layers by download strategy.

This tool only reads public catalog metadata. It does not authenticate,
bypass access controls, or scrape protected feature payloads.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import requests


CATALOG_URL = "https://bhumi.atrbpn.go.id/panel/items/layers"
BHUMI_BASE = "https://bhumi.atrbpn.go.id"


def fetch_catalog(limit: int, pages: int, timeout: int) -> list[dict]:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; demnas-bulk-downloader/1.0)",
        "Referer": f"{BHUMI_BASE}/peta",
        "Accept": "application/json",
    })

    rows: list[dict] = []
    for page in range(1, pages + 1):
        params = {
            "filter[status][_eq]": "published",
            "limit": limit,
            "page": page,
        }
        r = session.get(CATALOG_URL, params=params, timeout=timeout)
        r.raise_for_status()
        payload = r.json()
        batch = payload.get("data", []) if isinstance(payload, dict) else []
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < limit:
            break
    return rows


def classify(row: dict) -> tuple[str, str]:
    vendor = str(row.get("map_service_vendor") or "").strip()
    url = str(row.get("map_service_url") or "").strip()
    layer = str(row.get("map_service_layer_name") or "").strip()
    vendor_l = vendor.lower()
    url_l = url.lower()

    if vendor_l == "arcgis":
        if "/featureserver" in url_l:
            return (
                "arcgis-feature",
                "High: inspect FeatureServer layers then query features/GeoJSON where allowed",
            )
        if "/mapserver" in url_l or "/mapserver/export" in url_l:
            return (
                "arcgis-map",
                "High: inspect MapServer JSON; query vector sublayers or export map where supported",
            )
        return (
            "arcgis-other",
            "Medium: inspect ArcGIS service metadata before download",
        )

    if vendor_l in {"3d tile", "3d tiles"}:
        return (
            "3d-tiles",
            "High: fetch tileset.json then referenced 3D tile assets",
        )

    if vendor_l == "terrain":
        return (
            "terrain",
            "High: fetch tilejson/tiles metadata then terrain tiles",
        )

    if "{x}" in url and "{y}" in url and "{z}" in url:
        return (
            "xyz-tile",
            "High: XYZ tile template; download only requested zoom/AOI",
        )

    if vendor_l == "geoserver":
        if url.startswith("/"):
            if url.startswith("/bhumigs/"):
                return (
                    "bhumi-wrapper",
                    "Restricted/unknown: catalog/legend may be public; feature/render access may use BHUMI application endpoints",
                )
            return (
                "relative-ogc",
                f"Medium: resolve against {BHUMI_BASE} and probe OGC capabilities",
            )

        if url.startswith("http://") or url.startswith("https://"):
            if "/wms/" in url_l or url_l.endswith("/wms"):
                return (
                    "wms",
                    "Medium: rendered map; try GetCapabilities/GetMap, not raw vector by default",
                )
            if "/ows" in url_l or "/geoserver" in url_l:
                return (
                    "ogc",
                    "High/Medium: probe WMS/WFS GetCapabilities; WFS may expose vector features",
                )
            return (
                "geoserver-other",
                "Medium: inspect service URL and supported OGC operations",
            )

    return (
        "unknown",
        "Manual inspection required",
    )


def resolved_url(row: dict) -> str:
    url = str(row.get("map_service_url") or "").strip()
    if url.startswith("/"):
        return BHUMI_BASE + url
    return url


def normalized(row: dict) -> dict:
    category, strategy = classify(row)
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "vendor": row.get("map_service_vendor"),
        "service_url": row.get("map_service_url"),
        "resolved_url": resolved_url(row),
        "service_layer": row.get("map_service_layer_name"),
        "type": row.get("type"),
        "category": category,
        "strategy": strategy,
        "sw_bound": row.get("sw_bound"),
        "ne_bound": row.get("ne_bound"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Plan download strategy for BHUMI catalog")
    ap.add_argument("search", nargs="?", default="")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--pages", type=int, default=20)
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--json", dest="json_path")
    ap.add_argument("--csv", dest="csv_path")
    args = ap.parse_args()

    try:
        rows = fetch_catalog(args.limit, args.pages, args.timeout)
    except (requests.RequestException, ValueError) as exc:
        print(f"Gagal membaca katalog: {exc}", file=sys.stderr)
        return 2

    items = [normalized(r) for r in rows]

    needle = args.search.lower().strip()
    if needle:
        items = [
            x for x in items
            if needle in json.dumps(x, ensure_ascii=False).lower()
        ]

    counts = Counter(x["category"] for x in items)
    print(f"Layers: {len(items)}")
    print("\n=== SUMMARY ===")
    for category, count in sorted(counts.items()):
        print(f"{category:20s} {count:3d}")

    print("\n=== PLAN ===")
    for x in items:
        print("\n---")
        print(f"name: {x['name']}")
        print(f"category: {x['category']}")
        print(f"vendor: {x['vendor']}")
        print(f"service_url: {x['service_url']}")
        print(f"resolved_url: {x['resolved_url']}")
        print(f"service_layer: {x['service_layer']}")
        print(f"strategy: {x['strategy']}")

    if args.json_path:
        p = Path(args.json_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nJSON: {p}")

    if args.csv_path:
        p = Path(args.csv_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        fields = [
            "id", "name", "vendor", "service_url", "resolved_url",
            "service_layer", "type", "category", "strategy",
        ]
        with p.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(items)
        print(f"CSV: {p}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
