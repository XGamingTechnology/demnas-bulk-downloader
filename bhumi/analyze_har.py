#!/usr/bin/env python3
"""
Analyze a browser HAR captured from BHUMI ATR/BPN.

The analyzer never uploads the HAR anywhere. It scans requests locally and
prints likely map/data endpoints (WMS/WFS/GeoServer/ArcGIS/vector tiles/expapi).

IMPORTANT:
HAR files may contain cookies, authorization headers, session tokens and
personal data. Do not commit raw HAR files to a public repository.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit


INTERESTING = re.compile(
    r"(wms|wfs|wmts|geoserver|ows|GetMap|GetFeature|GetFeatureInfo|"
    r"mapserver|featureserver|arcgis|vector|\.pbf(?:\?|$)|mvt|tile|tiles|"
    r"expapi|getpersil|rating_layer|persil|bidang|identify|query)",
    re.I,
)

SENSITIVE_HEADERS = {
    "cookie",
    "set-cookie",
    "authorization",
    "proxy-authorization",
    "x-api-key",
}


def safe_headers(headers):
    result = []
    for item in headers or []:
        name = str(item.get("name", ""))
        value = str(item.get("value", ""))
        if name.lower() in SENSITIVE_HEADERS:
            value = "[REDACTED]"
        result.append((name, value))
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Analyze BHUMI HAR network capture")
    ap.add_argument("har", type=Path)
    ap.add_argument("--all", action="store_true", help="Show every request")
    ap.add_argument(
        "--details",
        action="store_true",
        help="Print selected request/response headers with secrets redacted",
    )
    args = ap.parse_args()

    try:
        with args.har.open("r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except Exception as exc:
        print(f"Gagal membaca HAR: {exc}", file=sys.stderr)
        return 2

    entries = doc.get("log", {}).get("entries", [])
    print(f"Entries: {len(entries)}")

    hosts = Counter()
    for e in entries:
        url = e.get("request", {}).get("url", "")
        hosts[urlsplit(url).netloc] += 1

    if hosts:
        print("\nHosts:")
        for host, count in hosts.most_common():
            print(f"  {count:4d}  {host}")

    interesting = []
    for i, e in enumerate(entries, 1):
        req = e.get("request", {})
        res = e.get("response", {})
        url = req.get("url", "")
        if args.all or INTERESTING.search(url):
            interesting.append((i, req, res))

    print(f"\nCandidate requests: {len(interesting)}")
    for i, req, res in interesting:
        method = req.get("method", "?")
        status = res.get("status", "?")
        url = req.get("url", "")
        mime = res.get("content", {}).get("mimeType", "")
        print(f"\n[{i}] {method}  HTTP {status}")
        print(f"URL: {url}")
        if mime:
            print(f"MIME: {mime}")

        if args.details:
            print("Request headers:")
            for name, value in safe_headers(req.get("headers")):
                if name.lower() in {
                    "origin", "referer", "content-type", "accept",
                    "authorization", "cookie"
                }:
                    print(f"  {name}: {value}")

            print("Response headers:")
            for name, value in safe_headers(res.get("headers")):
                if name.lower() in {
                    "location", "content-type", "server",
                    "www-authenticate", "set-cookie"
                }:
                    print(f"  {name}: {value}")

            post = req.get("postData", {})
            if post:
                ctype = post.get("mimeType", "")
                text = post.get("text", "")
                print(f"POST MIME: {ctype}")
                if text:
                    # Avoid dumping potential secrets/body data; only metadata.
                    print(f"POST body length: {len(text)} bytes")

    if not interesting:
        print(
            "\nTidak ada request peta/data yang terdeteksi. "
            "Capture ulang Network dengan filter 'All', reload halaman, "
            "aktifkan layer yang ingin diambil, klik satu objek/bidang, "
            "lalu Save All As HAR."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
