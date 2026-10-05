#!/usr/bin/env python3
"""
Probe known/public BHUMI Persil rendering variants.

This is a diagnostic, not a crawler. It performs only a handful of requests
against public map endpoints and reports whether each response is an image or
an OGC/HTML error.

Evidence behind the variants:
- Current BHUMI HAR: /expapi/bhumigs/umum/wms and legend layer umum:Persil
- Historical public WMS integrations: workspace umum, layer PersilHak,
  WMS 1.1.1, EPSG:3857

No cookies, tokens, or authentication bypasses are used.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Dict, Tuple

import requests


CURRENT_WMS = "https://bhumi.atrbpn.go.id/expapi/bhumigs/umum/wms"
LEGACY_PROXY_WMS = (
    "https://bhumi.atrbpn.go.id/proxy/"
    "http://10.20.20.142:80/geoserver/umum/wms"
)
REFERER = "https://bhumi.atrbpn.go.id/"

DEFAULT_BBOX_4326 = (
    104.08144856688278,
    -3.508670771548452,
    104.43584512679433,
    -3.3288696787825245,
)


def lonlat_to_mercator(lon: float, lat: float) -> Tuple[float, float]:
    origin = 20037508.342789244
    x = lon * origin / 180.0
    lat = max(min(lat, 89.5), -89.5)
    y = math.log(math.tan((90.0 + lat) * math.pi / 360.0))
    y = y * origin / math.pi
    return x, y


def bbox_3857(bbox4326):
    minx, miny, maxx, maxy = bbox4326
    x0, y0 = lonlat_to_mercator(minx, miny)
    x1, y1 = lonlat_to_mercator(maxx, maxy)
    return x0, y0, x1, y1


def detect_payload(resp: requests.Response) -> Tuple[str, str]:
    body = resp.content
    prefix = body[:2000].lstrip().lower()
    ctype = resp.headers.get("content-type", "").lower()

    if body.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG", ""
    if body[:3] == b"\xff\xd8\xff":
        return "JPEG", ""
    if (
        prefix.startswith(b"<?xml")
        or b"<serviceexception" in prefix
        or b"<ows:exception" in prefix
    ):
        return "XML_ERROR", resp.text[:1200].replace("\n", " ")
    if b"<html" in prefix or "text/html" in ctype:
        return "HTML", resp.text[:500].replace("\n", " ")
    return f"OTHER({ctype or 'unknown'})", body[:200].decode("utf-8", "replace")


def run_request(
    session: requests.Session,
    name: str,
    url: str,
    params: Dict[str, str],
    output_dir: Path,
    timeout: int,
):
    print(f"\n=== {name} ===")
    print(f"URL: {url}")
    try:
        resp = session.get(url, params=params, timeout=timeout, allow_redirects=True)
    except requests.RequestException as exc:
        print(f"RESULT: REQUEST_ERROR {type(exc).__name__}: {exc}")
        return False

    kind, detail = detect_payload(resp)
    print(f"HTTP: {resp.status_code}")
    print(f"Content-Type: {resp.headers.get('content-type', '')}")
    print(f"Bytes: {len(resp.content)}")
    print(f"Final URL: {resp.url}")
    print(f"RESULT: {kind}")

    safe_name = name.lower().replace(" ", "_").replace("/", "_")
    suffix = ".png" if kind == "PNG" else ".jpg" if kind == "JPEG" else ".txt"
    out = output_dir / f"{safe_name}{suffix}"
    out.write_bytes(resp.content)
    print(f"Saved: {out}")

    if detail:
        print(f"DETAIL: {detail}")

    return kind in {"PNG", "JPEG"}


def main() -> int:
    ap = argparse.ArgumentParser(description="Probe public BHUMI Persil map services")
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--output-dir", default="/tmp/bhumi_probe")
    args = ap.parse_args()

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    b3857 = bbox_3857(DEFAULT_BBOX_4326)
    b3857s = ",".join(f"{v:.8f}" for v in b3857)

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; demnas-bulk-downloader/1.0)",
            "Referer": REFERER,
            "Accept": "image/png,image/*,application/xml,text/xml,*/*;q=0.8",
        }
    )

    tests = [
        (
            "01_current_legend",
            CURRENT_WMS,
            {
                "SERVICE": "WMS",
                "REQUEST": "GetLegendGraphic",
                "VERSION": "1.3.0",
                "FORMAT": "image/png",
                "WIDTH": "12",
                "HEIGHT": "12",
                "LAYER": "umum:Persil",
            },
        ),
        (
            "02_current_persilhak_3857",
            CURRENT_WMS,
            {
                "service": "WMS",
                "format": "image/png",
                "tiled": "false",
                "propertyname": "NIB,TIPEHAK,LUASPETA,PENGGUNAAN",
                "srs": "EPSG:3857",
                "transparent": "true",
                "exceptions": "application/vnd.ogc.se_xml",
                "styles": "",
                "feature_count": "101",
                "version": "1.1.1",
                "request": "GetMap",
                "layers": "PersilHak",
                "width": "512",
                "height": "512",
                "bbox": b3857s,
            },
        ),
        (
            "03_current_persil_3857",
            CURRENT_WMS,
            {
                "service": "WMS",
                "format": "image/png",
                "tiled": "false",
                "srs": "EPSG:3857",
                "transparent": "true",
                "exceptions": "application/vnd.ogc.se_xml",
                "styles": "",
                "version": "1.1.1",
                "request": "GetMap",
                "layers": "Persil",
                "width": "512",
                "height": "512",
                "bbox": b3857s,
            },
        ),
        (
            "04_legacy_proxy_persilhak",
            LEGACY_PROXY_WMS,
            {
                "service": "WMS",
                "format": "image/png",
                "tiled": "false",
                "propertyname": "NIB,TIPEHAK,LUASPETA,PENGGUNAAN",
                "srs": "EPSG:3857",
                "transparent": "true",
                "exceptions": "application/vnd.ogc.se_xml",
                "styles": "",
                "feature_count": "101",
                "version": "1.1.1",
                "request": "GetMap",
                "layers": "PersilHak",
                "width": "512",
                "height": "512",
                "bbox": b3857s,
            },
        ),
    ]

    successes = 0
    for name, url, params in tests:
        if run_request(session, name, url, params, outdir, args.timeout):
            successes += 1

    print("\n=== SUMMARY ===")
    print(f"Image responses: {successes}/{len(tests)}")
    print(f"Artifacts: {outdir}")
    if successes <= 1:
        print(
            "Only the known legend (or no map image) worked. "
            "This strongly suggests the current Persil map is rendered from "
            "a tile/vector source rather than ordinary WMS GetMap."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
