#!/usr/bin/env python3
"""Export *observed* BKPM opportunity detail pages as GeoJSON Point features.

Only pages explicitly listed in this repository or in --urls-file are
requested. No ID guessing, no protected endpoints, no API enumeration.
This does not spatialize LKPM realisation totals.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .investment_inventory import Client, SEEDS, kind, parse_detail, safe_url


def project_feature(record: dict) -> tuple[dict | None, str]:
    if record.get("kind") != "peluang_proyek_detail":
        return None, "not_project"
    try:
        lon = float(record.get("longitude_raw"))
        lat = float(record.get("latitude_raw"))
    except (TypeError, ValueError):
        return None, "coordinates_missing_or_invalid"
    if not (math.isfinite(lon) and math.isfinite(lat)
            and -180 <= lon <= 180 and -90 <= lat <= 90):
        return None, "coordinates_out_of_range"
    # Conservative bounding check only, not evidence of a valid site location.
    if not (94 <= lon <= 142 and -12 <= lat <= 7):
        return None, "coordinates_outside_indonesia_bbox"

    url = record.get("url")
    props = {
        "source": "BKPM Regional Investment - public opportunity detail",
        "source_url": url,
        "source_id": urlparse(url).path.split("/")[-1] if url else None,
        "title_raw": record.get("title_raw"),
        "kbli_raw": record.get("kbli_raw"),
        "investment_raw": record.get("investment_raw"),
        "year_raw": record.get("year_raw"),
        "irr_raw": record.get("irr_raw"),
        "npv_raw": record.get("npv_raw"),
        "payback_raw": record.get("payback_raw"),
        "location_quality": "published_coordinate_not_site_validated",
        "investment_kind": "investment_opportunity_not_realization",
    }
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": props,
    }, "ok"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--urls-file", type=Path,
                        help="One previously observed public detail URL per line")
    parser.add_argument("--output", type=Path,
                        default=Path("data/bkpm/spatial"))
    parser.add_argument("--delay", type=float, default=1.5)
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)

    urls = {s for s in SEEDS if kind(s) == "peluang_proyek_detail"}
    if args.urls_file:
        for raw in args.urls_file.read_text(encoding="utf-8").splitlines():
            u = safe_url(raw.strip())
            if u and kind(u) == "peluang_proyek_detail":
                urls.add(u)

    client = Client(args.delay)
    features: list[dict] = []
    audit: list[dict] = []
    for url in sorted(urls):
        info: dict = {"source_url": url, "status": "unknown"}
        try:
            html, status, sha = client.fetch(url)
            record = parse_detail(html, url)
            record["url"] = url
            feature, quality = project_feature(record)
            info.update(http_status=status, html_sha256=sha, status=quality)
            if feature:
                features.append(feature)
            else:
                info["reason"] = "No valid published coordinate; feature omitted"
        except (RuntimeError, ValueError) as exc:
            info.update(status="fetch_or_parse_error", reason=str(exc))
        audit.append(info)
        print(f"{info['status']}: {url}", flush=True)

    output = {"type": "FeatureCollection", "features": features}
    (args.output / "bkpm_opportunities_points.geojson").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (args.output / "point_audit.csv").open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["source_url", "status", "http_status",
                                                  "html_sha256", "reason"], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(audit)
    summary = {
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_pages": len(urls),
        "point_features_exported": len(features),
        "limits": [
            "Only explicitly observed project URLs",
            "Points from publisher coordinates have NOT been site-validated",
            "Not realized investment, not boundaries, not footprint polygons",
            "Coordinates interpreted as longitude/latitude EPSG:4326",
        ],
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if features else 2


if __name__ == "__main__":
    raise SystemExit(main())
