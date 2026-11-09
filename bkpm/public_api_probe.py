#!/usr/bin/env python3
"""Inspect observed, public BKPM investment JSON endpoints without credentials.

Only fixed URLs observed in browser Network logs are contacted. Records JSON
structure, array counts and field names, not personal records or raw payloads.
No endpoint guessing, login bypass, or undocumented bulk pagination.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

BASE = "https://regionalinvestment.bkpm.go.id"
ENDPOINTS = {
    "cards": "/be/peluang/peluang_investasi_card/",
    "regions": "/be/peluang/peluang_investasi_wilayah",
    "sectors": "/be/peluang/peluang_investasi_sektor/",
    "commodity_geojson": "/data/komoditas.geojson",
}
MAX_BYTES = 5 * 1024 * 1024


def describe_json(value, depth: int = 0) -> dict:
    """Describe container structure and sizes without storing row values."""
    if isinstance(value, list):
        result = {"type": "array", "length": len(value)}
        if value and depth < 5:
            result["first_item_structure"] = describe_json(value[0], depth + 1)
        return result
    if isinstance(value, dict):
        result = {"type": "object", "keys": sorted(str(k) for k in value)}
        if depth < 5:
            result["fields"] = {
                str(k): describe_json(v, depth + 1)
                for k, v in value.items()
            }
        return result
    return {"type": type(value).__name__}


def get_public_json(session: requests.Session, url: str):
    parsed = urlparse(url)
    if (parsed.scheme != "https" or
            parsed.hostname != "regionalinvestment.bkpm.go.id" or
            parsed.path not in ENDPOINTS.values() or
            parsed.query or parsed.fragment):
        raise ValueError("URL is not one of the observed public endpoints")
    with session.get(url, timeout=(12, 30), stream=True,
                     allow_redirects=False) as response:
        if response.status_code in (401, 403, 429):
            raise RuntimeError(f"Access restricted: HTTP {response.status_code}")
        if response.is_redirect:
            raise RuntimeError(f"Redirect HTTP {response.status_code}; not following")
        response.raise_for_status()
        ctype = response.headers.get("Content-Type", "").split(";")[0].lower().strip()
        if ctype not in {"application/json", "application/geo+json"}:
            raise RuntimeError(f"Unexpected content type {ctype!r}")
        raw = bytearray()
        for chunk in response.iter_content(65536):
            raw.extend(chunk)
            if len(raw) > MAX_BYTES:
                raise RuntimeError("Payload exceeds 5 MiB cap; not saved")
        return json.loads(raw), response.status_code, ctype, len(raw)


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=Path("data/bkpm/discovery/api_structure.json"))
    parser.add_argument("--delay", type=float, default=2.0)
    args = parser.parse_args(argv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = "bkpm-public-schema-audit/1.0"
    results = {}
    restricted = False
    for name, path in ENDPOINTS.items():
        if restricted:
            results[name] = {"status": "skipped_after_access_restriction"}
            continue
        url = BASE + path
        print("AUDIT", url, flush=True)
        try:
            data, status, ctype, nbytes = get_public_json(session, url)
            results[name] = {
                "url": url,
                "http_status": status,
                "content_type": ctype,
                "bytes": nbytes,
                "structure": describe_json(data),
            }
            print(" OK", status, ctype, nbytes, "bytes")
        except Exception as exc:
            results[name] = {"url": url, "error": str(exc)[:250]}
            print(" ERROR", str(exc)[:250])
            if "Access restricted" in str(exc):
                restricted = True
        time.sleep(max(1.0, args.delay))
    output = {
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "inspection_only": True,
        "records_downloaded_to_disk": 0,
        "endpoint_count": len(results),
        "endpoints": results,
    }
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    print("SAVED:", args.output)
    return 0 if any("structure" in rec for rec in results.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
