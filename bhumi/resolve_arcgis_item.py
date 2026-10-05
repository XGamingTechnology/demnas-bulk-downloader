#!/usr/bin/env python3
"""
Resolve the public ArcGIS Online item used for
"Bidang Tanah - Bhumi AtrBpn" and print its source service URLs.

No authentication is used. This only reads public ArcGIS Online item
metadata/data.

Known item:
  11987ae333e5411ea95d5537a2b85296
"""

from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import urlparse

import requests


DEFAULT_ITEM_ID = "11987ae333e5411ea95d5537a2b85296"
PORTAL = "https://www.arcgis.com"


def walk_urls(value, path="$"):
    if isinstance(value, dict):
        for k, v in value.items():
            p = f"{path}.{k}"
            if isinstance(v, str) and v.startswith(("http://", "https://")):
                yield p, v
            yield from walk_urls(v, p)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from walk_urls(v, f"{path}[{i}]")


def get_json(session, url, timeout):
    r = session.get(
        url,
        params={"f": "json"},
        timeout=timeout,
        allow_redirects=True,
    )
    r.raise_for_status()
    try:
        return r.json()
    except ValueError as exc:
        raise RuntimeError(
            f"Response bukan JSON: {url} "
            f"Content-Type={r.headers.get('content-type', '')}"
        ) from exc


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Resolve public ArcGIS Online item source URLs."
    )
    ap.add_argument("--item-id", default=DEFAULT_ITEM_ID)
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--save-dir")
    args = ap.parse_args()

    item_id = args.item_id.strip()
    base = f"{PORTAL}/sharing/rest/content/items/{item_id}"

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; demnas-bulk-downloader/1.0)",
        "Accept": "application/json,text/plain,*/*",
    })

    try:
        meta = get_json(session, base, args.timeout)
        data = get_json(session, f"{base}/data", args.timeout)
    except (requests.RequestException, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if isinstance(meta, dict) and meta.get("error"):
        print(
            "ArcGIS item error: "
            + json.dumps(meta["error"], ensure_ascii=False),
            file=sys.stderr,
        )
        return 3

    print("=== ITEM ===")
    for key in (
        "id", "title", "type", "typeKeywords", "owner", "access",
        "url", "description", "snippet",
    ):
        value = meta.get(key) if isinstance(meta, dict) else None
        if value not in (None, "", []):
            if key in {"description", "snippet"}:
                value = str(value).replace("\n", " ")[:500]
            print(f"{key}: {value}")

    urls = []
    seen = set()

    direct_url = meta.get("url") if isinstance(meta, dict) else None
    if isinstance(direct_url, str) and direct_url.startswith(("http://", "https://")):
        seen.add(direct_url)
        urls.append(("item.url", direct_url))

    for path, url in walk_urls(data):
        if url not in seen:
            seen.add(url)
            urls.append((path, url))

    print("\n=== SOURCE URLS ===")
    if not urls:
        print("(tidak menemukan URL service di item metadata/data)")
    else:
        for path, url in urls:
            print(f"{path}: {url}")

    if args.save_dir:
        from pathlib import Path

        out = Path(args.save_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{item_id}_item.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (out / f"{item_id}_data.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nSaved metadata: {out}")

    # Hint based on discovered service URL.
    for _path, url in urls:
        u = url.lower()
        if "wmts" in u:
            print("\n=== WMTS CANDIDATE ===")
            print(url)
            if "request=getcapabilities" not in u.lower():
                sep = "&" if "?" in url else "?"
                print(
                    "Capabilities candidate: "
                    + url
                    + sep
                    + "SERVICE=WMTS&REQUEST=GetCapabilities&VERSION=1.0.0"
                )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
